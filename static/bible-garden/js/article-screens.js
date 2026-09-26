(() => {
    const layout = document.querySelector('.article-screen-layout');
    if (!layout) return;

    const headings = [...layout.querySelectorAll('h2[data-screen]')];
    const images = [...layout.querySelectorAll('.article-screen-phone-image')];
    const desktop = window.matchMedia('(min-width: 1024px)');
    let active = -1;
    let requested = -1;
    let requestVersion = 0;
    let scheduled = false;

    function preload(index) {
        if (index >= images.length) return;
        const image = images[index];
        if (!image.hasAttribute('src')) image.src = image.dataset.src;
    }

    function showScreen(index) {
        if (index === active) {
            if (requested !== -1) {
                requestVersion += 1;
                requested = -1;
            }
            return;
        }
        if (index === requested) return;
        requested = index;
        const version = ++requestVersion;
        preload(index);
        images[index].decode().then(() => {
            if (version !== requestVersion || !desktop.matches) return;
            if (active >= 0) {
                images[active].classList.remove('is-active');
                images[active].setAttribute('aria-hidden', 'true');
            }
            images[index].classList.add('is-active');
            images[index].setAttribute('aria-hidden', 'false');
            active = index;
            requested = -1;
            preload(index + 1);
        }).catch((error) => {
            if (version !== requestVersion) return;
            requested = -1;
            console.error(`Unable to load article screen ${images[index].dataset.src}`, error);
        });
    }

    function updateScreen() {
        scheduled = false;
        if (!desktop.matches) return;
        const activationLine = Math.max(112, window.innerHeight * 0.28);
        let next = 0;
        headings.forEach((heading, index) => {
            if (heading.getBoundingClientRect().top <= activationLine) next = index;
        });
        showScreen(next);
    }

    function scheduleUpdate() {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(updateScreen);
    }

    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);
    window.addEventListener('hashchange', scheduleUpdate);
    desktop.addEventListener('change', () => {
        requestVersion += 1;
        requested = -1;
        scheduleUpdate();
    });
    scheduleUpdate();

    const dialog = document.querySelector('.article-screen-dialog');
    const largeImage = dialog.querySelector('img');
    let opener = null;
    layout.querySelectorAll('.article-screen-link').forEach((link) => {
        link.addEventListener('click', (event) => {
            if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
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
