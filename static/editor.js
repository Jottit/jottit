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

// Mirrors utils.py slugify: lowercase, strip non [a-z0-9\s-], collapse
// whitespace and hyphens. Used to auto-derive the slug from the title
// on new pages so users see their URL form as they type.
function slugify(s) {
    return s.toLowerCase().trim()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-+|-+$/g, '');
}

function updatePreview() {
    var title = titleInput.value;
    var body = contentInput.value;
    var html = '';
    if (title) html += '<div class="e-content-title"><h1>' + title.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</h1></div>';
    if (body) html += smartypants(marked.parse(body));
    preview.innerHTML = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(html) : html;
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
    } catch (e) { localStorage.removeItem(cursorKey); }
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
    } catch (e) { clearDraft(); }
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
    form.addEventListener('submit', function() {
        var btn = document.querySelector('.btn-publish');
        btn.disabled = true;
        btn.textContent = 'Publishing\u2026';
        clearDraft();
    });
}

var cancelLink = document.querySelector('.editor-actions a');
if (cancelLink) {
    cancelLink.addEventListener('click', clearDraft);
}

// Slug rename popover
var slugChip = document.getElementById('slug-chip');
var slugPopover = document.getElementById('slug-popover');
var slugInput = document.getElementById('slug-input');
var slugForm = document.getElementById('slug-form');
var slugError = document.getElementById('slug-error');
var editorEl = document.querySelector('.editor');
var currentSlug = editorEl ? editorEl.dataset.slug : '';

if (slugChip && slugPopover) {
    var SPECIAL_SLUGS = ['AGENTS'];
    var saveBtn = slugForm.querySelector('button[type="submit"]');

    function validateSlug(value) {
        if (!value) return 'Slug cannot be empty.';
        if (value === currentSlug) return '';
        if (SPECIAL_SLUGS.indexOf(value) !== -1) return '';
        var normalized = value.toLowerCase();
        if (!/^[a-z0-9-]+$/.test(normalized)) return 'Only letters, numbers, and hyphens.';
        if (/\.md$|\.txt$/.test(normalized)) return 'Slug cannot end in .md or .txt.';
        return '';
    }

    var hasSubmitted = false;

    function onSlugInput() {
        var error = validateSlug(slugInput.value.trim());
        saveBtn.disabled = !!error;
        if (hasSubmitted) {
            if (error) {
                slugError.textContent = error;
                slugError.hidden = false;
            } else {
                slugError.hidden = true;
            }
        }
    }

    slugInput.addEventListener('input', onSlugInput);

    slugChip.addEventListener('click', function() {
        hasSubmitted = false;
        slugInput.value = currentSlug;
        slugPopover.hidden = false;
        slugError.hidden = true;
        onSlugInput();
        slugInput.focus();
        slugInput.select();
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !slugPopover.hidden) {
            slugPopover.hidden = true;
        }
    });

    document.addEventListener('mousedown', function(e) {
        if (!slugPopover.hidden && !slugPopover.contains(e.target) && e.target !== slugChip) {
            slugPopover.hidden = true;
        }
    });

    var newPageSlugInput = document.getElementById('new-page-slug');
    var isNewPage = !!newPageSlugInput;
    var slugManuallySet = false;

    // Auto-derive the slug from the title as the user types. Stops once
    // they pick their own slug via the popover below.
    if (isNewPage && titleInput) {
        var autoSlugFromTitle = function() {
            if (slugManuallySet) return;
            var derived = slugify(titleInput.value);
            newPageSlugInput.value = derived;
            currentSlug = derived;
            slugChip.textContent = derived ? '/' + derived : '/set-slug';
        };
        titleInput.addEventListener('input', autoSlugFromTitle);
        autoSlugFromTitle();
    }

    slugForm.addEventListener('submit', function(e) {
        e.preventDefault();
        hasSubmitted = true;
        var rawSlug = slugInput.value.trim();
        var error = validateSlug(rawSlug);
        if (error) {
            slugError.textContent = error;
            slugError.hidden = false;
            return;
        }
        var newSlug = SPECIAL_SLUGS.indexOf(rawSlug) !== -1 ? rawSlug : rawSlug.toLowerCase();
        if (!newSlug || newSlug === currentSlug) {
            slugPopover.hidden = true;
            return;
        }

        if (isNewPage) {
            newPageSlugInput.value = newSlug;
            currentSlug = newSlug;
            slugChip.textContent = '/' + newSlug;
            slugPopover.hidden = true;
            slugError.hidden = true;
            slugManuallySet = true;
            return;
        }

        var csrfToken = slugForm.querySelector('[name="csrf_token"]').value;
        var formData = new FormData();
        formData.append('new_slug', newSlug);
        formData.append('csrf_token', csrfToken);

        var renameUrl = form.action.replace(/\/edit$/, '/rename');

        fetch(renameUrl, {
            method: 'POST',
            body: formData
        }).then(function(response) {
            return response.json().then(function(data) {
                if (response.ok && data.ok) {
                    currentSlug = data.slug;
                    slugChip.textContent = '/' + data.slug;
                    editorEl.dataset.slug = data.slug;
                    form.action = form.action.replace(/\/[^/]+\/edit$/, '/' + data.slug + '/edit');
                    var newPath = window.location.pathname.replace(/\/[^/]+\/edit$/, '/' + data.slug + '/edit');
                    var newStorageKey = 'jottit-draft:' + newPath;
                    var newCursorKey = 'jottit-cursor:' + newPath;
                    var draft = localStorage.getItem(storageKey);
                    if (draft) localStorage.setItem(newStorageKey, draft);
                    var cursor = localStorage.getItem(cursorKey);
                    if (cursor) localStorage.setItem(newCursorKey, cursor);
                    localStorage.removeItem(storageKey);
                    localStorage.removeItem(cursorKey);
                    storageKey = newStorageKey;
                    cursorKey = newCursorKey;
                    history.replaceState(null, '', newPath);
                    slugPopover.hidden = true;
                    slugError.hidden = true;
                } else {
                    slugError.textContent = data.error || 'Rename failed.';
                    slugError.hidden = false;
                }
            });
        }).catch(function() {
            slugError.textContent = 'Network error.';
            slugError.hidden = false;
        });
    });
}
