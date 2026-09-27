(() => {
    const demo = document.querySelector('[data-multi-reading-demo]');
    if (!demo) return;

    const controls = demo.querySelector('.multi-reading-controls');
    const button = demo.querySelector('.multi-reading-toggle');
    const error = demo.querySelector('.multi-reading-error');
    const manual = demo.querySelector('.multi-reading-manual');
    const manualLabel = demo.querySelector('.multi-reading-manual-label');
    const audio = ['a', 'b'].map((key) => demo.querySelector(`[data-audio="${key}"]`));
    const timings = audio.map((item) => JSON.parse(item.dataset.verses));
    const lines = [...demo.querySelectorAll('.multi-reading-line')];
    let step = 0;
    let active = false;
    let inGap = false;
    let gapRemaining = 2000;
    let gapDeadline = 0;
    let timer = 0;
    let segmentTimer = 0;
    let frame = 0;
    let generation = 0;

    function label(value) {
        button.textContent = demo.dataset[value];
    }

    function highlight() {
        lines.forEach((line, index) => {
            const playing = active && !inGap && index === step;
            line.classList.toggle('is-playing', playing);
            if (playing) line.setAttribute('aria-current', 'true');
            else line.removeAttribute('aria-current');
        });
    }

    function stopTimers() {
        window.clearTimeout(timer);
        window.clearTimeout(segmentTimer);
        window.cancelAnimationFrame(frame);
        timer = 0;
        segmentTimer = 0;
        frame = 0;
    }

    function showError() {
        if (error.hidden === false) return;
        generation += 1;
        active = false;
        stopTimers();
        audio.forEach((item) => item.pause());
        highlight();
        error.textContent = demo.dataset.error;
        error.hidden = false;
        button.disabled = true;
        manual.hidden = false;
        manualLabel.hidden = false;
    }

    function finishSegment() {
        if (!active || inGap) return;
        const last = step === 9;
        if (last) active = false;
        else inGap = true;
        stopTimers();
        audio[step % 2].pause();
        if (last) {
            step = 0;
            gapRemaining = 2000;
            highlight();
            label('playAgain');
            return;
        }
        gapRemaining = 2000;
        highlight();
        beginGap();
    }

    function monitor() {
        frame = 0;
        if (!active || inGap) return;
        const item = audio[step % 2];
        const end = timings[step % 2][Math.floor(step / 2)][1];
        if (item.currentTime >= end - 0.015) {
            finishSegment();
            return;
        }
        frame = window.requestAnimationFrame(monitor);
    }

    audio.forEach((item, index) => {
        item.addEventListener('timeupdate', () => {
            if (active && !inGap && step % 2 === index &&
                item.currentTime >= timings[index][Math.floor(step / 2)][1] - 0.015) finishSegment();
        });
        item.addEventListener('ended', () => {
            if (active && !inGap && step % 2 === index) showError();
        });
    });

    function beginGap() {
        if (!active) return;
        gapDeadline = performance.now() + gapRemaining;
        timer = window.setTimeout(() => {
            if (!active) return;
            timer = 0;
            inGap = false;
            step += 1;
            startSegment(false);
        }, gapRemaining);
    }

    function ready(item) {
        if (item.readyState >= HTMLMediaElement.HAVE_METADATA) return Promise.resolve();
        return new Promise((resolve, reject) => {
            const timeout = window.setTimeout(() => { cleanup(); reject(new Error('Audio load timed out')); }, 20000);
            const cleanup = () => {
                window.clearTimeout(timeout);
                item.removeEventListener('loadedmetadata', loaded);
                item.removeEventListener('error', failed);
            };
            const loaded = () => { cleanup(); resolve(); };
            const failed = () => { cleanup(); reject(new Error('Audio metadata failed')); };
            item.addEventListener('loadedmetadata', loaded);
            item.addEventListener('error', failed);
            item.preload = 'auto';
            item.load();
        });
    }

    async function startSegment(resume) {
        const token = ++generation;
        const item = audio[step % 2];
        const [begin, end] = timings[step % 2][Math.floor(step / 2)];
        highlight();
        try {
            await ready(item);
            if (!active || inGap || token !== generation) return;
            if (!resume || item.currentTime < begin || item.currentTime >= end) item.currentTime = begin;
            if (item.seeking) {
                await new Promise((resolve) => item.addEventListener('seeked', resolve, { once: true }));
            }
            if (!active || inGap || token !== generation) return;
            await item.play();
            if (!active || inGap || token !== generation) { item.pause(); return; }
            segmentTimer = window.setTimeout(finishSegment, Math.max(0, (end - item.currentTime) * 1000));
            monitor();
        } catch (reason) {
            if (active && token === generation) showError();
        }
    }

    button.addEventListener('click', () => {
        if (active) {
            active = false;
            generation += 1;
            if (inGap) gapRemaining = Math.max(0, gapDeadline - performance.now());
            stopTimers();
            audio.forEach((item) => item.pause());
            highlight();
            label('play');
            return;
        }
        active = true;
        label('pause');
        if (inGap) beginGap();
        else startSegment(step !== 0 || audio[0].currentTime > 0);
    });

    audio.forEach((item) => item.addEventListener('error', showError));
    manual.hidden = true;
    manualLabel.hidden = true;
    controls.hidden = false;
})();
