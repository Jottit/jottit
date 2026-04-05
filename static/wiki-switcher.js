(function() {
    var btn = document.querySelector('.wiki-switcher-btn');
    if (!btn) return;
    var dropdown = btn.nextElementSibling;

    btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var open = !dropdown.hidden;
        dropdown.hidden = open;
        btn.setAttribute('aria-expanded', String(!open));
    });

    document.addEventListener('click', function() {
        dropdown.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
    });

    dropdown.addEventListener('click', function(e) {
        e.stopPropagation();
    });
})();
