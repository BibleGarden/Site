// Exercise the real scroll handler, including pending and stale image decodes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

(async () => {
    const listeners = {};
    const positions = [500, 900, 1300];
    const label = { hidden: true };
    const pending = [];
    const images = ['bible-garden', 'lampada', 'bible-garden'].map((app, index) => {
        const classes = new Set();
        return {
            dataset: { app, src: `/screen-${index}.webp` },
            attributes: {},
            classList: { add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value) },
            hasAttribute(name) { return name === 'src' && Boolean(this.src); },
            setAttribute(name, value) { this.attributes[name] = value; },
            decode() { return new Promise(resolve => { pending[index] = resolve; }); },
        };
    });
    const desktop = { matches: true, addEventListener() {} };
    const layout = {
        querySelector() { return label; },
        querySelectorAll(selector) {
            if (selector === 'h2[data-screen]') return positions.map((_, index) => ({ getBoundingClientRect: () => ({ top: positions[index] }) }));
            if (selector === '.article-screen-phone-image') return images;
            return [];
        },
    };
    const button = { addEventListener() {} };
    const dialog = { querySelector: selector => selector === 'img' ? {} : button, addEventListener() {} };
    const frames = [];
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/bible-garden/js/article-screens.js'), 'utf8'), {
        document: { querySelector: selector => selector === '.article-screen-layout' ? layout : dialog },
        window: { innerHeight: 800, matchMedia: () => desktop, addEventListener: (name, callback) => { listeners[name] = callback; } },
        requestAnimationFrame: callback => frames.push(callback),
        console,
    });
    function scroll() { listeners.scroll(); frames.splice(0).forEach(callback => callback()); }
    async function finish(index) { pending[index](); await Promise.resolve(); }
    frames.splice(0).forEach(callback => callback());
    await finish(0);
    assert.equal(label.hidden, true);
    positions[1] = 100;
    scroll();
    assert.equal(label.hidden, true, 'Label must wait for the Lampada image decode');
    await finish(1);
    assert.equal(label.hidden, false);
    assert.equal(images[1].classList.contains('is-active'), true);
    assert.equal(images[1].attributes['aria-hidden'], 'false');
    positions[2] = 100;
    scroll();
    assert.equal(label.hidden, false, 'Keep the label while the Lampada screen is still active');
    await finish(2);
    assert.equal(label.hidden, true);
    assert.equal(images[1].attributes['aria-hidden'], 'true');
    positions[2] = 1300;
    scroll();
    positions[2] = 100;
    scroll();
    await finish(1);
    assert.equal(label.hidden, true, 'A stale Lampada decode must not restore its label');
    assert.equal(images[2].classList.contains('is-active'), true);
    desktop.matches = false;
    scroll();
    assert.equal(label.hidden, true);
})().catch(error => { console.error(error); process.exitCode = 1; });
