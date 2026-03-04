var btn = document.getElementById("delete-page-btn");
if (btn) {
    btn.addEventListener("click", function (e) {
        if (!confirm("Delete this page?")) {
            e.preventDefault();
        }
    });
}
