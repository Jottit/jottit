(function() {
    var updateLink = document.getElementById('avatar-update');
    var avatarInput = document.getElementById('avatar-input');
    var avatarPlaceholder = document.querySelector('.settings-avatar-placeholder');
    if (updateLink && avatarInput) {
        updateLink.addEventListener('click', function(e) {
            e.preventDefault();
            avatarInput.click();
        });
        if (avatarPlaceholder) {
            avatarPlaceholder.classList.add('clickable');
            avatarPlaceholder.addEventListener('click', function() {
                avatarInput.click();
            });
        }
        avatarInput.addEventListener('change', function() {
            if (avatarInput.files.length > 0) {
                avatarInput.form.submit();
            }
        });
    }
})();

(function() {
    var form = document.querySelector('form[action="/settings/profile"]');
    if (!form) return;
    var csrf = form.querySelector('input[name="csrf_token"]');
    var dirty = false;

    function save() {
        if (!dirty) return;
        dirty = false;
        var name = form.querySelector('#name');
        var bio = form.querySelector('#bio');
        fetch('/settings/profile', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf ? csrf.value : ''
            },
            body: JSON.stringify({
                name: name ? name.value : '',
                bio: bio ? bio.value : ''
            })
        });
    }

    form.addEventListener('input', function() {
        dirty = true;
    });

    form.querySelectorAll('input, textarea').forEach(function(el) {
        el.addEventListener('blur', save);
    });

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        dirty = true;
        save();
    });
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
