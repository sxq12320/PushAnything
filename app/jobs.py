# -*- coding: utf-8 -*-
"""
jobs.py — 上传任务队列。UI 与 HTTP API 共用一个 FIFO 工作线程，
保证同一时刻只有一个浏览器自动化/上传在跑。
已完成的任务持久化到 history.json，重启后投稿记录不丢。
"""
import json
import os
import threading
import time
import uuid
import traceback
import copy
from collections import deque

import paths
import storage

HISTORY_PATH = os.path.join(paths.DATA_DIR, "history.json")
HISTORY_MAX = 200


class Job:
    def __init__(self, kind, payload):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind              # "article" | "video" | ...
        self.payload = payload
        self.status = "queued"        # queued | running | done | error
        self.logs = []
        self.results = {}
        self.source = payload.get("_source", "api")
        self.created = time.time()
        self.finished = None
        self.completed = threading.Event()
        self._owner = None

    def log(self, msg):
        line = str(msg)
        with self._owner._cv:
            self.logs.append(line)
            self.logs = self.logs[-200:]
        self._owner.emit("log", self, line)

    def finish(self, ok, results=None):
        with self._owner._cv:
            self.results = results or {}
            values = list(self.results.values())
            successes = sum(isinstance(r, dict) and r.get("ok") is True for r in values)
            failures = sum(not isinstance(r, dict) or r.get("ok") is not True for r in values)
            if not ok or not successes:
                self.status = "error"
            elif failures:
                self.status = "partial"
            elif any(r.get("needs_attention") for r in values):
                self.status = "attention"
            else:
                self.status = "done"
            self.finished = time.time()

    def to_dict(self):
        plats = self.payload.get("platforms") or []
        if isinstance(plats, dict):
            plats = [k for k, v in plats.items() if v]
        return {
            "id": self.id, "kind": self.kind, "status": self.status,
            "source": self.source, "logs": list(self.logs[-200:]),
            "title": self.payload.get("title", ""),
            "platforms": plats,
            "results": copy.deepcopy(self.results),
            "created": self.created, "finished": self.finished,
            "can_retry": self.status in ("error", "partial"),
            "retry_of": self.payload.get("_retry_of"),
        }


class JobQueue:
    def __init__(self, history_path=None):
        self.history_path = history_path or HISTORY_PATH
        self._q = deque()
        self._jobs = {}
        self._hist = {}          # id -> dict，持久化的已完成任务
        self._listeners = []
        self._cv = threading.Condition()
        self._load_history()
        threading.Thread(target=self._worker, daemon=True).start()

    def _load_history(self):
        try:
            with open(self.history_path, encoding="utf-8") as handle:
                for j in json.load(handle):
                    self._hist[j["id"]] = j
        except Exception:
            pass

    def _persist(self, job):
        d = job.to_dict()
        d["_payload"] = copy.deepcopy(job.payload)
        self._hist[d["id"]] = d
        try:
            items = sorted(self._hist.values(),
                           key=lambda x: -x["created"])[:HISTORY_MAX]
            self._hist = {j["id"]: j for j in items}
            storage.atomic_json(self.history_path, items)
        except Exception as exc:
            job.log(f"投稿记录保存失败: {exc}")

    def add_listener(self, cb):
        """cb(kind, job, msg): kind ∈ 'log'|'done'|'status'"""
        self._listeners.append(cb)

    def emit(self, kind, job, msg):
        for cb in list(self._listeners):
            try:
                cb(kind, job, msg)
            except Exception:
                pass

    def submit(self, kind, payload):
        job = Job(kind, copy.deepcopy(payload))
        job._owner = self
        with self._cv:
            self._q.append(job)
            self._jobs[job.id] = job
            self._cv.notify()
        return job

    def get(self, job_id):
        with self._cv:
            return self._jobs.get(job_id)

    def detail(self, job_id):
        with self._cv:
            job = self._jobs.get(job_id)
            value = job.to_dict() if job else copy.deepcopy(self._hist.get(job_id))
            if value:
                value["can_retry"] = (value.get("status") in ("error", "partial")
                                      and bool(job or value.get("_payload")))
                value.pop("_payload", None)
            return value

    def retry(self, job_id, source="ui"):
        with self._cv:
            previous = self._jobs.get(job_id)
            saved = self._hist.get(job_id, {})
            status = previous.status if previous else saved.get("status")
            if status not in ("error", "partial"):
                raise ValueError("只有失败或部分失败的任务可以重试")
            payload = copy.deepcopy(previous.payload if previous else saved.get("_payload"))
            if not payload:
                raise ValueError("旧版记录未保存任务内容，请重新选择文章投递")
            results = previous.results if previous else saved.get("results", {})
            if payload.get("platforms"):
                platforms = payload["platforms"]
                if isinstance(platforms, list):
                    platforms = {p: True for p in platforms}
                payload["platforms"] = {p: True for p, enabled in platforms.items()
                                        if enabled and not results.get(p, {}).get("ok")}
                if not payload["platforms"]:
                    raise ValueError("所选平台均已成功，无需再次上传")
            payload.update({"_source": source, "_retry_of": job_id})
            return self.submit(previous.kind if previous else saved["kind"], payload)

    def cancel(self, job_id):
        with self._cv:
            job = self._jobs.get(job_id)
            if not job or job.status != "queued":
                return False
            self._q.remove(job)
            job.status = "cancelled"
            job.finished = time.time()
            self._persist(job)
            job.completed.set()
        self.emit("done", job, None)
        return True

    def recent(self, n=50):
        with self._cv:
            ids = set(self._hist) | set(self._jobs)
            items = [self.detail(job_id) for job_id in ids]
            return sorted(items, key=lambda j: -j["created"])[:n]

    def _worker(self):
        import runner  # 延迟导入避免循环
        while True:
            with self._cv:
                while not self._q:
                    self._cv.wait()
                job = self._q.popleft()
                job.status = "running"
            self.emit("status", job, None)
            try:
                results = runner.run_job(job)
                job.finish(True, results)
            except Exception as e:
                job.log(f"任务异常: {e}")
                job.log(traceback.format_exc(limit=3))
                job.finish(False, {"task": {"ok": False, "err": str(e)}})
            with self._cv:
                self._persist(job)
                completed = [j for j in self._jobs.values() if j.finished is not None]
                for old in sorted(completed, key=lambda j: -j.created)[HISTORY_MAX:]:
                    self._jobs.pop(old.id, None)
                job.completed.set()
            self.emit("done", job, None)


queue = JobQueue()
