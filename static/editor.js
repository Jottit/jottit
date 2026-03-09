var titleInput = document.querySelector('.editor-title');
var contentInput = document.querySelector('.editor-content');
var preview = document.getElementById('preview');
var siteSlug = document.querySelector('.editor').dataset.slug;

function processWikilinks(text) {
    return text.replace(/\[\[([^\[\]]+)\]\]/g, function(match, name) {
        name = name.trim();
        if (!name) return match;
        var slug = name.toLowerCase().replace(/[^a-z0-9\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
        if (!slug) return match;
        var display = name.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        return '<a href="/' + siteSlug + '/' + slug + '">' + display + '</a>';
    });
}

function updatePreview() {
    var title = titleInput.value;
    var body = contentInput.value;
    var html = '';
    if (title) html += '<h1>' + title.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</h1>';
    if (body) html += marked.parse(processWikilinks(body));
    preview.innerHTML = html;
}

var storageKey = 'jottit-draft:' + window.location.pathname;
var cursorKey = 'jottit-cursor:' + window.location.pathname;

function saveDraft() {
    localStorage.setItem(storageKey, JSON.stringify({
        title: titleInput.value,
        content: contentInput.value
    }));
}

function clearDraft() {
    localStorage.removeItem(storageKey);
}

function saveCursor() {
    var el = document.activeElement === titleInput ? titleInput : contentInput;
    localStorage.setItem(cursorKey, JSON.stringify({
        field: el === titleInput ? 'title' : 'content',
        start: el.selectionStart,
        end: el.selectionEnd
    }));
}

function restoreCursor() {
    var raw = localStorage.getItem(cursorKey);
    if (!raw) return;
    try {
        var pos = JSON.parse(raw);
        var el = pos.field === 'title' ? titleInput : contentInput;
        el.focus();
        el.setSelectionRange(pos.start, pos.end);
        el.blur();
        el.focus();
    } catch (e) {}
}

var saved = localStorage.getItem(storageKey);
if (saved) {
    try {
        var draft = JSON.parse(saved);
        if (draft.title !== undefined) titleInput.value = draft.title;
        if (draft.content !== undefined) contentInput.value = draft.content;
    } catch (e) {}
}

function onInput() {
    updatePreview();
    saveDraft();
    saveCursor();
}

[titleInput, contentInput].forEach(function(el) {
    el.addEventListener('input', onInput);
    el.addEventListener('keyup', saveCursor);
    el.addEventListener('click', saveCursor);
});

var previewPane = document.querySelector('.editor-preview');
function syncPreviewScroll() {
    if (!previewPane) return;
    var max = contentInput.scrollHeight - contentInput.clientHeight;
    var pct = max > 0 ? contentInput.scrollTop / max : 0;
    var previewMax = previewPane.scrollHeight - previewPane.clientHeight;
    previewPane.scrollTop = pct * previewMax;
}

contentInput.addEventListener('scroll', syncPreviewScroll);

updatePreview();
if (previewPane) previewPane.style.scrollBehavior = 'smooth';
restoreCursor();
syncPreviewScroll();
setTimeout(function() {
    if (previewPane) previewPane.style.scrollBehavior = '';
}, 500);

var form = document.querySelector('.editor-form');
if (form) {
    form.addEventListener('submit', clearDraft);
}

var cancelLink = document.querySelector('.editor-actions a');
if (cancelLink) {
    cancelLink.addEventListener('click', clearDraft);
}
