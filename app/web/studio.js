/* Writing studio: portable images, templates, recovery and task feedback. */
let defaultDraftDir = '';
let pubStyleRel = null;
let recoveryTimer = null;
let composing = false;
let closing = false;

async function checkPlatformLogin(platform) {
  if (!api) return;
  const result = await api.check_login(platform);
  toast(result.ok ? '已打开登录窗口，请完成登录' : result.msg);
}
const recoverySession = crypto.randomUUID();
const TASK_STATUS = {queued: '排队中', running: '执行中', done: '已完成', partial: '部分失败', error: '失败', attention: '需检查', cancelled: '已取消'};

function escapeHTML(value) {
  const element = document.createElement('span');
  element.textContent = String(value || '');
  return element.innerHTML;
}

function showDeleteUndo(token) {
  toast('文章已移到回收目录', 8000);
  const button = document.createElement('button');
  button.className = 'undo-delete'; button.textContent = '撤销';
  button.onclick = async () => {
    const result = await api.restore_article(token);
    if (result.ok) { await refreshAll(); toast('文章已恢复'); }
    else toast(result.msg);
  };
  $('toast').append(button);
}

function draftSnapshot() {
  return {session: recoverySession, revision: changeRevision, rel: curRel,
    folder: !curRel && curFolder ? curFolder : '',
    title: $('title').value.trim(), author: $('author').value.trim(),
    digest: $('digest').value.trim(), cover_path: $('coverPath').value,
    style: $('styleSel').value, md: getMd()};
}

function scheduleRecovery() {
  clearTimeout(recoveryTimer);
  recoveryTimer = setTimeout(async () => {
    if (!api || !dirty || composing) return;
    try { await api.save_recovery(draftSnapshot()); }
    catch (error) { log('恢复副本保存失败：' + error.message, 'err'); }
  }, 450);
}

async function recoverDraft() {
  const snapshot = await api.get_recovery();
  if (!snapshot || (!snapshot.title && !(snapshot.md || '').trim())) return;
  $('title').value = snapshot.title || '';
  $('author').value = snapshot.author || '';
  $('digest').value = snapshot.digest || '';
  $('coverPath').value = snapshot.cover_path || '';
  if (snapshot.style) $('styleSel').value = snapshot.style;
  const old = snapshot.rel ? await api.load_article(snapshot.rel) : null;
  const base = old ? old.base_dir : defaultDraftDir;
  let md = snapshot.md || '';
  md = md.replace(/(!\[[^\]]*\]\()(<assets\/[^>]+>|assets\/[^)\s]+)([^)]*\))/g,
    (_, prefix, filename, suffix) => prefix + '<' + base.replace(/\\/g, '/') + '/' + filename.replace(/[<>]/g, '') + '>' + suffix);
  setMd(md); curRel = null; setPage('write'); markDirty(true);
  toast('已恢复未完成的内容，并保留原文章', 6000);
}

function setEditorBase(directory) {
  if (!vditor || !directory) return;
  const base = 'file:///' + directory.replace(/\\/g, '/').replace(/^\//, '') + '/';
  vditor.vditor.options.preview.markdown.linkBase = base;
  if (vditor.vditor.lute) vditor.vditor.lute.SetLinkBase(base);
}

function imageMarkdown(result, description = '图片') {
  return '\n![' + description + '](<' + result.src.replace(/\\/g, '/') + '>)\n';
}

async function importPickedImage(path) {
  const epoch = documentEpoch;
  const targetRel = curRel || '';
  $('imageState').textContent = '正在处理图片…';
  try {
    const result = await api.import_image(targetRel, path);
    if (!result.ok) throw new Error(result.msg);
    if (epoch !== documentEpoch) { toast('图片已保存，请在原文章中重新插入'); return; }
    _ins(imageMarkdown(result));
    toast('图片已插入 · ' + result.width + ' × ' + result.height + ' · 原图已保留');
  } catch (error) { toast('图片导入失败：' + error.message, 4500); }
  finally { $('imageState').textContent = ''; }
}

async function importImageFiles(files) {
  if (!api) return;
  const epoch = documentEpoch;
  const targetRel = curRel || '';
  const list = Array.from(files || []).filter(file => file.type.startsWith('image/'));
  if (!list.length) { toast('请拖入图片文件，视频请在视频页选择'); return; }
  for (let index = 0; index < list.length; index++) {
    const file = list[index];
    if (file.size > 40 * 1024 * 1024) { toast(file.name + ' 超过 40 MB'); continue; }
    $('imageState').textContent = '正在导入图片 ' + (index + 1) + '/' + list.length + '…';
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('图片读取失败'));
        reader.readAsDataURL(file);
      });
      if (epoch !== documentEpoch) break;
      const result = await api.save_pasted_image(targetRel, data);
      if (!result.ok) throw new Error(result.msg);
      if (epoch !== documentEpoch) { toast('图片已保存，请在原文章中重新插入'); break; }
      _ins(imageMarkdown(result, file.name.replace(/[\[\]\\\r\n]/g, ' ').replace(/\.[^.]+$/, '') || '图片'));
    } catch (error) { toast('图片导入失败：' + error.message, 4500); }
  }
  $('imageState').textContent = '';
}

$('editorWrap').addEventListener('paste', event => {
  if (!event.clipboardData || !event.clipboardData.files.length) return;
  if (!Array.from(event.clipboardData.files).some(file => file.type.startsWith('image/'))) return;
  event.preventDefault(); event.stopPropagation();
  importImageFiles(event.clipboardData.files);
}, true);
let dragDepth = 0;
$('editorWrap').addEventListener('dragenter', event => {
  if (!event.dataTransfer.types.includes('Files')) return;
  event.preventDefault(); dragDepth++; $('imageDropHint').classList.remove('hidden');
});
$('editorWrap').addEventListener('dragover', event => {
  if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }
});
$('editorWrap').addEventListener('dragleave', () => {
  if (--dragDepth <= 0) { dragDepth = 0; $('imageDropHint').classList.add('hidden'); }
});
$('editorWrap').addEventListener('drop', event => {
  if (!event.dataTransfer.files.length) return;
  event.preventDefault(); event.stopPropagation();
  dragDepth = 0; $('imageDropHint').classList.add('hidden');
  importImageFiles(event.dataTransfer.files);
}, true);

function setSourceMode(enabled) {
  if (sourceMode === enabled) return;
  const md = getMd(); sourceMode = enabled; setMd(md);
  $('sourceEditor').classList.toggle('hidden', !enabled);
  $('vditor').classList.toggle('hidden', enabled);
  $('btnIR').classList.toggle('active', !enabled);
  $('btnSource').classList.toggle('active', enabled);
  $('btnIR').setAttribute('aria-pressed', String(!enabled));
  $('btnSource').setAttribute('aria-pressed', String(enabled));
  if (enabled) $('sourceEditor').focus(); else if (vdReady) vditor.focus();
  updatePreview();
}
$('btnIR').onclick = () => setSourceMode(false);
$('btnSource').onclick = () => setSourceMode(true);
$('sourceEditor').addEventListener('input', () => { markDirty(true); updatePreview(); });
$('sourceEditor').addEventListener('keydown', event => {
  if (event.isComposing) return;
  if (event.key === 'Tab') { event.preventDefault(); _ins('  '); }
  if (event.ctrlKey || event.metaKey) {
    const selected = event.target.value.substring(event.target.selectionStart, event.target.selectionEnd);
    const actions = {b: () => _ins('**' + (selected || '加粗') + '**'), i: () => _ins('*' + (selected || '斜体') + '*'), k: () => _ins('[' + (selected || '链接文字') + '](https://)')};
    const action = actions[event.key.toLowerCase()];
    if (action) { event.preventDefault(); action(); }
  }
});
document.addEventListener('compositionstart', () => { composing = true; clearTimeout(autoSaveTimer); });
document.addEventListener('compositionend', () => { composing = false; if (dirty) { scheduleAutoSave(); scheduleRecovery(); updatePreview(); } });

function toggleFocus() {
  const on = document.body.classList.toggle('focus-writing');
  $('btnFocus').textContent = on ? '退出专注' : '专注';
  $('btnFocus').setAttribute('aria-pressed', String(on)); setPage('write');
}
$('btnFocus').onclick = toggleFocus;
$('btnPreview').onclick = () => {
  const hidden = document.body.classList.toggle('preview-hidden');
  $('btnPreview').setAttribute('aria-pressed', String(!hidden)); updatePreview();
};
$('btnToggleLog').onclick = () => {
  const expanded = $('bottomBar').classList.toggle('expanded');
  $('btnToggleLog').textContent = expanded ? '收起' : '展开';
  $('btnToggleLog').setAttribute('aria-expanded', String(expanded));
};

// Sandbox the article: no scripts, no privileged bridge, and no external frames.
const frame = $('preview');
frame.srcdoc = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: https: http:; style-src 'unsafe-inline';"><style>html{color:#303034;font:15px/1.85 'Segoe UI','Microsoft YaHei',sans-serif;overflow-wrap:anywhere}body{max-width:660px;padding:20px 26px;margin:0 auto}img{max-width:100%;height:auto;cursor:zoom-in;border-radius:6px}p{margin:12px 0}h1,h2,h3{line-height:1.5}pre{overflow:auto;background:#f5f5f7;padding:16px;border-radius:10px}table{border-collapse:collapse;max-width:100%}td,th{border:1px solid #e3e3e8;padding:7px 12px}blockquote{margin:16px 0;padding:4px 16px;border-left:3px solid #d2d2d7;color:#62626a}a{color:#0071e3}::-webkit-scrollbar{width:7px}::-webkit-scrollbar-thumb{background:#d5d5db;border-radius:7px}</style></head><body><p style="color:#9a9aa2">你的内容会在这里实时呈现。</p></body></html>`;
let pendingPreviewHTML = null;
function renderPreviewHTML(html) {
  const doc = frame.contentDocument;
  if (!doc || !doc.body) { pendingPreviewHTML = html; return; }
  const parsed = new DOMParser().parseFromString(html, 'text/html');
  const allowed = new Set('h1 h2 h3 h4 h5 h6 p img ul ol li blockquote code pre table td th thead tbody tfoot tr hr br span div section sup sub strong em b i u s a del details summary'.split(' '));
  parsed.body.querySelectorAll('*').forEach(element => {
    if (!allowed.has(element.tagName.toLowerCase())) { element.remove(); return; }
    Array.from(element.attributes).forEach(attribute => {
      if (!['style', 'src', 'href', 'alt', 'width', 'height', 'colspan', 'rowspan', 'start'].includes(attribute.name)) element.removeAttribute(attribute.name);
    });
    if (element.hasAttribute('src') && !/^(https?:\/\/|data:image\/(png|jpe?g|webp|gif|bmp);base64,)/i.test(element.getAttribute('src'))) element.removeAttribute('src');
    if (element.hasAttribute('href') && !/^(https?:\/\/|mailto:|#)/i.test(element.getAttribute('href'))) element.removeAttribute('href');
  });
  const scrollTop = doc.scrollingElement.scrollTop;
  doc.body.innerHTML = parsed.body.innerHTML || '<p style="color:#9a9aa2">你的内容会在这里实时呈现。</p>';
  doc.scrollingElement.scrollTop = scrollTop;
  doc.body.querySelectorAll('img').forEach(image => {
    image.onload = () => { doc.scrollingElement.scrollTop = scrollTop; };
    image.onerror = () => { image.alt = '图片无法加载 · 请检查链接'; image.style.minHeight = '42px'; };
  });
}
frame.onload = () => {
  const doc = frame.contentDocument;
  if (!doc) return;
  doc.addEventListener('click', event => {
    const image = event.target.closest('img');
    if (image) { showImage(image.src, image.alt); return; }
    if (event.target.closest('a')) { event.preventDefault(); toast('链接在发布后的文章中打开'); }
  });
  if (pendingPreviewHTML !== null) { renderPreviewHTML(pendingPreviewHTML); pendingPreviewHTML = null; }
};
function showImage(src, alt) {
  $('imageView').src = src;
  $('imageViewCaption').textContent = alt || '图片预览';
  $('imageMask').classList.remove('hidden'); focusDialog(document.querySelector('.image-viewer'));
}
function closeImage() { $('imageMask').classList.add('hidden'); $('imageView').removeAttribute('src'); restoreDialogFocus(); }
$('btnCloseImage').onclick = closeImage;
$('imageMask').onclick = event => { if (event.target === $('imageMask')) closeImage(); };

const WILD_EXAMPLE = `# 这工具，怎么比写稿还费劲？

光标还在闪。

你拖进一张图，等了一会儿，正文里什么也没有。于是去找文件夹，复制路径，再回来粘贴。刚才想写的那句话，已经忘了一半。

事情很小。它一天可以发生好几次。

**我在意的是：一篇文章还没写完，注意力已经花在照顾软件上了。**

## 先让一张图顺利落下

选图、粘贴、拖入。动作可以不同，结果应该一样：图出现在光标附近，段落还在原处。

竖着拍的照片，方向要对；透明的图，边缘要干净。原图留着，正文里用适合阅读的尺寸。换个文件夹，图片也跟着走。

这几件事听起来没什么好吹的。我同意。

可只要有一件没做好，写作者就得停下来替它收拾。

> 下次打开，图还在原来的段落里。

## 把那点打断算清楚

试一次就知道。

写两句话，马上切到另一篇稿。再切回来，看刚才的话在不在。保存时继续敲字，看最后几个字有没有漏掉。

再拿一张手机拍的照片拖进去。软件如果要你先旋转、改名、压缩，然后自己管理路径，这一轮折腾会把人从内容里拽出来。

我愿意花时间改一句话。给图片修路径，实在没这个兴致。

### 有些地方，应该安静一点

保存成功，告诉我一声就够了。上传还在排队，让我看得见。哪个平台失败，把原因放在那个平台旁边。

把已经成功的稿子再传一遍，也算一次打断。重试时，先认清失败的是谁。

## 模板里，留一点自己的脾气

开头可以有一个画面，有一句不肯绕弯的话。观点需要事实撑着，配图要让读者看见文字没说清的细节。

有的稿子两节就够了。有的要展开慢慢讲。写到哪里该停，得由内容决定。

纸色、粗线、几笔锈红，让页面带点锋芒。至于正文，真正在意什么，就把那件事说透。

让图回到它该在的段落。

然后把下一句话写完。
`;

const BUILTIN_TEMPLATES = [
  {id: 'blank', name: '空白稿', description: '自由落笔，不预设结构', style: 'blue', md: ''},
  {id: 'wild', name: '旷野 · 野生观察', description: '有现场、有追问、有自己的判断', style: 'wild', md: '[从一个具体画面开场。写清谁在做什么，以及哪个细节让你停了一下。]\n\n[顺着这个细节，说出你真正想追问的问题。]\n\n**[一句明确的判断。读到这里，读者应该知道你要谈什么。]**\n\n## [第一个发现，用人话说]\n\n[把事情摊开：发生了什么？哪里不对劲？用一段具体经历、现象或事实说明。]\n\n[先让读者看见，再给出你的解释。]\n\n## [把最有分量的证据放在这里]\n\n[写下能核对的事实。数据附来源，体验说明场景；不确定的地方直说。]\n\n> [挑出一段值得停下来读的话。也可以删掉这一块。]\n\n[配图可以拖到这一段。图下补一句：读者要看哪个细节？]\n\n## [你的判断，别绕]\n\n[说明你赞成什么、介意什么，以及这个判断适用的条件。不要替所有人下结论。]\n\n[回到开头那个画面，用一个具体动作或变化结束。写到这里就停。]\n'},
  {id: 'essay', name: '深度长文', description: '观点 · 证据 · 分析 · 结论', style: 'blue', md: '> 用一句话说明：这篇文章为什么值得读。\n\n## 从一个具体问题开始\n\n写下你观察到的现象，或一个有代表性的故事。\n\n## 证据告诉了我们什么\n\n- 事实或数据一：\n- 事实或数据二：\n- 信息来源：\n\n## 我的分析\n\n解释事实之间的关系，区分事实与判断。\n\n## 留给读者的一个想法\n\n给出清晰的结论，以及可以采取的下一步。\n'},
  {id: 'review', name: '产品测评', description: '使用场景 · 实测 · 对比 · 建议', style: 'green', md: '> 先说结论：适合谁？解决什么问题？\n\n## 为什么试这款产品\n\n说明真实需求和使用场景。\n\n## 上手与体验\n\n### 最喜欢的细节\n\n### 仍然有待改善\n\n## 关键对比\n\n| 对比维度 | 本产品 | 对比产品 |\n| --- | --- | --- |\n| 使用体验 |  |  |\n| 价格与成本 |  |  |\n| 适用人群 |  |  |\n\n## 购买建议\n\n说明推荐的条件、取舍和测试范围。\n'},
  {id: 'research', name: '研究笔记', description: '问题 · 方法 · 结果 · 局限', style: 'ink', md: '## 研究问题\n\n想弄清楚什么？\n\n## 方法与材料\n\n记录数据来源、实验方法与分析过程。\n\n## 主要发现\n\n1. 发现一：\n2. 发现二：\n\n## 解释与局限\n\n结果支持哪些结论？还有哪些不确定性？\n\n## 下一步\n\n- [ ] 需要验证的问题\n- [ ] 后续实验或阅读\n\n## 参考资料\n\n- 作者，标题，年份，链接。\n'},
  {id: 'tutorial', name: '图文教程', description: '目标 · 准备 · 步骤 · 常见问题', style: 'orange', md: '> 完成这篇教程后，你将能够……\n\n## 开始之前\n\n- 准备的工具或材料：\n- 预计耗时：\n\n## 第一步：\n\n描述具体操作，把截图拖到这一段。\n\n## 第二步：\n\n说明怎么判断操作成功。\n\n## 常见问题\n\n### 遇到问题时怎么处理？\n\n## 检查结果\n\n- [ ] 第一个完成标准\n- [ ] 第二个完成标准\n'},
];
let templates = [], selectedTemplate = null;
async function openTemplates() {
  if (!api) return;
  templates = [...BUILTIN_TEMPLATES, ...await api.list_templates()];
  selectedTemplate = selectedTemplate && templates.find(item => item.id === selectedTemplate.id) || templates.find(item => item.id === 'wild');
  $('templateMask').classList.remove('hidden'); renderTemplates(); focusDialog($('templateSheet'));
}
function renderTemplates() {
  const list = $('templateList'); list.replaceChildren();
  templates.forEach(template => {
    const item = document.createElement('div'); item.className = 'template-row';
    const button = document.createElement('button');
    button.className = 'template-choice' + (selectedTemplate.id === template.id ? ' selected' : '');
    button.setAttribute('aria-pressed', String(selectedTemplate.id === template.id));
    const name = document.createElement('strong'); name.textContent = template.name;
    const description = document.createElement('span'); description.textContent = template.description;
    button.append(name, description); button.onclick = () => { selectedTemplate = template; renderTemplates(); };
    item.append(button);
    if (template.id.startsWith('custom_')) {
      const remove = document.createElement('button'); remove.className = 'template-remove'; remove.textContent = '×'; remove.title = '删除此模板';
      remove.onclick = async () => {
        if (!confirm('删除模板「' + template.name + '」？')) return;
        await api.delete_template(template.id); selectedTemplate = null; await openTemplates();
      };
      item.append(remove);
    }
    list.append(item);
  });
  $('templateDescription').textContent = selectedTemplate.description;
  $('templatePreview').textContent = selectedTemplate.md || '空白页面，留给你的想法。';
  renderTemplateVisual(selectedTemplate);
}
let templatePreviewRevision = 0;
async function renderTemplateVisual(template) {
  const revision = ++templatePreviewRevision;
  const markdown = template.id === 'wild' ? WILD_EXAMPLE : template.md;
  const result = await api.preview(markdown, 'wechat', template.style, '');
  if (revision !== templatePreviewRevision) return;
  const previewFrame = $('templatePreviewFrame');
  previewFrame.srcdoc = frame.srcdoc.split('<body>')[0] + '<body>' + result.html + '</body></html>';
}
$('btnTemplateVisual').onclick = () => setTemplatePreviewMode(false);
$('btnTemplateOutline').onclick = () => setTemplatePreviewMode(true);
function setTemplatePreviewMode(outline) {
  $('templatePreviewFrame').classList.toggle('hidden', outline);
  $('templatePreview').classList.toggle('hidden', !outline);
  $('btnTemplateVisual').classList.toggle('active', !outline);
  $('btnTemplateOutline').classList.toggle('active', outline);
}
function closeTemplates() { $('templateMask').classList.add('hidden'); restoreDialogFocus(); }
$('btnTemplates').onclick = openTemplates;
$('btnCloseTemplates').onclick = closeTemplates;
$('templateMask').onclick = event => { if (event.target === $('templateMask')) closeTemplates(); };
$('btnUseTemplate').onclick = async () => { if (await newArticle(selectedTemplate)) closeTemplates(); };
$('btnSaveTemplate').onclick = async () => {
  if (!getMd().trim()) { toast('先写好正文，再保存为模板'); return; }
  const name = $('templateName').value.trim();
  if (!name) { $('templateName').focus(); toast('请填写模板名称'); return; }
  const result = await api.save_template(name, getMd(), $('styleSel').value, curRel || '');
  if (!result.ok) { toast(result.msg); return; }
  selectedTemplate = result.template; await openTemplates(); toast('已保存到我的模板');
};

let taskCache = [], taskCacheAt = 0, taskRequest = null;
async function getTasks() {
  if (!api) return [];
  if (taskRequest) return taskRequest;
  if (Date.now() - taskCacheAt < 800) return taskCache;
  taskRequest = api.list_jobs().then(value => { taskCache = value || []; taskCacheAt = Date.now(); return taskCache; }).finally(() => { taskRequest = null; });
  return taskRequest;
}
async function refreshTaskViews() {
  taskCacheAt = 0;
  const tasks = await getTasks();
  const active = tasks.filter(task => ['running', 'queued'].includes(task.status));
  $('progressBar').classList.toggle('on', active.length > 0);
  $('stTask').textContent = active.length ? active.filter(task => task.status === 'running').length + ' 执行 · ' + active.filter(task => task.status === 'queued').length + ' 排队' : '';
  await Promise.all([renderTasks(), renderHistory(), renderVideoHistory()]);
}
function addTaskActions(item, task) {
  const container = document.createElement('span'); container.className = 'task-actions';
  const add = (text, run) => {
    const button = document.createElement('button'); button.className = 'btn small'; button.textContent = text;
    button.onclick = async event => {
      event.stopPropagation(); button.disabled = true;
      try { const result = await run(); toast(result.ok ? text === '重试失败平台' ? '失败平台已重新排队' : '已取消排队任务' : result.msg); await refreshTaskViews(); }
      catch (error) { toast(error.message); }
      finally { button.disabled = false; }
    };
    container.append(button);
  };
  if (task.can_retry) add('重试失败平台', () => api.retry_job(task.id));
  if (task.status === 'queued') add('取消', () => api.cancel_job(task.id));
  item.append(container);
}
async function submitUpload(buttonId, action) {
  const button = $(buttonId); button.disabled = true; button.classList.add('is-loading');
  try {
    const result = await action();
    if (!result || !result.ok) throw new Error(result && result.msg || '任务未提交');
    toast('已加入上传队列，可以继续写作'); await refreshTaskViews();
  } catch (error) { toast('提交失败：' + error.message, 5000); }
  finally { button.disabled = false; button.classList.remove('is-loading'); }
}

let eventPolling = false;
function startEventPolling() {
  setInterval(async () => {
    if (!api || eventPolling) return;
    eventPolling = true;
    try { (await api.drain_events()).forEach(window.onBackendEvent); }
    catch (error) { /* Window may already be closing. */ }
    finally { eventPolling = false; }
  }, 350);
  let previousSignature = '';
  setInterval(async () => {
    if (!api || document.hidden) return;
    const tasks = await getTasks();
    const signature = JSON.stringify(tasks.map(task => [task.id, task.status, task.logs.length]));
    if (signature !== previousSignature) { previousSignature = signature; await refreshTaskViews(); }
  }, 1500);
  setInterval(() => { if (dirty && !composing && !saveInFlight && !saveError) saveArticle(true, true); }, 10000);
}
async function prepareToClose() {
  if (!api || closing) return;
  closing = true;
  try {
    if (!await flushDraft()) return;
    const tasks = await api.list_jobs();
    if (tasks.some(task => ['running', 'queued'].includes(task.status)) && !confirm('还有上传或备份任务。关闭后任务会中断，仍要退出吗？')) return;
    await api.win_close();
  } finally { closing = false; }
}

const focusStack = [];
function focusDialog(dialog) {
  if (focusStack.at(-1)?.dialog === dialog) return;
  focusStack.push({dialog, previous: document.activeElement});
  const focusable = dialog.querySelector('button, input, textarea, select, [tabindex="0"]');
  if (focusable) focusable.focus();
}
function restoreDialogFocus() { const saved = focusStack.pop(); if (saved?.previous?.isConnected) saved.previous.focus(); }
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    if (!$('imageMask').classList.contains('hidden')) closeImage();
    else if (!$('templateMask').classList.contains('hidden')) closeTemplates();
    else if (document.body.classList.contains('focus-writing')) toggleFocus();
    hideMenu();
  }
  if (event.key === 'Tab' && focusStack.length) {
    const dialog = focusStack.at(-1).dialog;
    const controls = Array.from(dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex="0"]')).filter(control => control.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'f') { event.preventDefault(); toggleFocus(); }
  if ((event.ctrlKey || event.metaKey) && event.altKey && event.key.toLowerCase() === 'm') { event.preventDefault(); setSourceMode(!sourceMode); }
});
window.addEventListener('unhandledrejection', event => { toast('操作未完成：' + (event.reason?.message || '请稍后重试'), 5000); });
