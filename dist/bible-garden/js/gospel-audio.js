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
      if (controls.progress.style) controls.progress.style.setProperty('--gospel-progress', `${elapsed / total * 100}%`);
      controls.progress.setAttribute('aria-valuetext', `${clock(elapsed)} / ${clock(total)}`);
      controls.time.textContent = `${clock(elapsed)} / ${clock(total)}`;
      const label = finished ? strings.audio_again : playing ? strings.audio_pause : strings.audio_play;
      controls.button.textContent = controls.icon ? (playing ? 'Ⅱ' : '▶') : label;
      controls.button.setAttribute('aria-label', label);
      controls.button.setAttribute('aria-pressed', String(playing));
      if (controls.current) { controls.current.textContent = segment.reading; controls.current.setAttribute('title', segment.reading); }
      if (controls.cards) [...new Set(controls.cards)].forEach(card => card.classList.toggle('is-current', active && card === controls.cards[index]));
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
      try { audio.currentTime = segment.begin + seekOffset; seekOffset = 0; pending = false; }
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
    async function jump(target, within = 0, play = true) {
      if (disposed || controls.button.disabled || !Number.isInteger(target) || target < 0 || target >= playlist.length) return;
      generation++; clearBoundary();
      if (!audio) prepare();
      else audio.pause();
      index = target; finished = false; announced = -1; playing = false;
      // Seeking to a reading starts it; moving the range preserves pause/play.
      select();
      seekOffset = within;
      if (!pending) { audio.currentTime = playlist[index].begin + within; seekOffset = 0; }
      update();
      if (play && !controls.button.disabled) await start();
    }
    let seekOffset = 0;
    const seekProgress = () => {
      const value = Number(controls.progress.value);
      if (!Number.isFinite(value) || value < 0 || value > total) { fail(new Error('Invalid playlist seek')); return; }
      const target = offsets.findIndex((offset, n) => value < offset + playlist[n].end - playlist[n].begin);
      const n = target < 0 ? playlist.length - 1 : target;
      jump(n, Math.min(value - offsets[n], playlist[n].end - playlist[n].begin - TOLERANCE), playing);
    };
    controls.button.addEventListener('click', toggle);
    if (controls.jumps) controls.jumps.forEach(entry => entry.button.addEventListener('click', () => jump(entry.index)));
    controls.progress.addEventListener('change', seekProgress);
    update();
    return {toggle, jump, dispose() {
      disposed = true; generation++; playing = false; clearBoundary();
      if (audio) { audio.pause(); audio.removeAttribute('src'); audio.load(); }
      update();
    }};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {mountAudio, clock, TOLERANCE};
  if (typeof window !== 'undefined') window.GospelAudio = {mountAudio};
}());
