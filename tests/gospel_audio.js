'use strict';
const assert = require('node:assert/strict');
const {mountAudio, clock, TOLERANCE} = require('../static/bible-garden/js/gospel-audio.js');
class Element {
  constructor() { this.listeners = {}; this.attrs = {}; this.classes = new Set(); this.classList = {toggle: (key, on) => on ? this.classes.add(key) : this.classes.delete(key)}; }
  addEventListener(event, fn) { this.listeners[event] = fn; }
  setAttribute(k, v) { this.attrs[k] = v; }
  removeAttribute(k) { delete this.attrs[k]; }
  getAttribute(k) { return this.attrs[k]; }
}
class FakeAudio extends Element {
  constructor() { super(); this.currentTime = 0; this.duration = 100; this.playCalls = 0; this.loads = 0; this.ended = false; this.paused = true; this.playbackRate = 1; this.autoMetadata = true; }
  async play() { this.playCalls++; this.paused = false; this.listeners.playing(); }
  pause() { this.paused = true; }
  load() { this.loads++; if (this.autoMetadata && this.src) this.listeners.loadedmetadata(); }
  end(time) { this.currentTime = time; this.ended = true; this.listeners.ended(); this.ended = false; }
  set src(value) { this._src = value; this.currentTime = 0; this.ended = false; }
  get src() { return this._src; }
  removeAttribute(k) { super.removeAttribute(k); if (k === 'src') this._src = ''; }
  tick(time) { this.currentTime = time; this.listeners.timeupdate(); }
}
const controlsFor = () => Object.fromEntries(['button', 'progress', 'time', 'error', 'status'].map(k => [k, new Element()]));
const linesFor = () => Array.from({length: 4}, (_, i) => { const line = new Element(); line.setAttribute('data-audio-label', `Luke ${i + 1}`); return line; });
const playlist = [{url: 'https://api.test/01.mp3', begin: 10, end: 12},
  {url: 'https://api.test/01.mp3', begin: 20, end: 23}, // Skip verses outside the reference.
  {url: 'https://api.test/02.mp3', begin: 5, end: 7},
  {url: 'https://api.test/01.mp3', begin: 30, end: 32}]; // Composite returns to an earlier chapter.
const strings = {audio_play: 'Play', audio_pause: 'Pause', audio_again: 'Again', audio_error: 'Error', audio_verse: 'Verse {verse}'};
const originalTimeout = global.setTimeout, originalClear = global.clearTimeout;
let timerId = 0;
const timers = new Map();
global.setTimeout = fn => { timers.set(++timerId, fn); return timerId; };
global.clearTimeout = id => timers.delete(id);
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  const controls = controlsFor(), lines = linesFor(), audio = new FakeAudio();
  let created = 0, highlighted = [];
  const player = mountAudio(controls, playlist, lines, strings, () => { created++; return audio; }, line => highlighted.push(line));
  assert.equal(created, 0); assert.equal(controls.button.textContent, 'Play'); assert.equal(controls.progress.max, 9);
  await player.toggle(); assert.equal(created, 1); assert.equal(audio.preload, 'none'); assert.equal(audio.currentTime, 10);
  assert.equal(audio.src, playlist[0].url); assert.equal(audio.playCalls, 1); assert.equal(audio.loads, 1);
  assert.equal(lines[0].attrs['aria-current'], 'true'); assert.equal(controls.status.textContent, 'Verse Luke 1');
  audio.tick(11); assert.equal(controls.progress.value, 1);
  await player.toggle(); assert.equal(audio.paused, true); assert.equal(timers.size, 0); assert.equal(lines[0].attrs['aria-current'], undefined);
  audio.tick(11); assert.equal(audio.playCalls, 1);
  await player.toggle(); assert.equal(audio.currentTime, 11); assert.equal(audio.playCalls, 2);
  audio.tick(12); await settle(); assert.equal(audio.currentTime, 20); assert.equal(audio.loads, 1);
  assert.equal(lines[1].attrs['aria-current'], 'true'); assert.equal(controls.progress.value, 2);
  audio.tick(21); assert.equal(controls.progress.value, 3);
  audio.tick(23); await settle(); assert.equal(audio.src, playlist[2].url); assert.equal(audio.currentTime, 5);
  assert.equal(audio.loads, 2); assert.equal(lines[2].attrs['aria-current'], 'true');
  audio.tick(7); await settle(); assert.equal(audio.src, playlist[3].url); assert.equal(audio.currentTime, 30);
  // A timer catches the final boundary between sparse browser timeupdate events.
  audio.currentTime = 32 - TOLERANCE / 2;
  const boundary = [...timers.values()][0]; boundary();
  assert.equal(audio.paused, true); assert.equal(audio.currentTime, 32); assert.equal(timers.size, 0);
  assert.equal(controls.progress.value, 9); assert.equal(controls.button.textContent, 'Again');
  assert.equal(lines[3].attrs['aria-current'], undefined); assert.deepEqual(highlighted, lines);
  await player.toggle(); assert.equal(audio.src, playlist[0].url); assert.equal(audio.currentTime, 10);
  player.dispose(); assert.equal(audio.paused, true); assert.equal(timers.size, 0);
  const calls = audio.playCalls; audio.end(12); assert.equal(audio.playCalls, calls);
  const originalError = console.error; let failures = 0; console.error = () => failures++;
  for (const mode of ['play', 'error', 'short', 'early-end']) {
    const badControls = controlsFor(), badAudio = new FakeAudio();
    if (mode === 'play') badAudio.play = async () => { throw new Error('blocked'); };
    if (mode === 'short') badAudio.duration = 11;
    const bad = mountAudio(badControls, playlist, linesFor(), strings, () => badAudio);
    const before = failures;
    await bad.toggle();
    if (mode === 'error') badAudio.listeners.error();
    if (mode === 'early-end') badAudio.end(11);
    assert.equal(failures, before + 1); assert.equal(badControls.button.disabled, true);
    assert.equal(badControls.error.textContent, 'Error'); bad.dispose();
  }
  console.error = originalError;
  const waitingAudio = new FakeAudio(), pending = [];
  waitingAudio.play = () => { waitingAudio.paused = false; return new Promise(resolve => pending.push(resolve)); };
  const quick = mountAudio(controlsFor(), playlist, linesFor(), strings, () => waitingAudio);
  const first = quick.toggle(); await quick.toggle(); const latest = quick.toggle();
  pending[1](); await latest; pending[0](); await first; assert.equal(waitingAudio.paused, false); quick.dispose();
  const slowAudio = new FakeAudio(); slowAudio.autoMetadata = false;
  const slowLines = linesFor(), slowControls = controlsFor();
  const slow = mountAudio(slowControls, playlist, slowLines, strings, () => slowAudio);
  await slow.toggle(); assert.equal(slowLines[0].attrs['aria-current'], undefined);
  await slow.toggle(); slowAudio.listeners.loadedmetadata();
  assert.equal(slowAudio.currentTime, 10); assert.equal(slowAudio.paused, true);
  await slow.toggle(); assert.equal(slowLines[0].attrs['aria-current'], 'true'); slow.dispose();
  const endAudio = new FakeAudio(); const end = mountAudio(controlsFor(), playlist, linesFor(), strings, () => endAudio);
  await end.toggle(); endAudio.end(12); await settle(); assert.equal(endAudio.currentTime, 20); end.dispose();
  assert.throws(() => mountAudio(controlsFor(), [{url: 'a', begin: 1, end: 1}], [new Element()], strings));
  assert.equal(clock(65.9), '1:05'); assert.equal(timers.size, 0);
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  global.setTimeout = originalTimeout; global.clearTimeout = originalClear;
});
