/* Formula source stays editable; KaTeX font size never depends on expression width. */
let formulaContext = null;
let formulaDisplay = true;
let formulaValid = false;
let formulaTimer = null;

function formulaNodeFrom(element) {
  return element?.closest('[data-math]') || element?.closest('.vditor-ir__node')?.querySelector(
    'code[data-type="math-block"], code[data-type="math-inline"]');
}

function commitFormulaUndo() {
  // Formula changes are one edit, rather than the editor's 800 ms typing batch.
  const state = vditor.vditor;
  clearTimeout(state.ir.processTimeoutId);
  state.undo.addToUndoStack(state);
}

function normalizeFormula(value) {
  let source = String(value || '').trim();
  if (source.startsWith('$$') && source.endsWith('$$')) source = source.slice(2, -2);
  else if (source.startsWith('$') && source.endsWith('$')) source = source.slice(1, -1);
  return source.trim();
}

function sourceFormulaRanges(text) {
  const code = [];
  for (const match of text.matchAll(/```[^\n]*\n[\s\S]*?```|~~~[^\n]*\n[\s\S]*?~~~|`[^`\n]*`/g)) code.push([match.index, match.index + match[0].length]);
  const pattern = /(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<![\\$])\$(?!\$)(?:\\.|[^$\\\n])+?(?<!\s)\$(?!\$)/g;
  const ranges = [];
  for (const match of text.matchAll(pattern)) {
    const from = match.index, to = from + match[0].length;
    if (!code.some(([a,b]) => from >= a && from < b)) ranges.push(
      {start:from, end:to, tex:normalizeFormula(match[0]), display:match[0].startsWith('$$')});
  }
  return ranges;
}

function formulaWrappers() {
  return Array.from($('vditor').querySelectorAll('.vditor-ir__node')).filter(node =>
    node.querySelector('code[data-type="math-block"], code[data-type="math-inline"]'));
}

function sourceFormulaAt(text, start, end) {
  return sourceFormulaRanges(text).find(range => range.start <= start && range.end >= end) || null;
}

function openFormula(display=true, element=null) {
  if (page !== 'write') return;
  const context = {epoch:documentEpoch, mode:sourceMode, range:null, selection:null, replacing:false};
  let tex = '';
  if (sourceMode) {
    const editor = $('sourceEditor');
    let start = editor.selectionStart, end = editor.selectionEnd;
    const existing = sourceFormulaAt(editor.value, start, end);
    if (existing) {
      ({start, end, tex, display} = existing);
      context.replacing = true;
    } else tex = normalizeFormula(editor.value.slice(start, end));
    context.selection = {start, end};
  } else {
    const selection = window.getSelection();
    const anchor = selection.anchorNode?.nodeType === Node.ELEMENT_NODE ? selection.anchorNode : selection.anchorNode?.parentElement;
    const math = element || ($('vditor').contains(anchor) ? formulaNodeFrom(anchor) : null);
    if (math) {
      const wrapper = math.closest('.vditor-ir__node');
      if (wrapper) {
        context.range = document.createRange(); context.range.selectNode(wrapper);
        context.replacing = true;
        context.markdown = getMd();
        context.formulaIndex = formulaWrappers().indexOf(wrapper);
        context.sourceRange = sourceFormulaRanges(context.markdown)[context.formulaIndex];
        if (!context.sourceRange) { toast('无法定位公式源码，请切换到 Markdown 源码编辑'); return; }
        tex = math.getAttribute('data-math') || math.textContent;
        display = math.getAttribute('data-type') === 'math-block';
      }
    } else if (selection.rangeCount && $('vditor').contains(selection.anchorNode)) {
      context.range = selection.getRangeAt(0).cloneRange(); tex = normalizeFormula(selection.toString());
    }
  }
  if (!sourceMode) commitFormulaUndo();
  formulaContext = context; formulaDisplay = display;
  $('formulaSource').value = tex || (display ? '\\int_0^1 x^2\\,dx' : 'E=mc^2');
  $('btnApplyFormula').textContent = context.replacing ? '更新公式' : '插入公式';
  $('formulaMask').classList.remove('hidden');
  focusDialog($('formulaSheet'));
  $('formulaSource').focus(); $('formulaSource').select();
  renderFormulaEditor();
}

function renderFormulaEditor() {
  clearTimeout(formulaTimer);
  const source = normalizeFormula($('formulaSource').value);
  const target = $('formulaLivePreview');
  const error = $('formulaError');
  target.style.fontSize = (formulaDisplay ? 18 : 16) + 'px';
  $('formulaFontHint').textContent = (formulaDisplay ? '18' : '16') + ' px · 字号保持一致';
  $('btnFormulaInline').classList.toggle('active', !formulaDisplay);
  $('btnFormulaBlock').classList.toggle('active', formulaDisplay);
  formulaValid = false;
  try {
    if (!source) throw new Error('请输入公式');
    if (source.length > 16000) throw new Error('公式过长，请拆分为多个公式');
    katex.render(source, target, {displayMode:formulaDisplay, output:'htmlAndMathml',
      throwOnError:true, strict:false, trust:false, maxSize:20, maxExpand:1000});
    formulaValid = true; error.textContent = '';
  } catch (failure) {
    error.textContent = failure.message.replace(/^KaTeX parse error:\s*/, '');
    target.textContent = '补全公式后，这里会显示排版效果。';
  }
  $('btnApplyFormula').disabled = !formulaValid;
  $('formulaWarning').textContent = formulaValid && Array.from(target.querySelectorAll('.base')).some(
    part => part.getBoundingClientRect().width > 314)
    ? '这个分式或括号组较宽，投递前请拆分或用多行结构，避免平台缩小字号。' : '';
}

function closeFormula(restore=true) {
  clearTimeout(formulaTimer);
  $('formulaMask').classList.add('hidden');
  restoreDialogFocus();
  if (restore && formulaContext && formulaContext.epoch === documentEpoch) restoreFormulaSelection();
}

function restoreFormulaSelection() {
  const context = formulaContext;
  if (context.mode) {
    const editor = $('sourceEditor'); editor.focus();
    editor.setSelectionRange(context.selection.start, context.selection.end);
  } else {
    if (context.range && context.range.startContainer.isConnected) {
      const editable = $('vditor').querySelector('[contenteditable="true"]'); editable?.focus();
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(context.range);
    } else vditor.focus();
  }
}

function applyFormula() {
  renderFormulaEditor();
  if (!formulaValid || !formulaContext) return;
  if (formulaContext.epoch !== documentEpoch || formulaContext.mode !== sourceMode) {
    toast('当前文章已切换，请重新选择插入位置'); closeFormula(false); return;
  }
  const tex = normalizeFormula($('formulaSource').value);
  let text;
  if (formulaDisplay) {
    text = '$$\n' + tex + '\n$$';
    if (!formulaContext.replacing || formulaContext.mode) text = '\n\n' + text + '\n\n';
  } else text = '$' + tex + '$';
  const context = formulaContext;
  if (!context.mode && context.replacing) {
    if (getMd() !== context.markdown) { toast('正文已变化，请重新打开公式'); closeFormula(false); return; }
    closeFormula(false);
    setMd(context.markdown.slice(0, context.sourceRange.start) + text + context.markdown.slice(context.sourceRange.end));
    const wrapper = formulaWrappers()[context.formulaIndex];
    vditor.focus();
    if (wrapper) {
      const range = document.createRange(); range.setStartAfter(wrapper); range.collapse(true);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    }
  } else {
    closeFormula(false); restoreFormulaSelection();
    if (context.mode) _ins(text);
    else vditor.insertMD(text);
  }
  if (!context.mode) commitFormulaUndo();
  markDirty(true); updatePreview();
}

const FORMULA_SNIPPETS = [
  ['分式', '\\frac{a}{b}'], ['上下标', 'x_{i}^{2}'], ['积分', '\\int_{a}^{b} f(x)\\,dx'],
  ['求和', '\\sum_{i=1}^{n} x_i'],
  ['多行对齐', '\\begin{aligned}\na &= b+c \\\\\n  &= d+e\n\\end{aligned}'],
  ['矩阵', '\\begin{pmatrix}\na & b \\\\\nc & d\n\\end{pmatrix}'],
  ['分段函数', '\\begin{cases}\nx^2, & x \\ge 0 \\\\\n-x, & x < 0\n\\end{cases}']
];
FORMULA_SNIPPETS.forEach(([label, snippet]) => {
  const button = document.createElement('button'); button.textContent = label;
  button.onmousedown = event => event.preventDefault();
  button.onclick = () => {
    const editor = $('formulaSource'); editor.focus();
    if (!document.execCommand('insertText', false, snippet)) editor.setRangeText(snippet, editor.selectionStart, editor.selectionEnd, 'end');
    if (label === '多行对齐' || label === '矩阵' || label === '分段函数') formulaDisplay = true;
    renderFormulaEditor();
  };
  $('formulaSnippets').append(button);
});
$('formulaSource').addEventListener('input', event => {
  formulaValid = false; $('btnApplyFormula').disabled = true;
  clearTimeout(formulaTimer);
  if (!event.isComposing) formulaTimer = setTimeout(renderFormulaEditor, 100);
});
$('formulaSource').addEventListener('compositionend', renderFormulaEditor);
$('formulaSource').addEventListener('keydown', event => {
  if (event.key === 'Tab') {
    event.preventDefault(); document.execCommand('insertText', false, '  ');
  }
});
$('btnFormulaInline').onclick = () => { formulaDisplay = false; renderFormulaEditor(); };
$('btnFormulaBlock').onclick = () => { formulaDisplay = true; renderFormulaEditor(); };
$('btnApplyFormula').onclick = applyFormula;
$('btnCloseFormula').onclick = () => closeFormula();
$('formulaMask').onclick = event => { if (event.target === $('formulaMask')) closeFormula(); };
$('vditor').addEventListener('dblclick', event => {
  const math = formulaNodeFrom(event.target);
  if (math) { event.preventDefault(); event.stopImmediatePropagation(); openFormula(true, math); }
}, true);
document.addEventListener('keydown', event => {
  if (event.isComposing) return;
  if (!$('formulaMask').classList.contains('hidden')) {
    if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); closeFormula(); }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); event.stopImmediatePropagation(); applyFormula(); }
  } else if (page === 'write' && (event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'm') {
    event.preventDefault(); event.stopImmediatePropagation(); openFormula(false);
  }
}, true);
