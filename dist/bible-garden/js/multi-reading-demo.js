(() => {
    const demo = document.querySelector('[data-multi-reading-demo]');
    if (!demo) return;

    const controls = demo.querySelector('.multi-reading-controls');
    const button = demo.querySelector('.multi-reading-toggle');
    const error = demo.querySelector('.multi-reading-error');
    const player = demo.querySelector('[data-demo-player]');
    const clips = JSON.parse(demo.dataset.clips);
    const lines = [...demo.querySelectorAll('.multi-reading-line')];
    if (!Array.isArray(clips) || clips.length !== 10 || clips.some((path) => typeof path !== 'string' || !path.startsWith('/audio/demo/')) || lines.length !== 10) {
        throw new Error('Invalid Multi Reading demo markup');
    }

    const prefetched = new Map();
    let step = 0;
    let loadedStep = 0; // HTML already points at A1, so its first play() stays inside the click gesture.
    let active = false;
    let playing = false;
    let inGap = false;
    let completed = false;
    let gapRemaining = 2000;
    let gapDeadline = 0;
    let gapTimer = 0;
    let generation = 0;

    function highlight() {
        lines.forEach((line, index) => {
            const current = playing && active && !inGap && index === step;
            line.classList.toggle('is-playing', current);
            if (current) line.setAttribute('aria-current', 'true');
            else line.removeAttribute('aria-current');
        });
    }

    function showError() {
        if (!error.hidden) return;
        generation += 1;
        active = false;
        playing = false;
        window.clearTimeout(gapTimer);
        player.pause();
        highlight();
        error.textContent = demo.dataset.error;
        error.hidden = false;
        button.disabled = true;
    }

    function prefetch(index) {
        if (index >= clips.length || prefetched.has(index)) return;
        const pending = fetch(clips[index]).then((response) => {
            if (!response.ok) throw new Error(`Audio request failed: ${response.status}`);
            return response.blob();
        }).then((blob) => URL.createObjectURL(blob)).catch(() => null);
        prefetched.set(index, pending);
    }

    async function startClip() {
        const token = ++generation;
        try {
            if (loadedStep !== step || player.ended) {
                const url = prefetched.has(step) ? await prefetched.get(step) : clips[step];
                if (!url) { showError(); return; }
                if (!active || inGap || token !== generation) return;
                player.src = url;
                loadedStep = step;
            }
            player.preload = 'auto';
            const playback = player.play();
            prefetch(step + 1);
            await playback;
            if (token !== generation) return;
            if (!active || inGap) player.pause();
        } catch (reason) {
            if (active && token === generation) showError();
        }
    }

    function beginGap() {
        if (!active) return;
        const token = generation;
        gapDeadline = performance.now() + gapRemaining;
        gapTimer = window.setTimeout(() => {
            if (!active || !inGap || token !== generation) return;
            gapTimer = 0;
            inGap = false;
            step += 1;
            startClip();
        }, gapRemaining);
    }

    player.addEventListener('playing', () => {
        if (!active || inGap) return;
        playing = true;
        highlight();
    });
    player.addEventListener('waiting', () => { playing = false; highlight(); });
    player.addEventListener('pause', () => { playing = false; highlight(); });
    player.addEventListener('error', showError);
    player.addEventListener('ended', () => {
        if (!active || inGap || !player.ended) return;
        playing = false;
        if (step === clips.length - 1) {
            active = false;
            completed = true;
            step = 0;
            button.textContent = demo.dataset.playAgain;
            highlight();
            return;
        }
        inGap = true;
        gapRemaining = 2000;
        highlight();
        beginGap();
    });

    button.addEventListener('click', () => {
        if (active) {
            active = false;
            generation += 1;
            if (inGap) gapRemaining = Math.max(0, gapDeadline - performance.now());
            window.clearTimeout(gapTimer);
            player.pause();
            playing = false;
            highlight();
            button.textContent = demo.dataset.play;
            return;
        }
        active = true;
        button.textContent = demo.dataset.pause;
        if (completed) {
            completed = false;
            inGap = false;
            step = 0;
        }
        if (inGap) beginGap();
        else startClip();
    });

    window.addEventListener('pagehide', () => {
        prefetched.forEach((pending) => pending.then((url) => { if (url) URL.revokeObjectURL(url); }));
    });
    controls.hidden = false;
})();
