document.addEventListener('DOMContentLoaded', function() {
    var input = document.getElementById('avatar-file');
    var preview = document.getElementById('avatar-preview');
    if (!input || !preview) return;

    preview.addEventListener('click', function() {
        input.click();
    });

    input.addEventListener('change', function() {
        if (!input.files || !input.files[0]) return;
        var url = URL.createObjectURL(input.files[0]);
        preview.innerHTML = '<img src="' + url + '" class="setup-avatar-img">';
    });
});
