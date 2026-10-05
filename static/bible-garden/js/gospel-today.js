/* Local civil date selects committed readings. No client-side calendar arithmetic. */
(function () {
  'use strict';
  function localDate(now) {
    if (!(now instanceof Date) || !Number.isFinite(now.getTime())) throw new Error('Invalid local date');
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
  function midnightDelay(now) {
    return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime() - now.getTime() + 50;
  }
  function selectDay(schedule, texts, date, config) {
    if (!['ru', 'uk'].includes(config.lang)) throw new Error('Unsupported language');
    const year = Number(date.slice(0, 4));
    if (year < config.start_year || year > config.end_year) throw new RangeError(config.strings.out_of_range);
    const calendar = config.lang === 'ru' ? 'julian' : 'newjulian';
    const translation = config.lang === 'ru' ? 'syn' : 'ubh';
    if (schedule.schema_version !== 1 || schedule.calendar !== calendar || schedule.year !== year ||
        texts.schema_version !== 1 || texts.translation !== translation) throw new Error('Invalid reading assets');
    const day = schedule.days[date];
    if (!day || !Array.isArray(day.items) || day.items.length === 0 || typeof day.uncertain !== 'boolean' ||
        !Array.isArray(day.confirmed_by) || (config.lang === 'uk' && !day.uncertain && !day.confirmed_by.length)) {
      throw new Error('Missing or invalid daily readings');
    }
    function passage(id) {
      const p = texts.passages[id];
      if (!p || !p.label || !p.book_name || !Array.isArray(p.verses) || !p.verses.length ||
          p.verses.some(v => typeof v.text !== 'string' || !v.text.trim())) throw new Error('Missing passage text');
      return p;
    }
    day.items.forEach(item => {
      ['gospel', 'apostle'].forEach(key => { if (item[key] !== undefined && item[key] !== null) passage(item[key]); });
      ['gospel_composite', 'ot'].forEach(key => { if (item[key]) item[key].forEach(passage); });
      if (item.hours) item.hours.forEach(hour => { passage(hour.gospel); passage(hour.apostle); });
    });
    return day;
  }
  function renderReadings(document, day, texts, date, strings) {
    const fragment = document.createDocumentFragment();
    const add = (tag, text, parent = fragment) => {
      const node = document.createElement(tag); node.textContent = text; parent.appendChild(node); return node;
    };
    const stamp = add('time', date); stamp.dateTime = date;
    if (day.uncertain) add('p', strings.uncertain);
    if (day.note) {
      if (!(day.note in strings)) throw new Error('Unknown daily note');
      add('p', strings[day.note]);
    }
    let firstPassage = null;
    function show(id, title) {
      const p = texts.passages[id];
      add('h4', `${title}: ${p.label}`);
      const paragraph = add('p', '');
      p.verses.forEach(v => {
        const verse = add('span', `${v.chapter}:${v.first}${v.last === v.first ? '' : `–${v.last}`} `, paragraph);
        verse.className = 'text-gray-400';
        paragraph.appendChild(document.createTextNode(v.text + ' '));
      });
      if (!firstPassage) firstPassage = p;
    }
    day.items.forEach(item => {
      if (!(item.kind in strings)) throw new Error('Unknown daily reading kind');
      add('h3', item.name || strings[item.kind]);
      if (item.note) {
        if (!(item.note in strings)) throw new Error('Unknown reading note');
        add('p', strings[item.note]);
      }
      if (item.gospel) show(item.gospel, strings.gospel);
      if (item.gospel_composite) item.gospel_composite.forEach(id => show(id, strings.gospel));
      if (item.apostle) show(item.apostle, strings.apostle);
      if (item.ot) item.ot.forEach(id => show(id, strings.ot));
      if (item.hours) item.hours.forEach(hour => {
        add('h4', strings.hour.replace('{hour}', String(hour.hour)));
        show(hour.gospel, strings.gospel); show(hour.apostle, strings.apostle);
      });
    });
    if (firstPassage) {
      const v = firstPassage.verses[0];
      add('p', strings.app_hint.replace('{book}', firstPassage.book_name).replace('{chapter}', String(v.chapter)).replace('{verse}', String(v.first)));
    }
    return fragment;
  }
  function mount(root, document, fetcher, now = () => new Date()) {
    const config = JSON.parse(root.querySelector('[data-gospel-config]').textContent);
    const status = root.querySelector('[data-gospel-status]');
    const readings = root.querySelector('[data-gospel-readings]');
    let activeDate = null, token = 0, timer = null;
    const cache = new Map();
    function asset(name) {
      if (!cache.has(name)) cache.set(name, (async () => {
        const response = await fetcher(`/data/gospel-today/${config.lang}/${name}.json`);
        if (!response.ok) throw new Error(`Reading asset HTTP ${response.status}: ${name}`);
        return response.json();
      })());
      return cache.get(name);
    }
    async function refresh() {
      const clock = now(), date = localDate(clock);
      clearTimeout(timer);
      timer = setTimeout(refresh, midnightDelay(clock));
      if (date === activeDate) return;
      activeDate = date;
      const request = ++token;
      readings.replaceChildren(); status.hidden = false; status.setAttribute('role', 'status'); status.textContent = config.strings.loading;
      try {
        const year = clock.getFullYear();
        if (year < config.start_year || year > config.end_year) throw new RangeError(config.strings.out_of_range);
        const [schedule, texts] = await Promise.all([asset(String(year)), asset('texts')]);
        const day = selectDay(schedule, texts, date, config);
        const rendered = renderReadings(document, day, texts, date, config.strings);
        if (request !== token) return;
        readings.replaceChildren(rendered); status.textContent = date; status.hidden = true;
      } catch (error) {
        if (request !== token) return;
        status.textContent = error instanceof RangeError ? error.message : config.strings.error;
        status.setAttribute('role', 'alert');
        console.error('gospel-today:', error);
      }
    }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    refresh();
    return {refresh, dispose: () => clearTimeout(timer)};
  }
  const api = {localDate, midnightDelay, selectDay, renderReadings, mount};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof document !== 'undefined') document.querySelectorAll('[data-gospel-today]').forEach(root => mount(root, document, window.fetch.bind(window)));
}());
