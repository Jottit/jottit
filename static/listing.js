(function() {
    var form = document.querySelector('.listing-form');
    var select = document.querySelector('.listing-select');
    var csrf = document.querySelector('input[name="csrf_token"]');
    if (!select || !form) return;
    select.addEventListener('change', function() {
        fetch(form.action, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrf ? csrf.value : '',
                'X-Requested-With': 'fetch'
            },
            body: 'listing=' + encodeURIComponent(select.value)
        });
    });
})();
