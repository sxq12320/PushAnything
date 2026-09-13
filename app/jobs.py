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
from collections import deque

import paths

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

    def log(self, msg):
        line = str(msg)
        self.logs.append(line)
        queue.emit("log", self, line)

    def finish(self, ok, results=None):
        self.status = "done" if ok else "error"
        self.results = results or {}
        self.finished = time.time()
        queue.emit("done", self, None)

    def to_dict(self):
        plats = self.payload.get("platforms") or []
        if isinstance(plats, dict):
            plats = [k for k, v in plats.items() if v]
        return {
            "id": self.id, "kind": self.kind, "status": self.status,
            "source": self.source, "logs": self.logs[-200:],
            "title": self.payload.get("title", ""),
            "platforms": plats,
            "results": self.results,
            "created": self.created, "finished": self.finished,
        }


class JobQueue:
    def __init__(self):
        self._q = deque()
        self._jobs = {}
        self._hist = {}          # id -> dict，持久化的已完成任务
        self._listeners = []
        self._cv = threading.Condition()
        self._load_history()
        threading.Thread(target=self._worker, daemon=True).start()

    def _load_history(self):
        try:
            for j in json.load(open(HISTORY_PATH, encoding="utf-8")):
                self._hist[j["id"]] = j
        except Exception:
            pass

    def _persist(self, job):
        d = job.to_dict()
        self._hist[d["id"]] = d
        try:
            items = sorted(self._hist.values(),
                           key=lambda x: -x["created"])[:HISTORY_MAX]
            self._hist = {j["id"]: j for j in items}
            tmp = HISTORY_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False)
            os.replace(tmp, HISTORY_PATH)
        except Exception:
            pass

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
        job = Job(kind, payload)
        with self._cv:
            self._q.append(job)
            self._jobs[job.id] = job
            self._cv.notify()
        return job

    def get(self, job_id):
        return self._jobs.get(job_id)

    def recent(self, n=50):
        merged = dict(self._hist)
        for j in self._jobs.values():
            merged[j.id] = j.to_dict()
        jobs = sorted(merged.values(), key=lambda j: -j["created"])
        return jobs[:n]

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
                job.finish(False, {"err": str(e)})
            self._persist(job)


queue = JobQueue()
