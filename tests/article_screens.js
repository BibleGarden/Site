// Exercise the real scroll handler, including pending and stale image decodes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

(async () => {
    const listeners = {};
    const positions = [500, 900, 1300, 1700];
    const headingScreens = ['screen-0', 'screen-1', 'screen-2', 'screen-0'];
    function control() {
        return {
            attributes: {},
            listeners: {},
            setAttribute(name, value) { this.attributes[name] = value; },
            removeAttribute(name) { delete this.attributes[name]; },
            addEventListener(name, callback) { this.listeners[name] = callback; },
            click() { this.listeners.click(); },
        };
    }
    const previous = control();
    const next = control();
    const dots = Array.from({ length: 3 }, control);
    const pager = {
        hidden: true,
        querySelector: selector => selector === '.article-screen-previous' ? previous : next,
    };
    const label = { hidden: true };
    const pending = [];
    const images = ['bible-garden', 'lampada', 'bible-garden'].map((app, index) => {
        const classes = new Set();
        return {
            dataset: { app, screen: headingScreens[index], src: `/screen-${index}.webp` },
            alt: 'Caption ' + index,
            attributes: {},
            classList: { add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value) },
            hasAttribute(name) { return name === 'src' && Boolean(this.src); },
            setAttribute(name, value) { this.attributes[name] = value; },
            decode() { return new Promise(resolve => { pending[index] = resolve; }); },
        };
    });
    const desktop = { matches: true, addEventListener(name, callback) { this.change = callback; } };
    const layout = {
        querySelector(selector) { return selector === '.article-screen-pager' ? pager : label; },
        querySelectorAll(selector) {
            if (selector === 'h2[data-screen]') return positions.map((_, index) => ({ dataset: { screen: headingScreens[index] }, getBoundingClientRect: () => ({ top: positions[index] }) }));
            if (selector === '.article-screen-phone-image') return images;
            if (selector === '.article-screen-dot') return dots;
            return [];
        },
    };
    const button = { addEventListener() {} };
    const dialog = { querySelector: selector => selector === 'img' ? {} : button, addEventListener() {} };
    const frames = [];
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/bible-garden/js/article-screens.js'), 'utf8'), {
        document: { querySelector: selector => selector === '.article-screen-layout' ? layout : dialog },
        window: { scrollTo() { throw new Error('Pager must not scroll the article'); }, innerHeight: 800, matchMedia: () => desktop, addEventListener: (name, callback) => { listeners[name] = callback; } },
        requestAnimationFrame: callback => frames.push(callback),
        console,
    });
    function scroll() { listeners.scroll(); frames.splice(0).forEach(callback => callback()); }
    async function finish(index) { pending[index](); await Promise.resolve(); }
    frames.splice(0).forEach(callback => callback());
    await finish(0);
    assert.equal(label.hidden, true);
    assert.equal(pager.hidden, false);
    assert.equal(previous.disabled, true);
    assert.equal(next.disabled, false);
    assert.equal(dots[0].attributes['aria-current'], 'true');
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
    assert.equal(next.disabled, true);
    assert.equal(dots[2].attributes['aria-current'], 'true');
    assert.equal(dots[1].attributes['aria-current'], undefined);

    // Manual paging keeps the article at exactly the same position.
    const before = [...positions];
    previous.click();
    assert.deepEqual(positions, before);
    assert.equal(label.hidden, true, 'Manual changes also wait for decode');
    await finish(1);
    assert.equal(label.hidden, false);
    assert.equal(images[1].alt, 'Caption 1');
    assert.equal(dots[1].attributes['aria-current'], 'true');
    scroll();
    listeners.resize();
    frames.splice(0).forEach(callback => callback());
    assert.equal(images[1].classList.contains('is-active'), true, 'Hold manual choice in the same section');
    assert.equal(previous.disabled, false);
    next.click();
    await finish(2);
    dots[0].click();
    await finish(0);
    assert.equal(label.hidden, true);
    assert.equal(previous.disabled, true);

    // Another section with a repeated screen still releases the manual hold.
    positions[3] = 100;
    scroll();
    positions[3] = 1700;
    scroll();
    await finish(2);
    assert.equal(images[2].classList.contains('is-active'), true);
    assert.equal(dots[2].attributes['aria-current'], 'true');

    // Rapid manual choices cancel stale decodes, including their label/dot updates.
    dots[1].click();
    dots[0].click();
    await finish(1);
    assert.equal(label.hidden, true);
    assert.equal(dots[2].attributes['aria-current'], 'true');
    await finish(0);
    assert.equal(dots[0].attributes['aria-current'], 'true');
    next.click();
    next.click();
    await finish(1);
    assert.equal(images[0].classList.contains('is-active'), true);
    await finish(2);
    assert.equal(images[2].classList.contains('is-active'), true);

    // Heading-to-image mapping uses ids rather than repeated heading indices.
    positions[3] = 100;
    scroll();
    await finish(0);
    assert.equal(images[0].classList.contains('is-active'), true);

    dots[1].click();
    desktop.matches = false;
    desktop.change();
    scroll();
    await finish(1);
    assert.equal(label.hidden, true, 'Entering mobile cancels pending manual decodes');
    dots[1].click();
    assert.equal(images[0].classList.contains('is-active'), true);
    desktop.matches = true;
    positions[3] = 1700;
    desktop.change();
    frames.splice(0).forEach(callback => callback());
    await finish(2);
    assert.equal(images[2].classList.contains('is-active'), true);

    // Single-screen articles have no controls and still run the same scroll handler.
    layout.querySelector = selector => selector === '.article-screen-pager' ? null : label;
    const queryAll = layout.querySelectorAll;
    layout.querySelectorAll = selector => {
        if (selector === '.article-screen-phone-image') return [images[0]];
        if (selector === 'h2[data-screen]') return [queryAll(selector)[0]];
        if (selector === '.article-screen-dot') return [];
        return queryAll(selector);
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/bible-garden/js/article-screens.js'), 'utf8'), {
        document: { querySelector: selector => selector === '.article-screen-layout' ? layout : dialog },
        window: { innerHeight: 800, matchMedia: () => desktop, addEventListener() {} },
        requestAnimationFrame: callback => callback(),
        console,
    });
    await finish(0);
    assert.equal(images[0].attributes['aria-hidden'], 'false');
})().catch(error => { console.error(error); process.exitCode = 1; });
