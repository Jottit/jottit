(function() {
    var input = document.querySelector('[name=username]');
    var notice = document.querySelector('.auth-subdomain-notice') ||
                 document.querySelector('.subdomain-notice');
    if (!input || !notice) return;

    var script = document.querySelector('script[data-current]');
    var current = script ? script.getAttribute('data-current') : '';
    var timer;

    function showNotice(msg) {
        notice.textContent = msg;
        notice.hidden = false;
    }
    function hideNotice() {
        notice.textContent = '';
        notice.hidden = true;
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
