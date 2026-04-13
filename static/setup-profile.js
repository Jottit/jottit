document.addEventListener('DOMContentLoaded', function() {
    var input = document.getElementById('avatar-file');
    var preview = document.getElementById('avatar-preview');
    if (!input || !preview) return;

    preview.addEventListener('click', function() {
        input.click();
    });

    input.addEventListener('change', function() {
        if (!input.files || !input.files[0]) return;
        var reader = new FileReader();
        reader.onload = function(e) {
            preview.innerHTML = '<img src="' + e.target.result + '" class="setup-avatar-img">';
        };
        reader.readAsDataURL(input.files[0]);
    });
});
