// Hero coverflow: the server renders the first screen in front; this script adds navigation.
(() => {
    const root = document.querySelector('[data-coverflow]');
    if (!root) {
        return;
    }
    const slides = [...root.querySelectorAll('.coverflow-slide')];
    const dots = [...root.querySelectorAll('.coverflow-dot')];
    const total = slides.length;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const AUTOPLAY_MS = 5000;
    const SWIPE_PX = 40;
    let current = 0;
    let timer = null;
    let stopped = false;
    let paused = false;
    let visible = false;

    // Shortest circular distance from slide i to the current one.
    function offset(i) {
        let diff = i - current;
        if (diff > total / 2) diff -= total;
        if (diff < -total / 2) diff += total;
        return diff;
    }

    function show(index) {
        current = (index + total) % total;
        slides.forEach((slide, i) => {
            const diff = offset(i);
            slide.dataset.pos = Math.abs(diff) <= 2 ? String(diff) : 'hidden';
            slide.setAttribute('aria-hidden', String(diff !== 0));
        });
        dots.forEach((dot, i) => {
            if (i === current) {
                dot.setAttribute('aria-current', 'true');
            } else {
                dot.removeAttribute('aria-current');
            }
        });
    }

    function schedule() {
        clearInterval(timer);
        timer = null;
        if (!stopped && !paused && visible && !reducedMotion.matches && !document.hidden) {
            timer = setInterval(() => show(current + 1), AUTOPLAY_MS);
        }
    }

    // Any deliberate interaction ends autoplay for this page view.
    function choose(index) {
        stopped = true;
        schedule();
        show(index);
    }

    dots.forEach((dot, i) => {
        dot.hidden = false;
        dot.addEventListener('click', () => choose(i));
    });

    root.addEventListener('keydown', (event) => {
        const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
        if (step) {
            event.preventDefault();
            choose(current + step);
            dots[current].focus();
        }
    });

    let start = null;
    let swiped = false;
    root.addEventListener('pointerdown', (event) => {
        start = { x: event.clientX, y: event.clientY };
        swiped = false;
    });
    root.addEventListener('pointerup', (event) => {
        if (!start) {
            return;
        }
        const dx = event.clientX - start.x;
        const dy = event.clientY - start.y;
        start = null;
        if (Math.abs(dx) >= SWIPE_PX && Math.abs(dx) > Math.abs(dy)) {
            swiped = true;
            choose(current + (dx < 0 ? 1 : -1));
        }
    });
    root.addEventListener('pointercancel', () => {
        start = null;
    });

    slides.forEach((slide, i) => {
        slide.addEventListener('click', () => {
            if (!swiped && i !== current) {
                choose(i);
            }
        });
    });

    root.addEventListener('mouseenter', () => { paused = true; schedule(); });
    root.addEventListener('mouseleave', () => { paused = root.contains(document.activeElement); schedule(); });
    root.addEventListener('focusin', () => { paused = true; schedule(); });
    root.addEventListener('focusout', (event) => {
        paused = root.contains(event.relatedTarget) || root.matches(':hover');
        schedule();
    });
    document.addEventListener('visibilitychange', schedule);
    reducedMotion.addEventListener('change', schedule);
    new IntersectionObserver(([entry]) => {
        visible = entry.isIntersecting;
        schedule();
    }, { threshold: 0.5 }).observe(root);

    root.classList.add('is-interactive');
    show(0);
})();
