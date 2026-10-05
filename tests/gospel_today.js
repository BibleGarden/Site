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
const month = {schema_version: 1, calendar: 'julian', translation: 'syn', month: '2026-10', days: {'2026-10-05': day, '2026-10-06': day, '2026-10-31': day}, passages: texts.passages};
assert.equal(selectDay(month, '2026-10-05', config), day);
assert.throws(() => selectDay(month, '2031-01-01', config), RangeError);
assert.throws(() => selectDay(month, '2026-10-07', config));
assert.throws(() => selectDay({...month, passages: {}}, '2026-10-05', config));
assert.throws(() => selectDay({...month, calendar: 'newjulian'}, '2026-10-05', config));
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
    const key = url.split('/').pop().slice(0, -5);
    return {ok: true, json: async () => ({...month, month: key, days: key === '2026-10' ? month.days : {[key + '-01']: day}})};
  }, () => clock);
  await settle();
  assert.equal(root.nodes['[data-gospel-status]'].textContent, '2026-10-05');
  assert.equal(root.nodes['[data-gospel-status]'].hidden, true);
  assert.equal(calls.length, 1);
  await client.refresh(); assert.equal(calls.length, 1);
  clock = new Date(2026, 9, 6, 0);
  await client.refresh(); assert.equal(calls.length, 1);
  assert.equal(root.nodes['[data-gospel-status]'].textContent, '2026-10-06');
  clock = new Date(2026, 10, 1, 0);
  listeners.visibilitychange(); await settle();
  assert.equal(calls.length, 2);
  assert.equal(calls[1], '/data/gospel-today/ru/2026-11.json');
  assert.equal(root.nodes['[data-gospel-status]'].textContent, '2026-11-01');
  clock = new Date(2027, 0, 1, 0);
  listeners.visibilitychange(); await settle();
  assert.equal(calls.length, 3);
  assert.equal(calls[2], '/data/gospel-today/ru/2027-01.json');
  assert.equal(root.nodes['[data-gospel-status]'].textContent, '2027-01-01');
  client.dispose();
  const bad = rootFor(config);
  const badClient = mount(bad, document, async () => ({ok: true, json: async () => month}), () => new Date(2026, 10, 1));
  const originalError = console.error; let errors = [];
  console.error = (...values) => errors.push(values);
  await settle();
  assert.equal(bad.nodes['[data-gospel-status]'].textContent, 'failed');
  assert.equal(bad.nodes['[data-gospel-status]'].hidden, false);
  assert.equal(bad.nodes['[data-gospel-status]'].attrs.role, 'alert');
  assert.equal(bad.nodes['[data-gospel-readings]'].children.length, 0);
  assert.equal(errors.length, 1);
  badClient.dispose();
  const outside = rootFor(config);
  const expired = mount(outside, document, () => { throw new Error('must not fetch'); }, () => new Date(2031, 0, 1));
  await settle(); assert.equal(outside.nodes['[data-gospel-status]'].textContent, 'outside range'); expired.dispose();
  const failed = rootFor(config);
  const failure = mount(failed, document, async () => ({ok: false, status: 404}), () => new Date(2026, 9, 5));
  await settle(); assert.equal(failed.nodes['[data-gospel-status]'].textContent, 'failed'); failure.dispose();
  console.error = originalError;
  global.setTimeout = originalTimeout; global.clearTimeout = originalClear;
  // Exercise every public month and every kind with the real build output.
  for (const lang of ['ru', 'uk']) {
    const base = path.join(__dirname, '../dist/bible-garden/data/gospel-today', lang);
    assert.equal(fs.readdirSync(base).length, 60);
    for (const filename of fs.readdirSync(base)) {
      assert.match(filename, /^20[0-9]{2}-[0-9]{2}\.json$/);
      const monthly = JSON.parse(fs.readFileSync(path.join(base, filename), 'utf8'));
      for (const [date, reading] of Object.entries(monthly.days)) {
        const selected = selectDay(monthly, date, {...config, lang});
        assert.ok(renderReadings(document, selected, monthly, date, strings).allText());
        assert.equal(selected, reading);
      }
    }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
