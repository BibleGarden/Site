(() => {
    const demo = document.querySelector('[data-multi-reading-demo]');
    if (!demo) return;

    const voices = demo.dataset.kind === 'voices';
    if (!voices && demo.dataset.kind !== 'multi-reading') throw new Error('Invalid audio demo kind');
    const player = demo.querySelector('[data-demo-player]');
    const status = demo.querySelector('[data-demo-status]');
    const trackElements = voices ? [...demo.querySelectorAll('[data-demo-track]')] : [demo];
    const tracks = trackElements.map((element) => ({
        controls: element.querySelector('.multi-reading-controls'),
        button: element.querySelector('.multi-reading-toggle'),
        error: element.querySelector('.multi-reading-error'),
        clips: JSON.parse(element.dataset.clips),
        lines: [...element.querySelectorAll(voices ? '[data-verse]' : '.multi-reading-line')],
        label: element.dataset.label || '',
        passage: voices ? element.querySelector('[data-voice-passage]') : null,
        intervals: voices ? JSON.parse(element.dataset.intervals) : null,
    }));
    if (!status || !demo.dataset.verseLabel || !tracks.length || tracks.some((track) => !Array.isArray(track.clips)
        || track.clips.length !== (voices ? 1 : 10)
        || track.clips.some((path) => typeof path !== 'string' || !path.startsWith('/audio/demo/'))
        || (voices ? !track.clips[0].endsWith('/1-5.mp3') || !track.passage
            || !Array.isArray(track.intervals) || track.intervals.length !== 5
            || track.intervals.some((interval, index) => !Number.isFinite(interval.start)
                || !Number.isFinite(interval.end) || interval.start < 0 || interval.end <= interval.start
                || (index > 0 && interval.start < track.intervals[index - 1].end))
            || track.lines.length !== 5
            : track.lines.length !== track.clips.length))) {
        throw new Error('Invalid audio demo markup');
    }

    const prefetched = new Map();
    let track = tracks[0];
    let step = 0;
    let loadedStep = 0; // HTML points at the first clip, so play() stays inside the click gesture.
    let loadedTrack = track;
    let active = false;
    let playing = false;
    let inGap = false;
    let completed = false;
    let gapRemaining = 2000;
    let gapDeadline = 0;
    let gapTimer = 0;
    let generation = 0;

    function setButton(target, state) {
        target.button.textContent = demo.dataset[state];
        if (voices) target.button.setAttribute('aria-label', `${demo.dataset[state]}: ${target.label}`);
    }

    function announce(verse) {
        const text = `${demo.dataset.verseLabel} ${verse}`;
        if (status.textContent !== text) status.textContent = text;
    }

    function highlight() {
        if (voices) {
            tracks.forEach((item) => {
                const index = item === track && playing && active
                    ? item.intervals.findIndex((interval) => player.currentTime >= interval.start && player.currentTime <= interval.end)
                    : -1;
                if (index >= 0) announce(index + 1);
                item.lines.forEach((line, verse) => {
                    const current = verse === index;
                    line.classList.toggle('is-playing', current);
                    if (current) line.setAttribute('aria-current', 'true');
                    else line.removeAttribute('aria-current');
                });
            });
            return;
        }
        if (playing && active && !inGap) announce(Math.floor(step / 2) + 1);
        tracks.forEach((item) => item.lines.forEach((line, index) => {
            const current = item === track && playing && active && !inGap && index === step;
            line.classList.toggle('is-playing', current);
            if (current) line.setAttribute('aria-current', 'true');
            else line.removeAttribute('aria-current');
        }));
    }

    function showError() {
        if (!track.error.hidden) return;
        generation += 1;
        active = false;
        playing = false;
        window.clearTimeout(gapTimer);
        player.pause();
        highlight();
        track.error.textContent = demo.dataset.error;
        track.error.hidden = false;
        track.button.disabled = true;
        setButton(track, 'play');
    }

    function prefetch(index) {
        if (voices) return;
        if (index >= track.clips.length) return;
        const path = track.clips[index];
        if (prefetched.has(path)) return;
        const pending = fetch(path).then((response) => {
            if (!response.ok) throw new Error(`Audio request failed: ${response.status}`);
            return response.blob();
        }).then((blob) => URL.createObjectURL(blob)).catch(() => null);
        prefetched.set(path, pending);
    }

    async function startClip() {
        const token = ++generation;
        const currentTrack = track;
        try {
            if (loadedTrack !== track || loadedStep !== step || player.ended) {
                const path = track.clips[step];
                const url = prefetched.has(path) ? await prefetched.get(path) : path;
                if (!url) { showError(); return; }
                if (!active || inGap || token !== generation) return;
                player.src = url;
                loadedTrack = track;
                loadedStep = step;
            }
            player.preload = 'auto';
            const playback = player.play();
            prefetch(step + 1);
            await playback;
            if (token !== generation) return;
            if (!active || inGap) player.pause();
        } catch (reason) {
            if (active && token === generation && currentTrack === track) showError();
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
    player.addEventListener('timeupdate', () => { if (voices) highlight(); });
    player.addEventListener('waiting', () => { playing = false; highlight(); });
    player.addEventListener('pause', () => { playing = false; highlight(); });
    player.addEventListener('error', showError);
    player.addEventListener('ended', () => {
        if (!active || inGap || !player.ended) return;
        playing = false;
        if (step === track.clips.length - 1) {
            active = false;
            completed = true;
            step = 0;
            setButton(track, 'playAgain');
            highlight();
            return;
        }
        inGap = true;
        gapRemaining = 2000;
        highlight();
        beginGap();
    });

    tracks.forEach((item) => item.button.addEventListener('click', () => {
        if (item !== track) {
            generation += 1;
            window.clearTimeout(gapTimer);
            player.pause();
            setButton(track, 'play');
            if (voices) track.passage.hidden = true;
            status.textContent = '';
            track = item;
            step = 0;
            loadedStep = -1;
            active = false;
            playing = false;
            inGap = false;
            completed = false;
            gapRemaining = 2000;
            highlight();
        } else if (active) {
            active = false;
            generation += 1;
            if (inGap) gapRemaining = Math.max(0, gapDeadline - performance.now());
            window.clearTimeout(gapTimer);
            player.pause();
            playing = false;
            highlight();
            setButton(track, 'play');
            return;
        }
        if (voices) item.passage.hidden = false;
        active = true;
        setButton(track, 'pause');
        if (completed) {
            completed = false;
            inGap = false;
            step = 0;
        }
        if (inGap) beginGap();
        else startClip();
    }));

    window.addEventListener('pagehide', () => {
        prefetched.forEach((pending) => pending.then((url) => { if (url) URL.revokeObjectURL(url); }));
    });
    tracks.forEach((item) => {
        if (voices) item.passage.hidden = true;
        item.controls.hidden = false;
    });
})();
