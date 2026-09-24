(() => {
    const layout = document.querySelector('.article-screen-layout');
    if (!layout) return;

    const headings = [...layout.querySelectorAll('h2[data-screen]')];
    const images = [...layout.querySelectorAll('.article-screen-phone-image')];
    let active = 0;
    let scheduled = false;

    function updateScreen() {
        scheduled = false;
        const activationLine = Math.max(112, window.innerHeight * 0.28);
        let next = 0;
        headings.forEach((heading, index) => {
            if (heading.getBoundingClientRect().top <= activationLine) next = index;
        });
        if (next === active) return;
        images[active].classList.remove('is-active');
        images[active].setAttribute('aria-hidden', 'true');
        images[next].classList.add('is-active');
        images[next].setAttribute('aria-hidden', 'false');
        active = next;
    }

    function scheduleUpdate() {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(updateScreen);
    }

    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);
    window.addEventListener('hashchange', scheduleUpdate);
    scheduleUpdate();

    const dialog = document.querySelector('.article-screen-dialog');
    const largeImage = dialog.querySelector('img');
    let opener = null;
    layout.querySelectorAll('.article-screen-link').forEach((link) => {
        link.addEventListener('click', (event) => {
            event.preventDefault();
            opener = link;
            largeImage.src = link.href;
            largeImage.alt = link.querySelector('img').alt;
            largeImage.width = Number(link.dataset.zoomWidth);
            largeImage.height = Number(link.dataset.zoomHeight);
            dialog.showModal();
            dialog.querySelector('.article-screen-close').focus();
        });
    });
    dialog.querySelector('.article-screen-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
        if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', () => {
        if (opener) opener.focus();
        largeImage.removeAttribute('src');
    });
})();
