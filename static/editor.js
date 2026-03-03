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

titleInput.addEventListener('input', updatePreview);
contentInput.addEventListener('input', updatePreview);
updatePreview();
