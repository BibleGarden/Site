'use strict';
const assert = require('node:assert/strict');
const {localDate, midnightDelay, selectDay, renderReadings, mount} = require('../static/bible-garden/js/gospel-today.js');
const date = new Date(2026, 9, 5, 23, 59, 59);
assert.equal(localDate(date), '2026-10-05');
assert.equal(midnightDelay(date), 1050);
assert.equal(localDate(new Date(2026, 11, 31, 23)), '2026-12-31');
assert.throws(() => localDate(new Date(NaN)));
const fs = require('node:fs'), path = require('node:path');
const strings = {
  out_of_range: 'outside range', loading: 'loading', error: 'failed', uncertain: 'uncertain',
  gospel: 'gospel', apostle: 'apostle', ordinary: 'ordinary', triodion: 'triodion',
  pentecostarion: 'pentecostarion', feast: 'feast', special: 'special', royal_hours: 'hours',
  no_liturgy: 'no liturgy', no_liturgy_gospel: 'no liturgy', no_liturgy_vespers_gospel: 'vespers',
  presanctified: 'presanctified', ordinary_may_be_omitted: 'omitted', ot: 'OT', hour: 'hour {hour}',
  app_hint: 'open {book} {chapter}:{verse}'
};
const config = {lang: 'ru', start_year: 2026, end_year: 2030, strings};
const texts = {schema_version: 1, translation: 'syn', passages: {p: {
  label: 'Лк 3:19–22', book_name: 'Лк', verses: [{chapter: 3, first: 19, last: 19, text: '<script>alert(1)</script>'}]
}}};
const day = {items: [{kind: 'ordinary', gospel: 'p', apostle: null}], uncertain: false, confirmed_by: []};
const schedule = {schema_version: 1, calendar: 'julian', year: 2026, days: {'2026-10-05': day}};
assert.equal(selectDay(schedule, texts, '2026-10-05', config), day);
assert.throws(() => selectDay(schedule, texts, '2031-01-01', config), RangeError);
assert.throws(() => selectDay(schedule, texts, '2026-10-06', config));
assert.throws(() => selectDay(schedule, {...texts, passages: {}}, '2026-10-05', config));
assert.throws(() => selectDay({...schedule, calendar: 'newjulian'}, texts, '2026-10-05', config));
class Node {
  constructor(tag, text = '') { this.tag = tag; this.textContent = text; this.children = []; this.attrs = {}; }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attrs[key] = value; }
  allText() { return this.textContent + this.children.map(child => child.allText()).join(''); }
}
const listeners = {};
const document = {
  hidden: false,
  createDocumentFragment: () => new Node('fragment'),
  createElement: tag => new Node(tag),
  createTextNode: text => new Node('text', text),
  addEventListener: (name, fn) => { listeners[name] = fn; }
};
const rendered = renderReadings(document, day, texts, '2026-10-05', strings);
assert.ok(rendered.allText().includes('<script>alert(1)</script>'));
assert.ok(rendered.allText().includes('open Лк 3:19'));
assert.equal(rendered.children.filter(n => n.tag === 'script').length, 0);
function rootFor(configuration) {
  const nodes = {
    '[data-gospel-config]': new Node('script', JSON.stringify(configuration)),
    '[data-gospel-status]': new Node('p', 'no JS'), '[data-gospel-readings]': new Node('div')
  };
  return {nodes, querySelector: selector => nodes[selector]};
}
const originalTimeout = global.setTimeout, originalClear = global.clearTimeout;
global.setTimeout = () => 1; global.clearTimeout = () => {};
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  let clock = new Date(2026, 9, 5, 12), calls = [];
  const root = rootFor(config);
  const client = mount(root, document, async url => {
    calls.push(url);
    return {ok: true, json: async () => url.endsWith('texts.json') ? texts : schedule};
  }, () => clock);
  await settle();
  assert.equal(root.nodes['[data-gospel-status]'].textContent, '2026-10-05');
  assert.equal(root.nodes['[data-gospel-status]'].hidden, true);
  assert.equal(calls.length, 2);
  await client.refresh(); assert.equal(calls.length, 2);
  clock = new Date(2027, 0, 1, 0);
  const originalError = console.error; let errors = [];
  console.error = (...values) => errors.push(values);
  listeners.visibilitychange(); await settle();
  assert.equal(calls.length, 3); // Texts are loaded only once; next year needs its own schedule.
  assert.equal(root.nodes['[data-gospel-status]'].textContent, 'failed');
  assert.equal(root.nodes['[data-gospel-status]'].hidden, false);
  assert.equal(root.nodes['[data-gospel-status]'].attrs.role, 'alert');
  assert.equal(root.nodes['[data-gospel-readings]'].children.length, 0);
  assert.equal(errors.length, 1);
  client.dispose();
  const outside = rootFor(config);
  const expired = mount(outside, document, () => { throw new Error('must not fetch'); }, () => new Date(2031, 0, 1));
  await settle(); assert.equal(outside.nodes['[data-gospel-status]'].textContent, 'outside range'); expired.dispose();
  const failed = rootFor(config);
  const failure = mount(failed, document, async () => ({ok: false, status: 404}), () => new Date(2026, 9, 5));
  await settle(); assert.equal(failed.nodes['[data-gospel-status]'].textContent, 'failed'); failure.dispose();
  console.error = originalError;
  global.setTimeout = originalTimeout; global.clearTimeout = originalClear;
  // Exercise every kind and every passage with real committed assets.
  for (const lang of ['ru', 'uk']) {
    const base = path.join(__dirname, '../content/bible-garden/lectionary', lang);
    const passages = JSON.parse(fs.readFileSync(path.join(base, 'texts.json'), 'utf8'));
    for (let year = 2026; year <= 2030; year++) {
      const calendar = JSON.parse(fs.readFileSync(path.join(base, `${year}.json`), 'utf8'));
      for (const [date, reading] of Object.entries(calendar.days)) {
        const selected = selectDay(calendar, passages, date, {...config, lang});
        assert.ok(renderReadings(document, selected, passages, date, strings).allText());
        assert.equal(selected, reading);
      }
    }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
