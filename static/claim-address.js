(function() {
    var input = document.querySelector('[name=username]');
    var notice = document.querySelector('.auth-subdomain-notice');
    var timer;
    input.focus();
    function showNotice(msg) {
        notice.textContent = msg;
        notice.style.display = '';
    }
    function hideNotice() {
        notice.textContent = '';
        notice.style.display = 'none';
    }
    if (!notice.textContent.trim()) hideNotice();
    input.addEventListener('input', function() {
        clearTimeout(timer);
        var val = input.value.trim().toLowerCase();
        if (!val) { hideNotice(); return; }
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
