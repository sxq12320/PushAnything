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
let page = "home";
let documentEpoch = 0;
let changeRevision = 0;
let suppressInput = false;
let sourceMode = false;
let saveInFlight = null;
let saveError = "";
let previewRevision = 0;
let previewInFlight = false;
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
  typewriterMode: false,
  lang: "zh_CN",
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
    handler: async (files) => { await importImageFiles(files); return null; },
  },
  placeholder: "用 Markdown 开始写作…",
  height: "100%",
  input: () => { if (!suppressInput) markDirty(true); updatePreview(); },
  after: () => {
    vdReady = true;
    if (pendingMd !== null) { vditor.setValue(pendingMd); pendingMd = null; }
    updatePreview();
  },
});

function getMd() { return sourceMode ? $("sourceEditor").value : (vdReady ? vditor.getValue() : (pendingMd || "")); }
function setMd(md) {
  suppressInput = true;
  try {
    $("sourceEditor").value = md || "";
    if (vdReady) vditor.setValue(md || "");
    else pendingMd = md || "";
  } finally { suppressInput = false; }
}

// ---- 编辑器工具栏 ----
function _sel() { try { if (sourceMode) return $("sourceEditor").value.substring($("sourceEditor").selectionStart, $("sourceEditor").selectionEnd); return window.getSelection().toString(); } catch (e) { return ""; } }
function _ins(t) {
  if (sourceMode) {
    const editor = $("sourceEditor");
    editor.focus();
    if (document.execCommand('insertText', false, t)) return;
    editor.setRangeText(t, editor.selectionStart, editor.selectionEnd, "end");
    editor.focus(); markDirty(true); updatePreview();
  } else if (vdReady) vditor.insertValue(t);
}
function _wrap(b, a, ph) { _ins(b + (_sel() || ph) + a); }
function _line(pre, ph) { _ins("\n" + pre + (_sel() || ph) + "\n"); }
async function _insImage() {
  if (!api) return;
  const path = await api.pick_image();
  if (path) await importPickedImage(path);
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
  { t: "编写行内公式 $…$", l: "∑", f: () => openFormula(false) },
  { t: "独立公式 $$…$$", l: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 5H6l6 7-6 7h12"/></svg>',
    f: () => openFormula(true) },
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
  else if (k === "m" && e.shiftKey) openFormula(false);
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
  clearTimeout(autoSaveTimer);
  if (!dirty || !api || composing) return;
  autoSaveTimer = setTimeout(() => saveArticle(true, true), 1200);
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
function markDirty(value) {
  if (value && suppressInput) return;
  dirty = value;
  if (value) {
    changeRevision++;
    saveError = "";
    scheduleAutoSave();
    scheduleRecovery();
  }
  renderStatus();
}

function renderStatus() {
  const words = getMd().replace(/[\s`*#\->|!\[\]()$\\]/g, '').length;
  let label = words ? words + ' 字' : '就绪';
  if (curRel) label += ' · ' + curRel;
  if (saveError) label += ' · 保存失败，内容已保留';
  else if (saveInFlight) label += ' · 正在保存…';
  else if (dirty) label += ' · 等待保存';
  else if (lastSaveAt) label += ' · 已保存 ' + lastSaveAt;
  $('stLeft').textContent = label;
  $('stDirty').className = 'st-dot' + (dirty ? ' on' : '');
  $('stDirty').title = saveError || (dirty ? '有未保存更改' : '内容已保存');
  $('saveState').textContent = saveError ? '保存失败' : saveInFlight ? '保存中…' : dirty ? '等待保存' : curRel ? '已保存' : '自动保存已开启';
  $('saveState').classList.toggle('error', !!saveError);
}

function log(msg, cls) {
  const div = document.createElement("div");
  if (cls) div.className = cls;
  else if (/^=====/.test(msg)) div.className = "plat";
  else if (/失败|错误|超时/.test(msg)) div.className = "err";
  else if (/成功|已保存|完成/.test(msg)) div.className = "ok";
  div.textContent = msg;
  const box = $("log");
  const pinned = box.scrollHeight - box.scrollTop - box.clientHeight < 56;
  box.appendChild(div);
  while (box.children.length > 200) box.firstChild.remove();
  if (pinned) box.scrollTop = box.scrollHeight;
}

let toastTimer = null;
function toast(msg, ms = 2600) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), ms);
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
window.onBackendEvent = (event) => {
  if (event.kind === "log") log(event.data);
  else if (event.kind === "toast") toast(event.data, 4000);
  else if (event.kind === "refresh") refreshAll();
  else if (event.kind === "close") prepareToClose();
  else if (event.kind === "status" || event.kind === "done") {
    refreshTaskViews();
    if (event.kind === "done") {
      const task = event.data || {};
      const status = {done: "全部完成", partial: "部分失败，可重试", error: "失败，可重试", attention: "需要手动检查", cancelled: "已取消"}[task.status] || "已结束";
      toast(`${task.title || "任务"} · ${status}`, 4500);
      if (task.kind === "feishu") refreshAll();
    }
  }
};

// ---------- 目录 ----------

async function refreshAll() {
  if (!api) return;
  const [folders, articles] = await Promise.all([
    api.list_folders(), api.list_articles(),
  ]);
  allFolders = folders; allArticles = articles;
  renderFolders();
  renderArticles();
  renderPubCard();
  if (page === "home") renderHome();
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
              if (curRel && curRel.startsWith(r.label + '/') && !await flushDraft()) return;
              const result = await api.delete_folder(r.label);
              if (!result.ok) { toast(result.msg); return; }
              if (result.moved[curRel]) { curRel = result.moved[curRel]; await loadArticle(curRel, true); }
              if (result.moved[pubRel]) pubRel = result.moved[pubRel];
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
  row.innerHTML = '<input placeholder="文件夹名">';
  row.firstChild.value = name;
  $("folderList").appendChild(row);
  const inp = row.querySelector("input");
  inp.focus(); inp.select();
  let finished = false;
  const done = async (commit) => {
    if (finished) return;
    finished = true;
    const v = inp.value.trim();
    row.remove();
    if (commit && v && v !== name) {
      if (curRel && curRel.startsWith(name + '/') && !await flushDraft()) return;
      const result = await api.rename_folder(name, v);
      if (!result.ok) { toast(result.msg); return; }
      if (curFolder === name) curFolder = result.folder;
      if (curRel && curRel.startsWith(name + '/')) { curRel = result.folder + curRel.slice(name.length); await loadArticle(curRel, true); }
      if (pubRel && pubRel.startsWith(name + '/')) pubRel = result.folder + pubRel.slice(name.length);
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
    item.onclick = async () => {
      if (page === "publish") { selectPub(a.rel); return; }
      await loadArticle(a.rel);
      if (page === "home") setPage("write");
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
      if (curRel === a.rel && !await flushDraft()) return;
      const result = await api.delete_article(a.rel);
      if (!result.ok) { toast(result.msg); return; }
      if (pubRel === a.rel) pubRel = null;
      if (curRel === a.rel) { dirty = false; await newArticle(); }
      await refreshAll();
      showDeleteUndo(result.token);
    } });
  showMenu(e.clientX, e.clientY, items);
}

async function moveArticle(article, folder) {
  if (curRel === article.rel && !await flushDraft()) return;
  const result = await api.move_article(article.rel, folder);
  if (!result.ok) { toast(result.msg || "移动失败"); return; }
  if (pubRel === article.rel) pubRel = result.rel;
  if (curRel === article.rel) {
    curRel = result.rel;
    await loadArticle(result.rel, true);
  }
  await refreshAll();
}

async function loadArticle(rel, skipSave = false) {
  if (!api || (curRel === rel && !skipSave)) return;
  if (!skipSave && !await flushDraft()) return;
  const epoch = ++documentEpoch;
  const article = await api.load_article(rel);
  if (!article || epoch !== documentEpoch) return;
  if (dirty && !await flushDraft()) return;
  clearTimeout(autoSaveTimer);
  curRel = article.rel;
  $("title").value = article.title || "";
  $("author").value = article.author || "";
  $("digest").value = article.digest || "";
  $("coverPath").value = article.cover_path || "";
  if (article.style) $("styleSel").value = article.style;
  setEditorBase(article.base_dir);
  setMd(article.md || "");
  dirty = false; saveError = ""; lastSaveAt = "";
  updateCoverThumb(); syncTbTitle(); updatePreview(); renderArticles();
}

async function newArticle(template = null) {
  if (!await flushDraft()) return false;
  ++documentEpoch;
  curRel = null;
  clearTimeout(autoSaveTimer);
  $("title").value = "";
  $("digest").value = "";
  $("coverPath").value = "";
  if (template && template.style) $("styleSel").value = template.style;
  setEditorBase(defaultDraftDir);
  setMd(template ? template.md : "");
  dirty = false; saveError = ""; lastSaveAt = "";
  setPage("write");
  updateCoverThumb(); syncTbTitle(); updatePreview(); renderArticles();
  if (template && template.md) markDirty(true);
  $("title").focus();
  return true;
}

async function saveArticle(quiet = false, autosave = false) {
  // DOM click events are arguments too; only an explicit boolean means quiet.
  quiet = quiet === true;
  if (!api) return null;
  if (saveInFlight) {
    const result = await saveInFlight;
    if (!result) return null;
    if (!dirty) return curRel;
  }
  const snapshot = draftSnapshot();
  if (!snapshot.title && !snapshot.md.trim()) return curRel;
  const epoch = documentEpoch;
  const button = $("btnSave");
  button.disabled = true;
  saveError = "";
  saveInFlight = (async () => {
    try {
      const result = await api.save_article(snapshot.rel || "", snapshot.title || "无标题",
        snapshot.author, snapshot.digest, snapshot.cover_path, snapshot.md, snapshot.style,
        snapshot.folder, autosave);
      if (!result || !result.rel) throw new Error("未收到保存结果");
      if (epoch === documentEpoch) {
        curRel = result.rel;
        lastSaveAt = new Date().toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit"});
        if (snapshot.revision === changeRevision) {
          dirty = false;
          clearTimeout(autoSaveTimer);
          clearTimeout(recoveryTimer);
          await api.clear_recovery(snapshot.session, snapshot.revision);
        }
        await refreshAll();
      }
      if (!quiet) toast(result.feishu_queued ? "已保存，飞书备份已排队" : "已保存");
      return result.rel;
    } catch (error) {
      saveError = error.message || "请检查数据目录";
      if (!quiet) toast("保存失败：" + saveError, 5000);
      return null;
    } finally {
      button.disabled = false;
      saveInFlight = null;
      renderStatus();
    }
  })();
  renderStatus();
  return saveInFlight;
}

async function flushDraft() {
  clearTimeout(autoSaveTimer);
  if (!dirty && !saveInFlight) return true;
  const result = await saveArticle(true, true);
  if (!result && dirty) {
    toast("保存失败，已保留当前内容：" + saveError, 5000);
    return false;
  }
  if (dirty) return !!await saveArticle(true, true);
  return true;
}

// ---------- 预览 ----------

function updatePreview() {
  renderStatus();
  clearTimeout(previewTimer);
  const revision = ++previewRevision;
  if (page !== "write" || document.body.classList.contains("preview-hidden")) return;
  previewTimer = setTimeout(async () => {
    if (!api) return;
    if (previewInFlight) { updatePreview(); return; }
    previewInFlight = true;
    $("previewState").textContent = "更新中…";
    try {
      const result = await api.preview(getMd(), $("previewPlat").value, $("styleSel").value, curRel || "");
      if (revision === previewRevision && result && result.html != null) renderPreviewHTML(result.html);
    } catch (error) {
      if (revision === previewRevision) $("previewState").textContent = "暂时无法预览";
    } finally {
      previewInFlight = false;
      if (revision === previewRevision) $("previewState").textContent = "实时预览";
      else updatePreview();
      renderOutline();
    }
  }, 240);
}

function updateCoverThumb() {
  const p = $("coverPath").value;
  const img = $("coverThumb");
  if (p) { img.src = "file://" + p.replace(/\\/g, "/"); img.classList.remove("hidden"); }
  else img.classList.add("hidden");
}

// ---------- 页面切换 ----------

let videoPath = "";

const PAGE_TITLE = { home: "PushAnything", write: null, publish: "发布文章", video: "视频投稿" };
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
  if (p === "home") renderHome();
  if (p === "write") updatePreview();
  document.querySelectorAll(".nav-item").forEach(n => n.setAttribute("aria-current", n.dataset.page === p ? "page" : "false"));
  renderArticles();
}

// ---------- 首页 ----------
const HOME_STYLE_C = {
  wild: "#A8402B",
  red: "#D64541", blue: "#2B5EA7", green: "#2E8B6A",
  orange: "#E07B39", black: "#3A3A3C",
};
function renderHome() {
  const h = new Date().getHours();
  const hi = h < 6 ? "夜深了" : h < 12 ? "早上好" : h < 18 ? "下午好" : "晚上好";
  $("homeHello").textContent = hi;
  const box = $("homeGrid");
  box.innerHTML = "";
  const list = [...allArticles]
    .sort((a, b) => (b.mtime || 0) - (a.mtime || 0)).slice(0, 8);
  if (!list.length) {
    box.innerHTML = '<div class="home-empty">还没有文章<br>' +
      '点上面「新建文章」开始写第一篇，或在左侧搜索 / 整理目录</div>';
    return;
  }
  list.forEach((a, i) => {
    const c = document.createElement("div");
    c.className = "h-card";
    c.style.setProperty("--c", HOME_STYLE_C[a.style] || "#0071E3");
    c.style.animationDelay = `${0.32 + Math.min(i * 0.04, 0.3)}s`;
    const t = document.createElement("span");
    t.className = "t"; t.textContent = a.title || a.slug;
    const sub = document.createElement("span");
    sub.className = "sub";
    const bits = [];
    if (a.mtime) bits.push(fmtDate(a.mtime));
    if (a.folder) bits.push(a.folder);
    sub.textContent = bits.join(" · ") || " ";
    c.appendChild(t); c.appendChild(sub);
    if (a.feishu) {
      const cl = document.createElement("span");
      cl.className = "c-ic"; cl.innerHTML = IC.cloud;
      cl.title = "已备份到飞书";
      sub.appendChild(cl);
    }
    c.onclick = async () => { await loadArticle(a.rel); setPage("write"); };
    box.appendChild(c);
  });
}

// ---------- 发布页 ----------

function selectPub(rel) {
  $("pubCoverPath").value = "";
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
      '<span class="pub-title">' + escapeHTML(a.title || a.slug) + '</span>' +
      '<span class="pub-sub">' + escapeHTML(bits.join("  ·  ")) + '</span>' +
    '</span>';
  if (a.style && pubStyleRel !== a.rel) $("pubStyle").value = a.style;
  pubStyleRel = a.rel;
}

async function doPublishUpload() {
  if (!api || $("btnUpload").disabled) return;
  if (!pubRel) { toast("先在左侧选择一篇文章"); return; }
  const platforms = {wechat: $("platWechat").checked, zhihu: $("platZhihu").checked, toutiao: $("platToutiao").checked};
  if (!Object.values(platforms).some(Boolean)) { toast("至少勾选一个平台"); return; }
  await submitUpload("btnUpload", async () => {
    if (pubRel === curRel && !await flushDraft()) throw new Error("请先保存当前文章");
    const article = await api.load_article(pubRel);
    if (!article) throw new Error("文章加载失败");
    return api.upload({title: article.title, author: article.author, digest: article.digest,
      cover_path: $("pubCoverPath").value || article.cover_path || "",
      style: $("pubStyle").value || article.style || "", md: article.md,
      platforms, base_dir: article.base_dir});
  });
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
    if (r) c.classList.add(r.needs_attention ? "attention" : r.ok ? "ok" : "fail");
    else if (j.status === "running") c.classList.add("run");
    c.textContent = PLAT_NAME[p] || p;
    if (r && !r.ok && r.err) c.title = r.err;
    meta.appendChild(c);
  });
  main.appendChild(meta);
  d.appendChild(main);

  const tm = document.createElement("span");
  tm.className = "h-time";
  tm.textContent = (TASK_STATUS[j.status] || j.status) + " · " + fmtDate(j.created);
  d.appendChild(tm);
  addTaskActions(d, j);

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
  const jobs = await getTasks();
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
  const jobs = await getTasks();
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
  if (!api || $("btnVideoUp").disabled) return;
  if (!videoPath) { toast("请先选择视频文件"); return; }
  const title = $("vTitle").value.trim();
  if (!title) { toast("请填写视频标题"); return; }
  const platforms = {zhihu: $("vPlatZhihu").checked, toutiao: $("vPlatToutiao").checked};
  if (!Object.values(platforms).some(Boolean)) { toast("至少勾选一个平台"); return; }
  await submitUpload("btnVideoUp", () => api.upload_video({title, video_path: videoPath,
    desc: $("vDesc").value.trim(), cover_path: $("vCoverPath").value, platforms}));
}

const KIND_NAME = { article: "图文", video: "视频", feishu: "飞书备份" };
async function renderTasks() {
  if (!api || page !== "video") return;
  const jobs = await getTasks();
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
    const stTxt = TASK_STATUS[j.status] || j.status;
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
  $("cfgApiLan").checked = !!cfg.api_lan;
  $("cfgDataDir").value = cfg.data_dir || "";
  $("cfgWxConfig").value = cfg.wechat_config || "";
  $("feishuTestRes").textContent = "";
  $("settingsMsg").textContent = "";
  $("settingsMask").classList.remove("hidden");
  focusDialog($("settingsSheet"));
  loadMobileInfo();
}

async function loadMobileInfo() {
  const m = await api.mobile_url();
  $("mobileUrl").value = m.url;
  const qr = await api.mobile_qr();
  const img = $("mobileQr");
  if (qr.ok) { img.src = qr.qr; img.style.display = "block"; }
  else img.style.display = "none";
  if (!m.enabled) $("mobileUrlText").textContent = "本地 API 未启用，手机端不可用。";
  else if (!m.lan) $("mobileUrlText").textContent = "局域网访问已关闭，勾选上方选项后重启生效。";
  else $("mobileUrlText").textContent = "手机与电脑连同一 WiFi，扫码或输入网址即可投稿。";
}

function closeSettings() { $("settingsMask").classList.add("hidden"); restoreDialogFocus(); }

async function saveSettings() {
  const port = Number($("cfgApiPort").value);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) { toast("端口应为 1024–65535 的整数"); return; }
  const r = await api.save_config({
    feishu_enabled: $("cfgFeishuOn").checked,
    feishu_app_id: $("cfgFeishuId").value.trim(),
    feishu_app_secret: $("cfgFeishuSecret").value.trim(),
    feishu_folder_token: $("cfgFeishuFolder").value.trim(),
    author: $("cfgAuthor").value.trim(),
    cover_tag: $("cfgCoverTag").value.trim(),
    wechat_style: $("cfgStyle").value,
    api_enabled: $("cfgApiOn").checked,
    api_port: port,
    api_token: $("cfgApiToken").value.trim(),
    api_lan: $("cfgApiLan").checked,
    wechat_config: $("cfgWxConfig").value.trim(),
  });
  if (r.ok === false) { toast(r.msg); return; }
  if (!curRel && !getMd().trim()) $("author").value = r.author || "";
  $("settingsMsg").textContent = "已保存";
  toast("设置已保存");
  closeSettings();
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
  setPage("home");
  const [cfg, themes] = await Promise.all([
    api.get_config(), api.wechat_themes()]);
  $("author").value = cfg.author || "";
  defaultDraftDir = (cfg.active_data_dir || cfg.data_dir) + "/drafts";
  setEditorBase(defaultDraftDir);
  if (cfg.startup_warning) toast(cfg.startup_warning, 8000);
  await fillThemeSels(themes, cfg.wechat_style || "red");
  await refreshAll();
  await recoverDraft();
  startEventPolling();
  updatePreview();
  const st = await api.api_status();
  $("stApi").innerHTML = st.running
    ? `<span class="dot">●</span> API 127.0.0.1:${st.port}`
    : (st.enabled ? "API 启动失败" : "API 已关闭");
});

// 首页快捷操作
document.querySelectorAll(".h-act").forEach((b) => {
  b.onclick = () => {
    const act = b.dataset.act;
    if (act === "new") { setPage("write"); newArticle(); }
    else if (act === "publish") setPage("publish");
    else if (act === "video") setPage("video");
    else if (act === "settings") openSettings();
  };
});
$("homeAll").onclick = () => setPage("write");

$("btnNew").onclick = () => newArticle();
$("btnNewFolder").onclick = newFolderInline;
$("btnSave").onclick = saveArticle;
$("btnUpload").onclick = doPublishUpload;
$("btnCover").onclick = async () => {
  if (!api) return;
  const p = await api.pick_image();
  if (p) { const r = await api.import_image(curRel || "", p); if (r.ok) { $("coverPath").value = r.path; updateCoverThumb(); markDirty(true); } else toast(r.msg); }
};
$("btnCoverClear").onclick = () => { $("coverPath").value = ""; updateCoverThumb(); markDirty(true); };
$("previewPlat").addEventListener("change", updatePreview);
$("styleSel").addEventListener("change", updatePreview);
$("btnLoginZhihu").onclick = () => checkPlatformLogin("zhihu");
$("btnLoginToutiao").onclick = () => checkPlatformLogin("toutiao");
$("btnSettings").onclick = openSettings;
$("btnBackup").onclick = backupToFeishu;
$("btnCloseSettings").onclick = closeSettings;
$("btnSaveSettings").onclick = saveSettings;
$("btnTestFeishu").onclick = testFeishu;
$("btnPickWx").onclick = async () => {
  if (!api) return;
  const p = await api.pick_json();
  if (p) $("cfgWxConfig").value = p;
};
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
$("winClose").onclick = () => prepareToClose();
document.querySelector(".tb-drag").addEventListener("dblclick", toggleMax);

// 标题栏拖动 → 系统原生移动循环（WM_NCLBUTTONDOWN/HTCAPTION）：
// 拖到屏幕顶部=最大化，左/右缘=半屏，系统 Snap 全部生效。
// 捕获阶段拦截并阻断 pywebview easy_drag 的模拟拖动。
document.addEventListener("mousedown", (e) => {
  if (e.button !== 0 || !api) return;
  if (!e.target.closest(".pywebview-drag-region")) return;
  if (e.target.closest("button, a, input, .tb-btns")) return;
  e.preventDefault();
  e.stopPropagation();
  api.native_drag(e.clientX / window.innerWidth);
}, true);

// 系统 Snap / 原生最大化不经过 winMaxed 标志——窗口尺寸变化时回读真实状态
window.addEventListener("resize", async () => {
  if (!api) return;
  const g = await api.win_geom();
  if (g && g.maxed !== undefined) {
    winMaxed = !!g.maxed;
    syncMaxedUI();
  }
});

// ---- 无边框窗口缩放（拖边缘/角落，逻辑像素） ----
const RZ_CURSOR = {
  n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize",
  nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize",
};
let rzDrag = null, rzRaf = 0, rzRect = null;

function rzEnd() {
  rzDrag = null; rzRect = null;
  document.body.classList.remove("resizing");
  document.body.style.cursor = "";
}

document.querySelectorAll(".rz").forEach((el) => {
  el.addEventListener("pointerdown", async (e) => {
    if (!api || winMaxed) return;
    const g = await api.win_geom();
    if (!g || g.maxed) return;
    rzDrag = { dir: el.className.split(" ")[1], sx: e.screenX, sy: e.screenY, g };
    document.body.classList.add("resizing");
    document.body.style.cursor = RZ_CURSOR[rzDrag.dir] || "";
    try { el.setPointerCapture(e.pointerId); } catch (_) {}
    e.preventDefault();
  });
});

document.addEventListener("pointermove", (e) => {
  if (!rzDrag) return;
  const dx = e.screenX - rzDrag.sx, dy = e.screenY - rzDrag.sy;
  const g = rzDrag.g, dir = rzDrag.dir;
  let w = g.w, h = g.h;
  if (dir.indexOf("e") >= 0) w = g.w + dx;
  if (dir.indexOf("s") >= 0) h = g.h + dy;
  if (dir.indexOf("w") >= 0) w = g.w - dx;
  if (dir.indexOf("n") >= 0) h = g.h - dy;
  rzRect = [Math.max(560, Math.round(w)), Math.max(420, Math.round(h)), dir];
  if (!rzRaf) rzRaf = requestAnimationFrame(() => {
    rzRaf = 0;
    if (rzRect) api.win_resize(rzRect[0], rzRect[1], rzRect[2]);
  });
});
document.addEventListener("pointerup", rzEnd);
document.addEventListener("pointercancel", rzEnd);
window.addEventListener("blur", rzEnd);

// 标题栏右键 → 贴边布局（左半屏/右半屏/上半屏/最大化）
document.querySelector("#titlebar").addEventListener("contextmenu", async (e) => {
  if (!api || e.target.closest(".tb-btn")) return;
  e.preventDefault();
  const sw = screen.availWidth, sh = screen.availHeight;
  const sl = screen.availLeft || 0, st = screen.availTop || 0;
  const snap = (x, y, w, h) => {
    api.win_rect(x, y, w, h);
    winMaxed = false; syncMaxedUI();
  };
  showMenu(e.clientX, e.clientY, [
    { label: "左半屏", fn: () => snap(sl, st, sw / 2, sh) },
    { label: "右半屏", fn: () => snap(sl + sw / 2, st, sw / 2, sh) },
    { label: "上半屏", fn: () => snap(sl, st, sw, sh / 2) },
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
