(function() {
    var input = document.getElementById('subdomain');
    var error = document.querySelector('.subdomain-error');
    var current = input.dataset.current;
    var timer;

    input.addEventListener('input', function() {
        clearTimeout(timer);
        var val = input.value.trim().toLowerCase();
        if (!val || val === current) {
            error.hidden = true;
            return;
        }
        timer = setTimeout(function() {
            fetch('/api/check-subdomain?subdomain=' + encodeURIComponent(val))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (input.value.trim().toLowerCase() !== val) return;
                    if (!data.available && data.error) {
                        error.textContent = data.error;
                        error.hidden = false;
                    } else {
                        error.hidden = true;
                    }
                });
        }, 300);
    });
})();
