(function() {
    var updateLink = document.getElementById('avatar-update');
    var avatarInput = document.getElementById('avatar-input');
    if (updateLink && avatarInput) {
        updateLink.addEventListener('click', function(e) {
            e.preventDefault();
            avatarInput.click();
        });
        avatarInput.addEventListener('change', function() {
            if (avatarInput.files.length > 0) {
                avatarInput.form.submit();
            }
        });
    }
})();

(function() {
    var input = document.getElementById('username');
    if (!input) return;
    var error = document.querySelector('.username-error');
    if (!error) return;
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
            fetch('/api/check-username?username=' + encodeURIComponent(val))
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
