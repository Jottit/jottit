document.addEventListener('DOMContentLoaded', function() {
    var btn = document.getElementById('mcp-config-btn');
    var output = document.getElementById('mcp-config-output');
    var text = document.getElementById('mcp-config-text');
    var copyBtn = document.getElementById('mcp-copy-btn');
    if (!btn) return;
    var csrf = btn.getAttribute('data-csrf');
    btn.addEventListener('click', function() {
        btn.textContent = 'Loading...';
        fetch('/setup/mcp-config', {method: 'POST', headers: {'X-CSRFToken': csrf}})
            .then(function(r) { return r.json(); })
            .then(function(data) {
                text.textContent = data.config_text;
                output.classList.remove('setup-hidden');
                btn.style.display = 'none';
                if (navigator.clipboard) {
                    navigator.clipboard.writeText(data.config_text);
                    copyBtn.title = 'Copied!';
                    setTimeout(function() { copyBtn.title = 'Copy to clipboard'; }, 2000);
                }
            });
    });
    copyBtn.addEventListener('click', function() {
        navigator.clipboard.writeText(text.textContent);
        copyBtn.title = 'Copied!';
        setTimeout(function() { copyBtn.title = 'Copy to clipboard'; }, 2000);
    });
});
