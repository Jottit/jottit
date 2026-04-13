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
            });
    });
    copyBtn.addEventListener('click', function() {
        navigator.clipboard.writeText(text.textContent).then(function() {
            copyBtn.textContent = 'Copied!';
            setTimeout(function() { copyBtn.textContent = 'Copy prompt'; }, 2000);
        });
    });
});
