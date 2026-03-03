(function() {
    var digits = document.querySelectorAll('.auth-code-digit');
    var hidden = document.getElementById('code-value');

    var form = document.querySelector('.auth-form');

    function syncHidden() {
        var code = '';
        digits.forEach(function(d) { code += d.value; });
        hidden.value = code;
        if (code.length === 6) {
            form.submit();
        }
    }

    digits.forEach(function(input, i) {
        input.addEventListener('input', function() {
            syncHidden();
            if (input.value && i < digits.length - 1) {
                digits[i + 1].focus();
            }
        });

        input.addEventListener('keydown', function(e) {
            if (e.key === 'Backspace' && !input.value && i > 0) {
                digits[i - 1].focus();
            }
        });

        input.addEventListener('paste', function(e) {
            e.preventDefault();
            var text = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '');
            for (var j = 0; j < digits.length; j++) {
                digits[j].value = text[j] || '';
            }
            syncHidden();
            var next = Math.min(text.length, digits.length - 1);
            digits[next].focus();
        });
    });
})();
