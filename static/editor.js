var titleInput = document.querySelector('.editor-title');
var contentInput = document.querySelector('.editor-content');
var preview = document.getElementById('preview');

function smartypants(html) {
    var parts = html.split(/(<[^>]*>)/);
    for (var i = 0; i < parts.length; i++) {
        if (parts[i].charAt(0) === '<') continue;
        parts[i] = parts[i]
            .replace(/---/g, '\u2014')
            .replace(/--/g, '\u2013')
            .replace(/\.\.\./g, '\u2026')
            .replace(/(^|[-\u2014/(\[{&\s])&#39;/g, '$1\u2018')
            .replace(/&#39;/g, '\u2019')
            .replace(/(^|[-\u2014/(\[{\u2018&\s])&quot;/g, '$1\u201C')
            .replace(/&quot;/g, '\u201D')
            .replace(/(^|[-\u2014/(\[{"\s])'/g, '$1\u2018')
            .replace(/'/g, '\u2019')
            .replace(/(^|[-\u2014/(\[{\u2018\s])"/g, '$1\u201C')
            .replace(/"/g, '\u201D');
    }
    return parts.join('');
}

function updatePreview() {
    var title = titleInput.value;
    var body = contentInput.value;
    var html = '';
    if (title) html += '<h1>' + title.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</h1>';
    if (body) html += smartypants(marked.parse(body));
    preview.innerHTML = html;
}

var storageKey = 'jottit-draft:' + window.location.pathname;
var cursorKey = 'jottit-cursor:' + window.location.pathname;

var serverTitle = titleInput.value;
var serverContent = contentInput.value;

function saveDraft() {
    localStorage.setItem(storageKey, JSON.stringify({
        title: titleInput.value,
        content: contentInput.value,
        serverTitle: serverTitle,
        serverContent: serverContent
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
        var draftMatchesServer = draft.serverTitle === serverTitle
            && draft.serverContent === serverContent;
        if (draftMatchesServer || (!serverTitle && !serverContent)) {
            if (draft.title !== undefined) titleInput.value = draft.title;
            if (draft.content !== undefined) contentInput.value = draft.content;
        } else {
            clearDraft();
        }
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
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        var btn = document.querySelector('.btn-publish');
        btn.disabled = true;
        btn.textContent = 'Publishing\u2026';

        function resetButton() {
            btn.disabled = false;
            btn.textContent = 'Publish';
        }

        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            redirect: 'follow'
        }).then(function(response) {
            if (response.ok) {
                clearDraft();
                window.location.href = response.url;
            } else {
                resetButton();
            }
        }).catch(resetButton);
    });
}

var cancelLink = document.querySelector('.editor-actions a');
if (cancelLink) {
    cancelLink.addEventListener('click', clearDraft);
}
