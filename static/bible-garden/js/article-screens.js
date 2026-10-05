(() => {
    const layout = document.querySelector('.article-screen-layout');
    if (!layout) return;

    const headings = [...layout.querySelectorAll('h2[data-screen]')];
    const images = [...layout.querySelectorAll('.article-screen-phone-image')];
    const appLabel = layout.querySelector('.article-screen-app-slot .article-screen-app-label');
    const pager = layout.querySelector('.article-screen-pager');
    const counter = layout.querySelector('.article-screen-counter');
    const dots = [...layout.querySelectorAll('.article-screen-dot')];
    const screenIndices = new Map(images.map((image, index) => [image.dataset.screen, index]));
    const desktop = window.matchMedia('(min-width: 1024px)');
    let active = -1;
    let requested = -1;
    let requestVersion = 0;
    let scheduled = false;
    let manualSection = null;

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
            appLabel.hidden = images[index].dataset.app !== 'lampada';
            active = index;
            requested = -1;
            if (pager) {
                if (counter) {
                    counter.textContent = `${index + 1} / ${images.length}`;
                    counter.setAttribute('aria-label', counter.dataset.label
                        .replace('{n}', index + 1).replace('{total}', images.length));
                }
                dots.forEach((dot, dotIndex) => {
                    if (dotIndex === index) dot.setAttribute('aria-current', 'true');
                    else dot.removeAttribute('aria-current');
                });
                pager.querySelector('.article-screen-previous').disabled = index === 0;
                pager.querySelector('.article-screen-next').disabled = index === images.length - 1;
            }
            preload(index + 1);
        }).catch((error) => {
            if (version !== requestVersion) return;
            requested = -1;
            console.error(`Unable to load article screen ${images[index].dataset.src}`, error);
        });
    }

    function sectionAtReadingLine() {
        const activationLine = Math.max(112, window.innerHeight * 0.28);
        let section = 0;
        headings.forEach((heading, index) => {
            if (heading.getBoundingClientRect().top <= activationLine) section = index;
        });
        return section;
    }

    function updateScreen() {
        scheduled = false;
        if (!desktop.matches) return;
        const section = sectionAtReadingLine();
        if (manualSection === section) return;
        manualSection = null;
        showScreen(screenIndices.get(headings[section].dataset.screen));
    }

    function chooseScreen(index) {
        if (!desktop.matches || index < 0 || index >= images.length) return;
        manualSection = sectionAtReadingLine();
        showScreen(index);
    }

    if (pager) {
        dots.forEach((dot, index) => dot.addEventListener('click', () => chooseScreen(index)));
        pager.querySelector('.article-screen-previous').addEventListener('click', () => {
            chooseScreen((requested >= 0 ? requested : active) - 1);
        });
        pager.querySelector('.article-screen-next').addEventListener('click', () => {
            chooseScreen((requested >= 0 ? requested : active) + 1);
        });
        pager.hidden = false;
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
        manualSection = null;
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
