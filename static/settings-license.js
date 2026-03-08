(function() {
    var select = document.getElementById('license');
    var csrf = document.querySelector('input[name="csrf_token"]');
    if (!select) return;

    select.addEventListener('change', function() {
        fetch('/settings/license', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrf ? csrf.value : '',
                'X-Requested-With': 'fetch'
            },
            body: 'license=' + encodeURIComponent(select.value)
        });
    });
})();
