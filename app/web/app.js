/* app.js — 前端逻辑：pywebview api 桥接 + 目录管理 + 主题选择 */
let api = null;
let curRel = null;        // 当前文章 "folder/slug" 或 "slug"
let curFolder = null;     // null=全部文章, ""=未分类, "name"=某文件夹
let previewTimer = null;
let vditor = null;
let vdReady = false;
let pendingMd = null;
let allArticles = [];
let allFolders = [];
let dirty = false;
let lastSaveAt = "";
let searchQ = "";
let page = "write";
let pubRel = null;   // 发布页选中的文章

const $ = (id) => document.getElementById(id);

// ---- SVG 图标 ----
const IC = {
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
  more: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="5" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.6" fill="currentColor" stroke="none"/></svg>',
  cloud: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
  file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
  arrowR: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>',
  ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
};

// Typora 式即时渲染编辑器（Vditor IR 模式）
vditor = new Vditor($("vditor"), {
  mode: "ir",
  toolbar: [],
  cache: { enable: false },
  typewriterMode: true,
  cdn: "vendor",
  icon: "",
  math: { engine: "KaTeX", inlineDigit: true },
  hljs: { enable: true, style: "github" },
  hint: { enable: false },          // 关掉 @/: 弹窗（离线白请求，拖慢输入）
  undoStackSize: 120,
  preview: {
    markdown: { autoSpace: true, mark: true, footnotes: true, toc: true },
  },
  upload: {
    accept: "image/*",
    multiple: false,
    handler: async (files) => {
      const f = files && files[0];
      if (!f || !f.type || !f.type.startsWith("image/") || !api) return null;
      const dataUrl = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result);
        r.onerror = rej;
        r.readAsDataURL(f);
      });
      const r = await api.save_pasted_image(curRel || "", dataUrl);
      if (r && r.ok) {
        return `\n![粘贴图片](${r.src})\n`;
      }
      toast("粘贴图片失败: " + ((r && r.msg) || "未知错误"));
      return null;
    },
  },
  placeholder: "用 Markdown 开始写作…",
  height: "100%",
  input: () => { markDirty(true); updatePreview(); scheduleAutoSave(); },
  after: () => {
    vdReady = true;
    if (pendingMd !== null) { vditor.setValue(pendingMd); pendingMd = null; }
    updatePreview();
  },
});

function getMd() { return vdReady ? vditor.getValue() : (pendingMd || ""); }
function setMd(md) {
  if (vdReady) vditor.setValue(md || "");
  else pendingMd = md || "";
}

// ---- 编辑器工具栏 ----
function _sel() { try { return window.getSelection().toString(); } catch (e) { return ""; } }
function _ins(t) { if (vdReady) vditor.insertValue(t); }
function _wrap(b, a, ph) { _ins(b + (_sel() || ph) + a); }
function _line(pre, ph) { _ins("\n" + pre + (_sel() || ph) + "\n"); }
async function _insImage() {
  if (api) {
    const p = await api.pick_image();
    if (p) { _ins("\n![图片](" + p.replace(/\\/g, "/") + ")\n"); return; }
  }
  _wrap("![", "](D:\\图片.png)", "说明");
}

const TB_ITEMS = [
  { t: "加粗", l: "<b>B</b>", f: () => _wrap("**", "**", "加粗") },
  { t: "斜体", l: "<i>I</i>", f: () => _wrap("*", "*", "斜体") },
  { t: "删除线", l: "<s>S</s>", f: () => _wrap("~~", "~~", "删除线") },
  { sep: 1 },
  { t: "小节标题", l: "H", f: () => _line("## ", "小节标题") },
  { t: "引用", l: "“", f: () => _line("> ", "引用内容") },
  { t: "无序列表", l: "•", f: () => _line("- ", "列表项") },
  { t: "有序列表", l: "1.", f: () => _line("1. ", "列表项") },
  { sep: 1 },
  { t: "行内代码", l: "</>", f: () => _wrap("`", "`", "code") },
  { t: "代码块", l: "{…}", f: () => _wrap("\n```\n", "\n```\n", "代码") },
  { t: "链接", l: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
    f: () => _wrap("[", "](https://)", "链接文字") },
  { t: "插入图片", l: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    f: _insImage },
  { sep: 1 },
  { t: "行内公式 $…$", l: "∑", f: () => _wrap("$", "$", "E=mc^2") },
  { t: "独立公式 $$…$$", l: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 5H6l6 7-6 7h12"/></svg>',
    f: () => _wrap("\n$$\n", "\n$$\n", "\\int_0^1 x^2\\,dx") },
  { t: "表格", l: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="12" y1="3" x2="12" y2="21"/></svg>',
    f: () => _ins("\n| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n|  |  |  |\n") },
  { t: "分割线", l: "—", f: () => _ins("\n---\n") },
  { sep: 1 },
  { t: "大纲", l: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
    f: toggleOutline },
];

(function buildToolbar() {
  const bar = $("edToolbar");
  TB_ITEMS.forEach((it) => {
    if (it.sep) {
      const s = document.createElement("span");
      s.className = "ed-sep"; bar.appendChild(s); return;
    }
    const b = document.createElement("button");
    b.className = "ed-btn"; b.title = it.t; b.innerHTML = it.l;
    b.onmousedown = (e) => e.preventDefault();  // 不抢编辑器焦点
    b.onclick = it.f;
    bar.appendChild(b);
  });
})();

// ---- Typora 式快捷键 ----
$("vditor").addEventListener("keydown", (e) => {
  if (!vdReady) return;
  const mod = e.ctrlKey || e.metaKey;
  const sel = _sel();
  // 选中文字时敲成对符号直接包裹（Typora 行为）
  if (!mod && !e.altKey && sel) {
    const pair = { "*": "**", "_": "*", "`": "`", "~": "~~", "$": "$" };
    if (pair[e.key]) {
      e.preventDefault(); e.stopPropagation();
      _ins(pair[e.key] + sel + pair[e.key]);
      return;
    }
  }
  // Alt+Shift+5 删除线（无 Ctrl）
  if (e.altKey && e.shiftKey && e.code === "Digit5") {
    e.preventDefault(); e.stopPropagation();
    _wrap("~~", "~~", "删除线");
    return;
  }
  if (!mod) return;
  const k = e.key.toLowerCase();
  let ok = true;
  if (k === "b") _wrap("**", "**", "加粗");
  else if (k === "i") _wrap("*", "*", "斜体");
  else if (k === "e" || (e.shiftKey && e.code === "Backquote"))
    _wrap("`", "`", "code");
  else if (k === "k" && e.shiftKey) _wrap("\n```\n", "\n```\n", "代码");
  else if (k === "k") _wrap("[", "](https://)", "链接文字");
  else if (k === "m" && e.shiftKey) _wrap("$", "$", "E=mc^2");
  else if (k === "t")
    _ins("\n| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n|  |  |  |\n");
  else ok = false;
  if (ok) { e.preventDefault(); e.stopPropagation(); }
}, true);

// 选中文字后粘贴 URL → 自动生成链接（Typora 行为）
$("vditor").addEventListener("paste", (e) => {
  const sel = _sel();
  if (!sel || !e.clipboardData) return;
  const text = (e.clipboardData.getData("text/plain") || "").trim();
  if (/^https?:\/\/\S+$/.test(text)) {
    e.preventDefault(); e.stopPropagation();
    _ins(`[${sel}](${text})`);
  }
}, true);

// ---- 自动保存（停笔 15s 静默落盘，不触发飞书） ----
let autoSaveTimer = null;
function scheduleAutoSave() {
  if (!curRel || !dirty) return;
  clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(async () => {
    if (!dirty || !curRel || !api) return;
    const title = $("title").value.trim();
    if (!title) return;
    const r = await api.save_article(
      curRel, title, $("author").value.trim(), $("digest").value.trim(),
      $("coverPath").value, getMd(), $("styleSel").value, "", true);
    if (r && r.rel) {
      const d = new Date();
      lastSaveAt = String(d.getHours()).padStart(2, "0") + ":" +
                   String(d.getMinutes()).padStart(2, "0");
      markDirty(false);
      refreshAll();
    }
  }, 15000);
}

// ---- 大纲 ----
function toggleOutline() {
  $("outline").classList.toggle("hidden");
  renderOutline();
}
function renderOutline() {
  const box = $("outline");
  if (box.classList.contains("hidden")) return;
  const heads = [];
  getMd().split("\n").forEach((line) => {
    const m = line.match(/^(#{1,6})\s+(.+)/);
    if (m) heads.push({ lv: m[1].length, text: m[2].replace(/[*`~$]/g, "").trim() });
  });
  box.innerHTML = heads.length ? "" : '<div class="o-empty">暂无标题</div>';
  heads.forEach((h) => {
    const d = document.createElement("div");
    d.className = "o-item lv" + h.lv;
    d.textContent = h.text;
    d.title = h.text;
    d.onclick = () => scrollToHeading(h.text);
    box.appendChild(d);
  });
}
function scrollToHeading(text) {
  const root = (vditor && vditor.vditor && vditor.vditor.element) || $("vditor");
  const els = root.querySelectorAll(
    "h1,h2,h3,h4,h5,h6,[data-type='heading'],.vditor-ir__node");
  for (const el of els) {
    const t = (el.textContent || "").replace(/^#+\s*/, "").trim();
    if (t.startsWith(text)) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      try { el.click(); } catch (err) {}
      return true;
    }
  }
  return false;
}

// ---- 状态栏 ----
function markDirty(v) { dirty = v; renderStatus(); }
function renderStatus() {
  const t = getMd();
  const n = t.replace(/[\s`*#\->|!\[\]()$\\]/g, "").length;
  let left = n ? `${n} 字` : "就绪";
  if (curRel) left += "  ·  " + curRel;
  if (dirty) left += "  ·  未保存";
  else if (lastSaveAt) left += "  ·  已保存 " + lastSaveAt;
  $("stLeft").textContent = left;
  $("stDirty").className = "st-dot" + (dirty ? " on" : "");
  $("stDirty").title = dirty ? "有未保存更改" : "内容已保存";
}

function log(msg, cls) {
  const div = document.createElement("div");
  if (cls) div.className = cls;
  else if (/^=====/.test(msg)) div.className = "plat";
  else if (/失败|错误|超时/.test(msg)) div.className = "err";
  else if (/成功|已保存|完成/.test(msg)) div.className = "ok";
  div.textContent = msg;
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
}

function toast(msg, ms = 2600) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), ms);
}

function fmtDate(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (sameDay) return "今天 " + hm;
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return "昨天 " + hm;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

// ---- 弹出菜单 ----
function showMenu(x, y, items) {
  const m = $("ctxMenu");
  m.innerHTML = "";
  items.forEach((it) => {
    if (it.sep) {
      const s = document.createElement("div");
      s.className = "ctx-sep"; m.appendChild(s); return;
    }
    if (it.head) {
      const h = document.createElement("div");
      h.className = "ctx-head"; h.textContent = it.head;
      m.appendChild(h); return;
    }
    const d = document.createElement("div");
    d.className = "ctx-item" + (it.danger ? " danger" : "");
    if (it.icon) d.innerHTML = it.icon;
    const s = document.createElement("span");
    s.textContent = it.label;
    d.appendChild(s);
    d.onclick = () => { hideMenu(); it.fn && it.fn(); };
    m.appendChild(d);
  });
  m.classList.remove("hidden");
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(x, innerWidth - r.width - 8) + "px";
  m.style.top = Math.min(y, innerHeight - r.height - 8) + "px";
}
function hideMenu() { $("ctxMenu").classList.add("hidden"); }
document.addEventListener("click", (e) => {
  if (!$("ctxMenu").contains(e.target)) hideMenu();
});

// 后端事件回调
window.onBackendEvent = (ev) => {
  if (ev.kind === "log") log(ev.data);
  else if (ev.kind === "toast") toast(ev.data, 4000);
  else if (ev.kind === "refresh") refreshAll();
  else if (ev.kind === "status") { renderTasks(); renderHistory(); renderVideoHistory(); }
  else if (ev.kind === "done") {
    $("btnUpload").disabled = false;
    $("btnUpload").classList.remove("is-loading");
    $("btnVideoUp").disabled = false;
    $("btnVideoUp").classList.remove("is-loading");
    $("progressBar").classList.remove("on");
    renderTasks();
    renderHistory();
    renderVideoHistory();
    const r = ev.data || {};
    const lines = Object.entries(r).map(([k, v]) =>
      `${k}: ${v.ok ? "成功" : "失败 " + (v.err || "")}`);
    log("===== 上传结束 =====");
    lines.forEach((l) => log(l, /成功/.test(l) ? "ok" : "err"));
    toast("上传结束：" + (lines.join("；") || "无平台被选中"), 5000);
  }
};

// ---------- 目录 ----------

async function refreshAll() {
  if (!api) return;
  [allFolders, allArticles] = await Promise.all([
    api.list_folders(), api.list_articles(),
  ]);
  renderFolders();
  renderArticles();
  renderPubCard();
}

function renderFolders() {
  const box = $("folderList");
  box.innerHTML = "";
  const rows = [
    { key: null, label: "全部文章", icon: IC.layers,
      count: allArticles.length },
    { key: "", label: "未分类", icon: IC.file,
      count: allArticles.filter(a => !a.folder).length },
    ...allFolders.map(f => ({
      key: f.name, label: f.name, icon: IC.folder, count: f.count,
      folder: true,
    })),
  ];
  rows.forEach((r, i) => {
    const d = document.createElement("div");
    d.className = "folder-item" + (curFolder === r.key ? " active" : "");
    d.style.animationDelay = `${Math.min(i * 30, 300)}ms`;
    d.innerHTML = r.icon;
    const nm = document.createElement("span");
    nm.className = "fname"; nm.textContent = r.label;
    const c = document.createElement("span");
    c.className = "cnt"; c.textContent = r.count;
    d.appendChild(nm); d.appendChild(c);
    d.onclick = () => { curFolder = r.key; renderFolders(); renderArticles(); };
    if (r.folder) {
      d.oncontextmenu = (e) => {
        e.preventDefault();
        showMenu(e.clientX, e.clientY, [
          { label: "重命名", icon: IC.edit,
            fn: () => renameFolderInline(r.label) },
          { sep: true },
          { label: "删除文件夹（文章移到未分类）", icon: IC.trash,
            danger: true,
            fn: async () => {
              if (!confirm(`删除文件夹「${r.label}」？里面的文章会移到未分类。`)) return;
              await api.delete_folder(r.label);
              if (curFolder === r.label) curFolder = null;
              refreshAll();
            } },
        ]);
      };
    }
    box.appendChild(d);
  });
}

function renameFolderInline(name) {
  const row = document.createElement("div");
  row.className = "folder-new";
  row.innerHTML = `<input value="${name}" placeholder="文件夹名">`;
  $("folderList").appendChild(row);
  const inp = row.querySelector("input");
  inp.focus(); inp.select();
  const done = async (commit) => {
    const v = inp.value.trim();
    row.remove();
    if (commit && v && v !== name) {
      await api.rename_folder(name, v);
      if (curFolder === name) curFolder = v;
      refreshAll();
    }
  };
  inp.onkeydown = (e) => {
    if (e.key === "Enter") done(true);
    if (e.key === "Escape") done(false);
  };
  inp.onblur = () => done(true);
}

function newFolderInline() {
  const row = document.createElement("div");
  row.className = "folder-new";
  row.innerHTML = `<input placeholder="新文件夹名">`;
  $("folderList").appendChild(row);
  const inp = row.querySelector("input");
  inp.focus();
  const done = async (commit) => {
    const v = inp.value.trim();
    row.remove();
    if (commit && v) { await api.create_folder(v); curFolder = v; refreshAll(); }
  };
  inp.onkeydown = (e) => {
    if (e.key === "Enter") done(true);
    if (e.key === "Escape") done(false);
  };
  inp.onblur = () => done(true);
}

// ---------- 文章列表 ----------

function renderArticles() {
  const box = $("articleList");
  box.innerHTML = "";
  let list;
  if (searchQ) {
    list = allArticles.filter(a =>
      ((a.title || "") + (a.slug || "") + (a.folder || ""))
        .toLowerCase().includes(searchQ));
  } else {
    list = allArticles.filter(a =>
      curFolder === null ? true : a.folder === curFolder);
  }
  if (!list.length) {
    box.innerHTML = '<div class="empty-tip"><span class="eic">' + IC.file +
      '</span>' + (searchQ ? "没有匹配的文章" : "这里还没有文章<br>点右上角 ＋ 开始写") + '</div>';
    return;
  }
  list.forEach((a, i) => {
    const item = document.createElement("div");
    const selRel = page === "publish" ? pubRel : curRel;
    item.className = "article-item" + (a.rel === selRel ? " active" : "");
    item.style.animationDelay = `${Math.min(i * 35, 350)}ms`;
    const col = document.createElement("span");
    col.className = "col";
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = a.title || a.slug;
    const sub = document.createElement("span");
    sub.className = "sub";
    const bits = [];
    if (a.mtime) bits.push(fmtDate(a.mtime));
    if (curFolder === null && a.folder) bits.push(a.folder);
    sub.textContent = bits.join(" · ");
    col.appendChild(t); col.appendChild(sub);
    item.appendChild(col);
    if (a.feishu) {
      const c = document.createElement("span");
      c.className = "cloud"; c.innerHTML = IC.cloud;
      c.title = "已备份到飞书";
      item.appendChild(c);
    }
    const more = document.createElement("button");
    more.className = "more"; more.innerHTML = IC.more;
    more.title = "更多";
    more.onclick = (e) => { e.stopPropagation(); articleMenu(a, e); };
    item.appendChild(more);
    item.onclick = () => {
      if (page === "publish") selectPub(a.rel);
      else loadArticle(a.rel);
    };
    item.oncontextmenu = (e) => { e.preventDefault(); articleMenu(a, e); };
    box.appendChild(item);
  });
}

function articleMenu(a, e) {
  const items = [];
  if (a.feishu_url) {
    items.push({ label: "在飞书中打开", icon: IC.ext,
                 fn: () => window.open(a.feishu_url) });
    items.push({ sep: true });
  }
  items.push({ head: "移动到" });
  if (a.folder) {
    items.push({ label: "未分类", icon: IC.file,
                 fn: () => moveArticle(a, "") });
  }
  allFolders.filter(f => f.name !== a.folder).forEach(f => {
    items.push({ label: f.name, icon: IC.folder,
                 fn: () => moveArticle(a, f.name) });
  });
  items.push({ sep: true });
  items.push({ label: "删除文章", icon: IC.trash, danger: true,
    fn: async () => {
      if (!confirm(`删除「${a.title || a.slug}」？`)) return;
      await api.delete_article(a.rel);
      if (curRel === a.rel) newArticle();
      refreshAll();
    } });
  showMenu(e.clientX, e.clientY, items);
}

async function moveArticle(a, folder) {
  const r = await api.move_article(a.rel, folder);
  if (r.ok && curRel === a.rel) curRel = r.rel;
  refreshAll();
}

async function loadArticle(rel) {
  const a = await api.load_article(rel);
  if (!a) return;
  curRel = a.rel;
  $("title").value = a.title || "";
  syncTbTitle();
  $("author").value = a.author || "";
  $("digest").value = a.digest || "";
  $("coverPath").value = a.cover_path || "";
  if (a.style) $("styleSel").value = a.style;
  updateCoverThumb();
  setMd(a.md || "");
  markDirty(false); lastSaveAt = "";
  updatePreview();
  renderArticles();
}

function newArticle() {
  curRel = null;
  $("title").value = "";
  syncTbTitle();
  $("digest").value = "";
  $("coverPath").value = "";
  updateCoverThumb();
  setMd("");
  markDirty(false); lastSaveAt = "";
  updatePreview();
  renderArticles();
  $("title").focus();
}

async function saveArticle() {
  const title = $("title").value.trim();
  if (!title) { toast("先写个标题再保存"); return null; }
  const folder = (curFolder && curRel === null) ? curFolder : "";
  const r = await api.save_article(
    curRel || title, title, $("author").value.trim(),
    $("digest").value.trim(), $("coverPath").value, getMd(),
    $("styleSel").value, folder);
  curRel = r.rel;
  const d = new Date();
  lastSaveAt = String(d.getHours()).padStart(2, "0") + ":" +
               String(d.getMinutes()).padStart(2, "0");
  markDirty(false);
  refreshAll();
  toast(r.feishu_queued ? "已保存，飞书备份中…" : "已保存");
  return r.rel;
}

// ---------- 预览 ----------

function updatePreview() {
  renderStatus();
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    if (!api) return;
    const md = getMd();
    const plat = $("previewPlat").value;
    $("preview").style.opacity = "0.35";
    const r = await api.preview(md, plat, $("styleSel").value);
    if (r && r.html != null) $("preview").innerHTML = r.html;
    $("preview").style.opacity = "1";
    renderOutline();
  }, 350);
}

function updateCoverThumb() {
  const p = $("coverPath").value;
  const img = $("coverThumb");
  if (p) { img.src = "file://" + p.replace(/\\/g, "/"); img.classList.remove("hidden"); }
  else img.classList.add("hidden");
}

// ---------- 页面切换 ----------

let videoPath = "";

const PAGE_TITLE = { write: null, publish: "发布文章", video: "视频投稿" };
function setPage(p) {
  page = p;
  document.body.className = document.body.className
    .replace(/\bpage-\w+/g, "").trim();
  document.body.classList.add("page-" + p);
  document.querySelectorAll(".nav-item").forEach(n =>
    n.classList.toggle("active", n.dataset.page === p));
  const t = PAGE_TITLE[p];
  $("tbTitle").textContent = t || ($("title").value.trim() || "无标题");
  if (p === "video") { renderTasks(); renderVideoHistory(); }
  if (p === "publish") renderHistory();
  renderArticles();
}

// ---------- 发布页 ----------

function selectPub(rel) {
  pubRel = rel;
  renderPubCard();
  renderArticles();
}

function renderPubCard() {
  const card = $("pubCard");
  const a = allArticles.find(x => x.rel === pubRel);
  if (!a) {
    card.className = "pub-card";
    card.innerHTML = '<div class="pub-empty">还没有选择文章<br>' +
      '<span class="pub-hint">在左侧「文章」列表点选要发布的内容</span></div>';
    return;
  }
  card.className = "pub-card sel";
  const bits = [a.author || "", a.folder || "", a.mtime ? fmtDate(a.mtime) : "",
                a.feishu ? "已备份飞书" : ""].filter(Boolean);
  card.innerHTML =
    '<span class="pub-ic">' + IC.file + '</span>' +
    '<span class="pub-info">' +
      '<span class="pub-title">' + (a.title || a.slug) + '</span>' +
      '<span class="pub-sub">' + bits.join("  ·  ") + '</span>' +
    '</span>';
  if (a.style) $("pubStyle").value = a.style;
}

async function doPublishUpload() {
  if (!pubRel) { toast("先在左侧选择一篇文章"); return; }
  const a = await api.load_article(pubRel);
  if (!a) { toast("文章加载失败"); return; }
  const platforms = {
    wechat: $("platWechat").checked,
    zhihu: $("platZhihu").checked,
    toutiao: $("platToutiao").checked,
  };
  if (!platforms.wechat && !platforms.zhihu && !platforms.toutiao) {
    toast("至少勾选一个平台"); return;
  }
  $("log").innerHTML = "";
  $("btnUpload").disabled = true;
  $("btnUpload").classList.add("is-loading");
  $("progressBar").classList.add("on");
  log("开始上传…");
  const r = await api.upload({
    title: a.title || "", author: a.author || "",
    digest: a.digest || "",
    cover_path: $("pubCoverPath").value || a.cover_path || "",
    style: $("pubStyle").value || a.style || "",
    md: a.md || "", platforms,
    base_dir: a.base_dir || undefined,
  });
  if (!r.ok) {
    $("btnUpload").disabled = false;
    $("btnUpload").classList.remove("is-loading");
    $("progressBar").classList.remove("on");
    toast(r.msg || "上传启动失败");
    log("上传启动失败: " + (r.msg || ""), "err");
  }
}

// 投稿记录（发布页）
const PLAT_NAME = { wechat: "公众号", zhihu: "知乎", toutiao: "头条", feishu: "飞书" };
const H_STATUS_IC = {
  done: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>',
  running: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.56"/></svg>',
  queued: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>',
};
let histOpen = null;

function buildHistItem(j, i) {
  const d = document.createElement("div");
  d.className = "h-item";
  d.style.animationDelay = `${Math.min(i * 30, 300)}ms`;

  const st = document.createElement("span");
  st.className = "h-status " + j.status;
  st.innerHTML = H_STATUS_IC[j.status] || H_STATUS_IC.queued;
  d.appendChild(st);

  const main = document.createElement("div");
  main.className = "h-main";
  const t = document.createElement("div");
  t.className = "h-title";
  t.textContent = j.title || "（无标题）";
  if (j.source && j.source !== "ui") {
    const s = document.createElement("span");
    s.className = "h-src";
    s.textContent = j.source.toUpperCase();
    t.appendChild(s);
  }
  main.appendChild(t);

  const meta = document.createElement("div");
  meta.className = "h-meta";
  const kind = document.createElement("span");
  kind.className = "h-kind";
  kind.textContent = KIND_NAME[j.kind] || j.kind;
  meta.appendChild(kind);
  (j.platforms || []).forEach((p) => {
    const c = document.createElement("span");
    c.className = "h-plat";
    const r = (j.results || {})[p];
    if (r) c.classList.add(r.ok ? "ok" : "fail");
    else if (j.status === "running") c.classList.add("run");
    c.textContent = PLAT_NAME[p] || p;
    if (r && !r.ok && r.err) c.title = r.err;
    meta.appendChild(c);
  });
  main.appendChild(meta);
  d.appendChild(main);

  const tm = document.createElement("span");
  tm.className = "h-time";
  tm.textContent = fmtDate(j.created);
  d.appendChild(tm);

  if (histOpen === j.id) {
    const lg = document.createElement("div");
    lg.className = "h-logs";
    lg.textContent = (j.logs || []).join("\n") || "（暂无日志）";
    d.appendChild(lg);
  }
  d.onclick = () => {
    histOpen = histOpen === j.id ? null : j.id;
    renderHistory();
    renderVideoHistory();
  };
  return d;
}

async function renderHistory() {
  if (!api || page !== "publish") return;
  const jobs = await api.list_jobs();
  const box = $("histList");
  const list = (jobs || []).filter(j => j.kind !== "feishu");
  box.innerHTML = "";
  if (!list.length) {
    box.innerHTML = '<div class="h-empty">还没有投稿记录</div>';
    return;
  }
  list.forEach((j, i) => box.appendChild(buildHistItem(j, i)));
}

async function renderVideoHistory() {
  if (!api || page !== "video") return;
  const jobs = await api.list_jobs();
  const box = $("histListV");
  const list = (jobs || []).filter(j => j.kind === "video");
  box.innerHTML = "";
  if (!list.length) {
    box.innerHTML = '<div class="h-empty">还没有视频投稿记录</div>';
    return;
  }
  list.forEach((j, i) => box.appendChild(buildHistItem(j, i)));
}

async function pickVideo() {
  if (!api) return;
  const r = await api.pick_video();
  if (!r || !r.path) return;
  videoPath = r.path;
  $("videoDrop").classList.add("picked");
  $("vDropTitle").textContent = r.name;
  $("vDropSub").textContent = (r.size / 1048576).toFixed(1) + " MB · " + r.path;
  if (!$("vTitle").value.trim())
    $("vTitle").value = r.name.replace(/\.[^.]+$/, "");
}

async function doVideoUpload() {
  if (!videoPath) { toast("请先选择视频文件"); return; }
  const title = $("vTitle").value.trim();
  if (!title) { toast("标题不能为空"); return; }
  const platforms = {
    zhihu: $("vPlatZhihu").checked,
    toutiao: $("vPlatToutiao").checked,
  };
  if (!platforms.zhihu && !platforms.toutiao) { toast("至少勾选一个平台"); return; }
  $("log").innerHTML = "";
  $("btnVideoUp").disabled = true;
  $("btnVideoUp").classList.add("is-loading");
  $("progressBar").classList.add("on");
  log("开始上传视频…");
  const r = await api.upload_video({
    title, video_path: videoPath,
    desc: $("vDesc").value.trim(),
    cover_path: $("vCoverPath").value,
    platforms,
  });
  if (!r.ok) {
    $("btnVideoUp").disabled = false;
    $("btnVideoUp").classList.remove("is-loading");
    $("progressBar").classList.remove("on");
    toast(r.msg || "上传启动失败");
    log("上传启动失败: " + (r.msg || ""), "err");
  }
}

const KIND_NAME = { article: "图文", video: "视频", feishu: "飞书备份" };
async function renderTasks() {
  if (!api || page !== "video") return;
  const jobs = await api.list_jobs();
  const box = $("taskList");
  box.innerHTML = "";
  const list = (jobs || []).filter(j => j.kind !== "feishu");
  if (!list.length) {
    box.innerHTML = '<div class="empty-tip">还没有任务</div>';
    return;
  }
  list.forEach((j, i) => {
    const d = document.createElement("div");
    d.className = "task-item";
    d.style.animationDelay = `${Math.min(i * 30, 300)}ms`;
    const dot = document.createElement("span");
    dot.className = "t-dot " + j.status;
    const col = document.createElement("span");
    col.className = "col";
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = j.title || KIND_NAME[j.kind] || j.kind;
    const sub = document.createElement("span");
    sub.className = "sub";
    const stTxt = { queued: "排队中", running: "执行中", done: "完成", error: "失败" }[j.status] || j.status;
    sub.textContent = `${KIND_NAME[j.kind] || j.kind} · ${stTxt} · ${fmtDate(j.created)}`;
    col.appendChild(t); col.appendChild(sub);
    d.appendChild(dot); d.appendChild(col);
    d.title = "点击查看任务日志";
    d.style.cursor = "pointer";
    d.onclick = () => {
      $("log").innerHTML = "";
      (j.logs || []).forEach(l => log(l));
      if (!j.logs || !j.logs.length) log("（暂无日志）");
    };
    box.appendChild(d);
  });
}

// ---------- 飞书备份 ----------

async function backupToFeishu() {
  if (!api) return;
  const title = $("title").value.trim();
  if (!title) { toast("标题不能为空"); return; }
  log("===== 飞书备份 =====");
  const r = await api.feishu_backup({
    slug: curRel || "", title, md: getMd(),
  });
  if (!r.ok) toast(r.msg || "备份启动失败");
  else toast("已提交飞书备份");
}

// ---------- 设置 ----------

async function fillThemeSels(themes, cur) {
  ["styleSel", "cfgStyle", "pubStyle"].forEach((id) => {
    const s = $(id);
    s.innerHTML = "";
    Object.entries(themes).forEach(([k, name]) => {
      const o = document.createElement("option");
      o.value = k; o.textContent = name;
      s.appendChild(o);
    });
    if (cur) s.value = cur;
  });
}

async function openSettings() {
  if (!api) return;
  const cfg = await api.get_config();
  $("cfgFeishuOn").checked = !!cfg.feishu_enabled;
  $("cfgFeishuId").value = cfg.feishu_app_id || "";
  $("cfgFeishuSecret").value = cfg.feishu_app_secret || "";
  $("cfgFeishuFolder").value = cfg.feishu_folder_token || "";
  $("cfgAuthor").value = cfg.author || "";
  $("cfgCoverTag").value = cfg.cover_tag || "";
  $("cfgStyle").value = cfg.wechat_style || "red";
  $("cfgApiOn").checked = !!cfg.api_enabled;
  $("cfgApiPort").value = cfg.api_port || 8737;
  $("cfgApiToken").value = cfg.api_token || "";
  $("cfgDataDir").value = cfg.data_dir || "";
  $("feishuTestRes").textContent = "";
  $("settingsMsg").textContent = "";
  $("settingsMask").classList.remove("hidden");
}

function closeSettings() { $("settingsMask").classList.add("hidden"); }

async function saveSettings() {
  const r = await api.save_config({
    feishu_enabled: $("cfgFeishuOn").checked,
    feishu_app_id: $("cfgFeishuId").value.trim(),
    feishu_app_secret: $("cfgFeishuSecret").value.trim(),
    feishu_folder_token: $("cfgFeishuFolder").value.trim(),
    author: $("cfgAuthor").value.trim(),
    cover_tag: $("cfgCoverTag").value.trim(),
    wechat_style: $("cfgStyle").value,
    api_enabled: $("cfgApiOn").checked,
    api_port: parseInt($("cfgApiPort").value, 10) || 8737,
    api_token: $("cfgApiToken").value.trim(),
  });
  $("author").value = r.author || "";
  $("settingsMsg").textContent = "已保存";
  toast("设置已保存");
  setTimeout(closeSettings, 500);
}

async function testFeishu() {
  const el = $("feishuTestRes");
  el.className = "hint";
  el.textContent = "连接中…";
  const r = await api.test_feishu({
    feishu_app_id: $("cfgFeishuId").value.trim(),
    feishu_app_secret: $("cfgFeishuSecret").value.trim(),
    feishu_folder_token: $("cfgFeishuFolder").value.trim(),
  });
  el.className = "hint " + (r.ok ? "ok" : "err");
  el.textContent = r.msg;
}

// ---------- 启动 ----------

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  document.body.classList.add("page-write");
  const [cfg, themes] = await Promise.all([
    api.get_config(), api.wechat_themes()]);
  $("author").value = cfg.author || "";
  await fillThemeSels(themes, cfg.wechat_style || "red");
  refreshAll();
  updatePreview();
  const st = await api.api_status();
  $("stApi").innerHTML = st.running
    ? `<span class="dot">●</span> API 127.0.0.1:${st.port}`
    : (st.enabled ? "API 启动失败" : "API 已关闭");
});

$("btnNew").onclick = newArticle;
$("btnNewFolder").onclick = newFolderInline;
$("btnSave").onclick = saveArticle;
$("btnUpload").onclick = doPublishUpload;
$("btnCover").onclick = async () => {
  if (!api) return;
  const p = await api.pick_image();
  if (p) { $("coverPath").value = p; updateCoverThumb(); }
};
$("btnCoverClear").onclick = () => { $("coverPath").value = ""; updateCoverThumb(); };
$("previewPlat").addEventListener("change", updatePreview);
$("styleSel").addEventListener("change", updatePreview);
$("btnLoginZhihu").onclick = () => api && api.check_login("zhihu");
$("btnLoginToutiao").onclick = () => api && api.check_login("toutiao");
$("btnSettings").onclick = openSettings;
$("btnBackup").onclick = backupToFeishu;
$("btnCloseSettings").onclick = closeSettings;
$("btnSaveSettings").onclick = saveSettings;
$("btnTestFeishu").onclick = testFeishu;
$("btnPickDir").onclick = async () => {
  if (!api) return;
  const p = await api.pick_dir();
  if (!p) return;
  $("settingsMsg").textContent = "迁移中…";
  const r = await api.set_data_dir(p);
  if (r.ok) {
    $("cfgDataDir").value = r.data_dir;
    toast(r.msg, 4000);
  } else {
    toast(r.msg || "切换失败", 4000);
  }
  $("settingsMsg").textContent = r.ok ? r.msg : (r.msg || "");
};
$("settingsMask").addEventListener("click", (e) => {
  if (e.target === $("settingsMask")) closeSettings();
});

// 页面导航
document.querySelectorAll(".nav-item").forEach(n => {
  n.onclick = () => setPage(n.dataset.page);
});
$("btnGoPublish").onclick = async () => {
  if (dirty) {
    const rel = await saveArticle();
    if (!rel) return;
  }
  if (!curRel) { toast("先保存文章再发布"); return; }
  pubRel = curRel;
  setPage("publish");
  renderPubCard();
};
$("btnPubCover").onclick = async () => {
  if (!api) return;
  const p = await api.pick_image();
  if (p) $("pubCoverPath").value = p;
};
$("btnHistRefresh").onclick = renderHistory;
$("btnHistRefreshV").onclick = renderVideoHistory;
$("videoDrop").onclick = pickVideo;
$("btnVCover").onclick = async () => {
  if (!api) return;
  const p = await api.pick_image();
  if (p) $("vCoverPath").value = p;
};
$("btnVCoverClear").onclick = () => { $("vCoverPath").value = ""; };
$("btnVideoUp").onclick = doVideoUpload;
// 标题同步到标题栏（Pages 式文档标题）
function syncTbTitle() {
  if (page !== "write") return;
  $("tbTitle").textContent = $("title").value.trim() || "无标题";
}
$("title").addEventListener("input", () => { markDirty(true); syncTbTitle(); });
$("btnClearLog").onclick = () => { $("log").innerHTML = ""; };

// 元信息变更也算未保存
["author", "digest", "coverPath", "styleSel"].forEach((id) => {
  $(id).addEventListener("input", () => markDirty(true));
  $(id).addEventListener("change", () => markDirty(true));
});
$("searchInp").addEventListener("input", (e) => {
  searchQ = e.target.value.trim().toLowerCase();
  renderArticles();
});
$("searchInp").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.target.value = ""; searchQ = ""; renderArticles(); }
});

// 窗口控制
let winMaxed = false;
function syncMaxedUI() {
  document.body.classList.toggle("maxed", winMaxed);
}
async function toggleMax() {
  if (!api) return;
  await api.win_toggle_max();
  winMaxed = !winMaxed;
  syncMaxedUI();
}
$("winMin").onclick = () => api && api.win_minimize();
$("winMax").onclick = toggleMax;
$("winClose").onclick = () => api && api.win_close();
document.querySelector(".tb-drag").addEventListener("dblclick", toggleMax);

// ---- 无边框窗口缩放（拖边缘/角落） ----
const DPR = () => window.devicePixelRatio || 1;
let rzDrag = null, rzRaf = 0, rzRect = null;

document.querySelectorAll(".rz").forEach((el) => {
  el.addEventListener("mousedown", async (e) => {
    if (!api || winMaxed) return;
    const g = await api.win_geom();
    if (!g || g.maxed) return;
    rzDrag = { dir: el.className.split(" ")[1], sx: e.screenX, sy: e.screenY, g };
    e.preventDefault();
  });
});

document.addEventListener("mousemove", (e) => {
  if (!rzDrag) return;
  const d = DPR();
  const dx = (e.screenX - rzDrag.sx) * d, dy = (e.screenY - rzDrag.sy) * d;
  const g = rzDrag.g;
  let { x, y, w, h } = g;
  if (rzDrag.dir.indexOf("e") >= 0) w = g.w + dx;
  if (rzDrag.dir.indexOf("s") >= 0) h = g.h + dy;
  if (rzDrag.dir.indexOf("w") >= 0) { w = g.w - dx; x = g.x + dx; }
  if (rzDrag.dir.indexOf("n") >= 0) { h = g.h - dy; y = g.y + dy; }
  if (w < 560) { if (rzDrag.dir.indexOf("w") >= 0) x = g.x + g.w - 560; w = 560; }
  if (h < 420) { if (rzDrag.dir.indexOf("n") >= 0) y = g.y + g.h - 420; h = 420; }
  rzRect = [x, y, w, h];
  if (!rzRaf) rzRaf = requestAnimationFrame(() => {
    rzRaf = 0;
    if (rzRect) api.win_rect(rzRect[0], rzRect[1], rzRect[2], rzRect[3]);
  });
});
document.addEventListener("mouseup", () => { rzDrag = null; rzRect = null; });

// 标题栏右键 → 贴边布局（左半屏/右半屏/上半屏/最大化）
document.querySelector("#titlebar").addEventListener("contextmenu", async (e) => {
  if (!api || e.target.closest(".tb-btn")) return;
  e.preventDefault();
  const d = DPR();
  const sw = screen.availWidth * d, sh = screen.availHeight * d;
  const snap = (x, y, w, h) => {
    api.win_rect(x, y, w, h);
    winMaxed = false; syncMaxedUI();
  };
  showMenu(e.clientX, e.clientY, [
    { label: "左半屏", fn: () => snap(0, 0, sw / 2, sh) },
    { label: "右半屏", fn: () => snap(sw / 2, 0, sw / 2, sh) },
    { label: "上半屏", fn: () => snap(0, 0, sw, sh / 2) },
    { sep: 1 },
    { label: winMaxed ? "还原窗口" : "最大化", fn: toggleMax },
  ]);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("settingsMask").classList.contains("hidden"))
    closeSettings();
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    saveArticle();
  }
});
renderStatus();
