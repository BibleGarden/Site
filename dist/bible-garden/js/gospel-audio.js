/* Stream chapter files, seeking through the displayed verse windows in order. */
(function () {
  'use strict';
  const TOLERANCE = 0.025;
  function clock(seconds) {
    const whole = Math.max(0, Math.floor(seconds));
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
  }
  function mountAudio(controls, playlist, lines, strings, audioFactory = () => new Audio(), onVerse = () => {}) {
    if (!playlist.length || playlist.length !== lines.length || playlist.some(s =>
      typeof s.url !== 'string' || !Number.isFinite(s.begin) || !Number.isFinite(s.end) || s.begin < 0 || s.end <= s.begin)) {
      throw new Error('Invalid Gospel playlist');
    }
    let audio = null, index = 0, playing = false, finished = false, disposed = false;
    let generation = 0, pending = false, timer = null, announced = -1;
    let total = 0;
    const offsets = playlist.map(segment => { const offset = total; total += segment.end - segment.begin; return offset; });
    controls.progress.max = total; controls.progress.value = 0;
    function clearBoundary() { clearTimeout(timer); timer = null; }
    function update() {
      const active = playing && !pending;
      lines.forEach((line, n) => {
        line.classList.toggle('is-playing', active && n === index);
        if (active && n === index) line.setAttribute('aria-current', 'true');
        else line.removeAttribute('aria-current');
      });
      const segment = playlist[index];
      const within = audio && !pending ? Math.max(0, Math.min(audio.currentTime - segment.begin, segment.end - segment.begin)) : 0;
      const elapsed = finished ? total : offsets[index] + within;
      controls.progress.value = elapsed;
      controls.time.textContent = `${clock(elapsed)} / ${clock(total)}`;
      controls.button.textContent = finished ? strings.audio_again : playing ? strings.audio_pause : strings.audio_play;
      if (active && announced !== index) {
        announced = index;
        controls.status.textContent = strings.audio_verse.replace('{verse}', lines[index].getAttribute('data-audio-label'));
        onVerse(lines[index]);
      }
    }
    function fail(error) {
      if (disposed) return;
      generation++; playing = false; clearBoundary();
      if (audio) audio.pause();
      controls.error.textContent = strings.audio_error; controls.error.hidden = false;
      controls.button.disabled = true; update();
      console.error('gospel-audio:', error);
    }
    function seek() {
      const segment = playlist[index];
      if (Number.isFinite(audio.duration) && segment.end > audio.duration + TOLERANCE) {
        fail(new Error('Gospel timecode exceeds chapter duration')); return;
      }
      try { audio.currentTime = segment.begin; pending = false; }
      catch (error) { fail(error); }
    }
    async function start() {
      const token = ++generation;
      playing = true; update();
      try {
        await audio.play();
        if (token !== generation) { if (!playing) audio.pause(); return; }
        if (disposed || !playing) audio.pause();
        else boundary();
      } catch (error) { if (token === generation) fail(error); }
    }
    function select() {
      clearBoundary();
      const segment = playlist[index];
      if (audio.src !== segment.url) {
        pending = true; audio.src = segment.url; audio.load();
      } else seek();
    }
    function advance() {
      clearBoundary(); audio.pause();
      if (index + 1 === playlist.length) {
        generation++; playing = false; finished = true;
        audio.currentTime = playlist[index].end; update(); return;
      }
      index++; select();
      if (!controls.button.disabled) start();
    }
    function boundary() {
      clearBoundary();
      if (disposed || !playing || pending || audio.paused || audio.seeking) return;
      const remaining = playlist[index].end - audio.currentTime;
      if (remaining <= TOLERANCE) { advance(); return; }
      update();
      // Supplement coarse timeupdate events with a short boundary timer.
      timer = setTimeout(boundary, Math.max(1, Math.min(50, (remaining - TOLERANCE) * 1000 / (audio.playbackRate || 1))));
    }
    function prepare() {
      audio = audioFactory(); audio.preload = 'none';
      audio.addEventListener('loadedmetadata', () => { if (!disposed && pending) { seek(); update(); } });
      audio.addEventListener('timeupdate', boundary);
      audio.addEventListener('seeked', boundary);
      audio.addEventListener('ratechange', boundary);
      audio.addEventListener('error', () => fail(new Error('Gospel chapter failed')));
      audio.addEventListener('playing', () => { if (!disposed && playing) { update(); boundary(); } });
      audio.addEventListener('ended', () => {
        if (disposed || !playing || !audio.ended) return;
        if (!pending && audio.currentTime >= playlist[index].end - TOLERANCE) advance();
        else fail(new Error('Gospel chapter ended before passage boundary'));
      });
    }
    async function toggle() {
      if (disposed || controls.button.disabled) return;
      if (playing) {
        generation++; playing = false; clearBoundary(); audio.pause(); update(); return;
      }
      if (!audio) { prepare(); select(); }
      if (finished) { finished = false; index = 0; announced = -1; select(); }
      if (!controls.button.disabled) await start();
    }
    controls.button.addEventListener('click', toggle);
    update();
    return {toggle, dispose() {
      disposed = true; generation++; playing = false; clearBoundary();
      if (audio) { audio.pause(); audio.removeAttribute('src'); audio.load(); }
      update();
    }};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {mountAudio, clock, TOLERANCE};
  if (typeof window !== 'undefined') window.GospelAudio = {mountAudio};
}());
