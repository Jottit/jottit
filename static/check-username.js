(function() {
    var input = document.querySelector('[name=username]');
    var notice = document.querySelector('.auth-subdomain-notice') ||
                 document.querySelector('.subdomain-notice');
    if (!input || !notice) return;

    var script = document.querySelector('script[data-current]');
    var current = script ? script.getAttribute('data-current') : '';
    var submit = input.closest('form').querySelector('[type=submit]');
    var timer;

    function showNotice(msg) {
        notice.textContent = msg;
        notice.style.color = 'var(--error)';
        notice.hidden = false;
        if (submit) submit.disabled = true;
    }
    function hideNotice() {
        notice.textContent = '';
        notice.style.color = '';
        notice.hidden = true;
        if (submit) submit.disabled = false;
    }
    if (!notice.textContent.trim()) hideNotice();

    input.addEventListener('input', function() {
        clearTimeout(timer);
        var val = input.value.trim().toLowerCase();
        if (!val || val === current) { hideNotice(); return; }
        timer = setTimeout(function() {
            fetch('/api/check-username?username=' + encodeURIComponent(val))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (input.value.trim().toLowerCase() !== val) return;
                    if (!data.available && data.error) {
                        showNotice(data.error);
                    } else {
                        hideNotice();
                    }
                });
        }, 300);
    });
})();
