(function() {
    var select = document.querySelector('.listing-select');
    var csrf = document.querySelector('input[name="csrf_token"]');
    if (!select) return;
    select.addEventListener('change', function() {
        var slug = select.getAttribute('data-slug');
        fetch('/' + slug + '/listing', {
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
