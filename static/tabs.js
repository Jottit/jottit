(function() {
    var container = document.querySelector('.tabs-container');
    if (!container) return;

    var tabs = container.querySelector('.tabs');
    var leftBtn = container.querySelector('.tabs-fade--left');
    var rightBtn = container.querySelector('.tabs-fade--right');

    function update() {
        var scrollLeft = tabs.scrollLeft;
        var maxScroll = tabs.scrollWidth - tabs.clientWidth;
        container.classList.toggle('can-scroll-start', scrollLeft > 1);
        container.classList.toggle('can-scroll-end', scrollLeft < maxScroll - 1);
    }

    tabs.addEventListener('scroll', update);
    update();

    leftBtn.addEventListener('click', function() {
        tabs.scrollBy({ left: -120, behavior: 'smooth' });
    });

    rightBtn.addEventListener('click', function() {
        tabs.scrollBy({ left: 120, behavior: 'smooth' });
    });
})();
