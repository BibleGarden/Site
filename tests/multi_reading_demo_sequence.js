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
    dataset: { play: 'Play', pause: 'Pause', playAgain: 'Play again', error: 'Audio error', clips: JSON.stringify(paths) },
    querySelector(selector) {
        return {
            '.multi-reading-controls': controls,
            '.multi-reading-toggle': button,
            '.multi-reading-error': error,
            '[data-demo-player]': player,
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
    console.log('A1, B1, A2, B2, A3, B3, A4, B4, A5, B5: OK');
}, 1);
