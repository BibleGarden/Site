// Run with `node tests/multi_reading_demo_sequence.js`.
// Drive real player code with media events and full-file (200) fetch responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const paths = Array.from({ length: 5 }, (_, verse) => [
    `/audio/demo/prozorovsky/${verse + 1}.mp3`,
    `/audio/demo/bsb_souer/${verse + 1}.mp3`,
]).flat();

function element() {
    const listeners = new Map();
    return {
        hidden: false,
        disabled: false,
        textContent: '',
        classList: { toggle() {} },
        attributes: {},
        addEventListener(name, callback) {
            if (!listeners.has(name)) listeners.set(name, []);
            listeners.get(name).push(callback);
        },
        emit(name) { (listeners.get(name) || []).forEach((callback) => callback()); },
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; },
    };
}

const controls = element();
const button = element();
const error = element();
error.hidden = true;
const lines = paths.map(element);
const status = element();
const announced = [];
Object.defineProperty(status, 'textContent', {
    get() { return this.text || ''; },
    set(value) { this.text = value; if (value) announced.push(value); },
});
const played = [];
let pausedGap = false;
let resolveFirstPlay;
const player = element();
player.src = paths[0];
player.ended = false;
player.paused = true;
player.pause = function () { this.paused = true; this.emit('pause'); };
player.play = function () {
    played.push(this.src);
    this.ended = false;
    this.paused = false;
    if (played.length === 1) return new Promise((resolve) => { resolveFirstPlay = resolve; });
    queueMicrotask(() => {
        if (this.paused) return;
        this.emit('playing');
        setImmediate(() => {
            if (this.paused) return;
            this.ended = true;
            this.emit('ended');
        });
    });
    return Promise.resolve();
};

const demo = {
    dataset: { kind: 'multi-reading', play: 'Play', pause: 'Pause', playAgain: 'Play again', error: 'Audio error', verseLabel: 'Verse', clips: JSON.stringify(paths) },
    querySelector(selector) {
        return {
            '.multi-reading-controls': controls,
            '.multi-reading-toggle': button,
            '.multi-reading-error': error,
            '[data-demo-player]': player,
            '[data-demo-status]': status,
        }[selector];
    },
    querySelectorAll(selector) {
        if (selector === '.multi-reading-line') return lines;
        throw new Error(selector);
    },
};

let blobNumber = 0;
const blobPaths = new Map();
const context = {
    document: { querySelector: () => demo },
    window: {
        setTimeout: (callback, delay) => setTimeout(callback, Math.min(delay, 1)),
        // Simulate a gap callback already queued when clearTimeout runs.
        clearTimeout() {},
        addEventListener() {},
    },
    performance,
    fetch: async (url) => ({ ok: true, status: 200, blob: async () => ({ path: url }) }),
    URL: {
        createObjectURL(blob) {
            const url = `blob:clip-${++blobNumber}`;
            blobPaths.set(url, blob.path);
            return url;
        },
        revokeObjectURL() {},
    },
};
vm.runInNewContext(fs.readFileSync('static/bible-garden/js/multi-reading-demo.js', 'utf8'), context);
player.addEventListener('ended', () => {
    if (pausedGap) return;
    pausedGap = true;
    button.emit('click');
    button.emit('click');
});
button.emit('click');
assert.equal(played.length, 1, 'first play() must run synchronously in the click handler');
setTimeout(() => {
    assert.equal(played.length, 1, 'buffering without ended must not start a gap');
    button.emit('click');
    button.emit('click');
    queueMicrotask(() => resolveFirstPlay());
}, 10);

const timeout = setTimeout(() => { throw new Error(`demo did not finish: ${JSON.stringify(played)}`); }, 3000);
const poll = setInterval(() => {
    if (button.textContent !== 'Play again') return;
    clearTimeout(timeout);
    clearInterval(poll);
    assert.equal(error.hidden, true);
    assert.equal(pausedGap, true);
    assert.deepEqual(played.map((url) => blobPaths.get(url) || url), [paths[0], ...paths]);
    assert.equal(played.length, 11);
    assert.deepEqual(announced, ['Verse 1', 'Verse 2', 'Verse 3', 'Verse 4', 'Verse 5'], 'each verse is announced once');
    assert.equal(button.attributes['aria-pressed'], undefined, 'the changing label is the only state');
    console.log('A1, B1, A2, B2, A3, B3, A4, B4, A5, B5: OK');
}, 1);

function testVoices() {
    const voicePaths = ['bondarenko', 'prudovsky'].map((name) => `/audio/demo/${name}/1-5.mp3`);
    const intervals = Array.from({ length: 5 }, (_, index) => ({ start: index * 2 + 0.05, end: index * 2 + 1 }));
    const rows = voicePaths.map((path, index) => {
        const controls = element();
        const button = element();
        const error = element();
        const passage = element();
        const lines = Array.from({ length: 5 }, (_, verse) => {
            const line = element();
            line.textContent = `Verse ${verse + 1}`;
            return line;
        });
        error.hidden = true;
        return {
            dataset: { clips: JSON.stringify([path]), intervals: JSON.stringify(intervals), label: `Voice ${index}` },
            controls, button, error, passage, lines,
            querySelector(selector) {
                return {
                    '.multi-reading-controls': controls,
                    '.multi-reading-toggle': button,
                    '.multi-reading-error': error,
                    '[data-voice-passage]': passage,
                }[selector];
            },
            querySelectorAll(selector) {
                if (selector === '[data-verse]') return lines;
                throw new Error(selector);
            },
        };
    });
    const voiceStatus = element();
    const voicePlayer = element();
    const voicePlayed = [];
    voicePlayer.src = voicePaths[0];
    voicePlayer.ended = false;
    voicePlayer.currentTime = 0;
    voicePlayer.pause = function () { this.emit('pause'); };
    voicePlayer.play = function () {
        this.ended = false;
        voicePlayed.push(this.src);
        this.emit('playing');
        return Promise.resolve();
    };
    const voiceDemo = {
        dataset: { kind: 'voices', play: 'Play', pause: 'Pause', playAgain: 'Play again', error: 'Audio error', verseLabel: 'Verse' },
        querySelector(selector) {
            if (selector === '[data-demo-player]') return voicePlayer;
            if (selector === '[data-demo-status]') return voiceStatus;
            throw new Error(selector);
        },
        querySelectorAll(selector) {
            if (selector === '[data-demo-track]') return rows;
            throw new Error(selector);
        },
    };
    vm.runInNewContext(fs.readFileSync('static/bible-garden/js/multi-reading-demo.js', 'utf8'), {
        document: { querySelector: () => voiceDemo },
        window: { setTimeout, clearTimeout, addEventListener() {} },
        performance,
        fetch: () => { throw new Error('continuous clips must not prefetch per-verse audio'); },
        URL: { createObjectURL() {}, revokeObjectURL() {} },
    });
    assert(rows.every((row) => row.passage.hidden), 'JS starts with compact rows');
    rows[0].button.emit('click');
    assert.deepEqual(voicePlayed, [voicePaths[0]]);
    assert.equal(rows[0].passage.hidden, false);
    assert.equal(rows[0].button.attributes['aria-label'], 'Pause: Voice 0');
    assert.equal(rows[0].button.attributes['aria-pressed'], undefined);
    voicePlayer.currentTime = 0.5;
    voicePlayer.emit('timeupdate');
    assert.equal(rows[0].lines[0].attributes['aria-current'], 'true');
    assert.equal(voiceStatus.textContent, 'Verse 1');
    voicePlayer.currentTime = 1.5;
    voicePlayer.emit('timeupdate');
    assert.equal(rows[0].lines[0].attributes['aria-current'], undefined);
    assert.equal(rows[0].passage.hidden, false, 'passage stays open during music');
    rows[0].button.emit('click');
    assert.equal(rows[0].passage.hidden, false, 'passage stays open while paused');
    rows[0].button.emit('click');
    assert.equal(rows[0].passage.hidden, false);
    rows[1].button.emit('click');
    assert.deepEqual(voicePlayed, [voicePaths[0], voicePaths[0], voicePaths[1]]);
    assert.equal(rows[0].button.attributes['aria-label'], 'Play: Voice 0');
    assert.equal(rows[0].passage.hidden, true);
    assert.equal(rows[1].passage.hidden, false);
    for (let verse = 0; verse < 5; verse += 1) {
        voicePlayer.currentTime = verse * 2 + 0.5;
        voicePlayer.emit('timeupdate');
        assert.equal(rows[1].lines[verse].attributes['aria-current'], 'true');
        assert.equal(voiceStatus.textContent, `Verse ${verse + 1}`);
        assert.equal(rows[1].passage.hidden, false);
    }
    assert.equal(rows[1].lines.map((line) => line.textContent).join(','), 'Verse 1,Verse 2,Verse 3,Verse 4,Verse 5');
    voicePlayer.ended = true;
    voicePlayer.emit('ended');
    assert.equal(rows[1].button.textContent, 'Play again');
    assert.equal(rows[1].button.attributes['aria-label'], 'Play again: Voice 1');
    assert.equal(rows[1].passage.hidden, false, 'passage stays open after playback');
    console.log('Persistent passage, verse highlight and switching: OK');
}
testVoices();
