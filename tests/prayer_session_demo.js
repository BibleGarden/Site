const assert = require('node:assert/strict');
const { Session, connectAudio, init } = require('../static/lampada/assets/prayer-session-demo.js');
const config = { questions: ['first', 'alternate', 'next'], sampleAnswer: 'example' };

function element(dataset = {}) {
    const handlers = {};
    const el = {
        dataset, hidden: false, disabled: false, textContent: '', value: '', open: false,
        attributes: {}, classes: new Set(), focused: false, style: {}, offsetHeight: 400,
        getBoundingClientRect() { return { width: 300, left: 20, bottom: 650 }; },
        addEventListener: (event, fn) => { (handlers[event] ||= []).push(fn); },
        emit: (event, data = {}) => { (handlers[event] || []).forEach(fn => fn(data)); },
        setAttribute(name, value) { this.attributes[name] = value; },
        replaceChildren() {}, focus() { this.focused = true; },
        click() { if (!this.disabled) this.emit('click'); },
        showModal() { this.open = true; }, close() { this.open = false; },
        querySelector() { return element(); },
        content: { cloneNode() { return {}; } },
    };
    el.classList = { toggle(name, yes) { if (yes) el.classes.add(name); else el.classes.delete(name); }, add(name) { el.classes.add(name); } };
    return el;
}
function root() {
    const nodes = new Map();
    const selectors = ['prayer-config', 'answer-input', 'takeaway', 'answer-dialog', 'notice-dialog', 'question-text', 'answer-text', 'answer-icon', 'next-icon', 'status', 'sheet-question', 'dialog-note', 'home-notice', 'complete-text', 'favorite-text', 'position'];
    nodes.set('.pd-phone', element());
    selectors.forEach(name => nodes.set(`[data-${name}]`, element()));
    nodes.get('[data-prayer-config]').textContent = JSON.stringify(config);
    ['plus','refresh','next','check','pen'].forEach(name => nodes.set(`[data-icon-${name}]`, element()));
    const actions = ['start','finish','return','complete','previous','next','answer','sample','mic','save','cancel','favorite','available','close-notice','restart'].map(name => element({ action: name }));
    actions.forEach(node => nodes.set(`[data-action="${node.dataset.action}"]`, node));
    const screens = ['home','session','reflect'].map(name => element({ screen: name }));
    ['session','reflect'].forEach(name => nodes.set(`[data-focus="${name}"]`, element()));
    const tabs = ['question','quote'].map(name => element({ tab: name }));
    const panels = ['question','quote'].map(name => element({ panel: name }));
    const el = element();
    el.dataset = { answerLabel:'Answer',editLabel:'Edit',confirmCancel:'Confirm',cancelLabel:'Cancel',saveQuoteLabel:'Save',savedQuoteLabel:'Saved',savedLabel:'Demo saved',finishLabel:'Finish',saveFinishLabel:'Save and finish' };
    el.querySelector = selector => nodes.get(selector) || null;
    el.querySelectorAll = selector => ({ '[data-screen]':screens, '[data-tab]':tabs, '[data-panel]':panels, '[data-action]':actions, '[data-action], [data-tab], textarea':[...actions,...tabs,nodes.get('[data-answer-input]'),nodes.get('[data-takeaway]')] })[selector];
    el.nodes = nodes; el.tabs = tabs;
    return el;
}

(async () => {
    assert.throws(() => new Session({}), /Invalid/);
    const state = new Session(config);
    state.next(); assert.equal(state.question, 'alternate');
    state.next(); assert.equal(state.question, 'first');
    state.openAnswer(); state.draft = 'private';
    assert.equal(state.cancel(), false); assert.equal(state.answerOpen, true);
    assert.equal(state.cancel(), true); assert.equal(state.entry.answer, null);
    state.openAnswer(); assert.throws(() => state.save(), /empty/);
    state.draft = 'saved'; state.save(); state.next(); assert.equal(state.question, 'next');
    state.previous(); assert.equal(state.entry.answer, 'saved');
    state.openAnswer(); assert.equal(state.draft, 'saved');
    state.draft = 'edited'; state.save(); assert.equal(state.entry.answer, 'edited');
    state.reset(); assert.equal(state.entry.answer, null); assert.equal(state.screen, 'home');

    global.window = { innerWidth: 375, innerHeight: 667, addEventListener() {} };
    global.document = { addEventListener() {} };
    const a = root(), b = root(); const first = init(a), second = init(b);
    const click = name => a.nodes.get(`[data-action="${name}"]`).click();
    click('start'); assert.equal(first.screen, 'session');
    a.tabs[1].click(); assert.equal(first.tab, 'quote');
    a.tabs[1].emit('keydown', { key: 'ArrowLeft', preventDefault() {} }); assert.equal(first.tab, 'question');
    click('answer'); assert.equal(a.nodes.get('[data-answer-dialog]').open, true);
    assert.equal(a.nodes.get('[data-answer-dialog]').style.left, '20px');
    assert.equal(a.nodes.get('[data-answer-dialog]').style.top, '250px');
    click('mic'); assert.equal(a.nodes.get('[data-dialog-note]').hidden, false);
    click('sample'); click('save'); assert.equal(first.entry.answer, 'example');
    assert.equal(a.nodes.get('[data-answer-text]').textContent, 'Edit');
    assert.equal(second.entry.answer, null);
    click('next'); assert.equal(first.question, 'next'); click('previous'); assert.equal(first.question, 'first');
    click('answer'); const input = a.nodes.get('[data-answer-input]'); input.value = 'changed'; input.emit('input');
    a.nodes.get('[data-answer-dialog]').emit('cancel', { preventDefault() {} });
    assert.equal(first.confirmCancel, true); assert.equal(a.nodes.get('[data-answer-dialog]').open, true);
    click('cancel'); assert.equal(a.nodes.get('[data-answer-dialog]').open, false); assert.equal(first.entry.answer, 'example');
    click('favorite'); assert.equal(a.nodes.get('[data-action="favorite"]').attributes['aria-pressed'], 'true');
    click('available'); assert.equal(a.nodes.get('[data-notice-dialog]').open, true); click('close-notice');
    click('finish'); assert.equal(first.screen, 'reflect'); click('return'); assert.equal(first.screen, 'session');
    click('finish'); const takeaway = a.nodes.get('[data-takeaway]'); takeaway.value = 'private takeaway'; takeaway.emit('input');
    assert.equal(a.nodes.get('[data-complete-text]').textContent, 'Save and finish');
    click('complete'); assert.equal(first.screen, 'home'); assert.equal(first.completed, true);
    click('restart'); assert.equal(first.completed, false); assert.equal(input.value, ''); assert.equal(takeaway.value, ''); assert.equal(first.entry.answer, null);
    assert.equal(second.screen, 'home');

    const player = element(); player.paused = true; player.currentTime = 0;
    player.pause = () => { player.paused = true; player.emit('pause'); };
    player.play = () => { player.paused = false; player.emit('playing'); return Promise.resolve(); };
    player.load = () => { player.loaded = true; };
    const labels = []; let errors = 0;
    const audio = connectAudio(player, (label, pending) => labels.push([label,pending]), () => errors++);
    await audio.toggle(); assert.equal(player.paused, false); assert.equal(labels.at(-1)[0], 'pause');
    player.currentTime = 1; await audio.toggle(); assert.equal(player.paused,true); assert.equal(labels.at(-1)[0],'resume');
    await audio.toggle(); player.paused = true; player.emit('ended'); assert.equal(player.currentTime,0);
    player.play = () => Promise.reject(new Error('Network')); await audio.toggle(); assert.equal(errors,1); assert.equal(labels.at(-1)[0],'listen');
    player.play = () => { player.paused = false; return Promise.resolve(); }; await audio.toggle(); assert.equal(player.loaded,true);
    audio.stop(); assert.equal(player.paused,true); assert.equal(player.currentTime,0);
    let resolve; player.play = () => new Promise(r => { resolve = r; });
    const pending = audio.toggle(); audio.stop(); resolve(); await pending; assert.equal(labels.at(-1)[0],'listen');
    player.emit('error'); assert.equal(errors,2);
    console.log('Prayer demo: flow, DOM actions, keyboard tabs, cancellation, instance isolation, reset, media lifecycle and errors passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
