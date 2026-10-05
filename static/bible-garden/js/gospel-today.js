/* Local civil date selects committed readings. No client-side calendar arithmetic. */
(function () {
  'use strict';
  function localDate(now) {
    if (!(now instanceof Date) || !Number.isFinite(now.getTime())) throw new Error('Invalid local date');
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
  function humanDate(date, lang) {
    const locales = {ru: 'ru-RU', uk: 'uk-UA'};
    if (!locales[lang]) throw new Error('Unsupported date language');
    const value = new Date(date + 'T12:00:00Z');
    if (!Number.isFinite(value.getTime()) || value.toISOString().slice(0, 10) !== date) throw new Error('Invalid reading date');
    return new Intl.DateTimeFormat(locales[lang], {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'
    }).format(value).replace(/ [гр]\.$/, '');
  }
  function midnightDelay(now) {
    return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime() - now.getTime() + 50;
  }
  function selectDay(daily, date, config) {
    if (!['ru', 'uk'].includes(config.lang)) throw new Error('Unsupported language');
    const year = Number(date.slice(0, 4));
    if (year < config.start_year || year > config.end_year) throw new RangeError(config.strings.out_of_range);
    const calendar = config.lang === 'ru' ? 'julian' : 'newjulian';
    const translation = config.lang === 'ru' ? 'syn' : 'ubh';
    if (daily.schema_version !== 1 || daily.calendar !== calendar || daily.date !== date ||
        daily.translation !== translation) throw new Error('Invalid reading assets');
    const day = daily.day;
    if (!day || !Array.isArray(day.items) || day.items.length === 0 || typeof day.uncertain !== 'boolean' ||
        !Array.isArray(day.confirmed_by) || (config.lang === 'uk' && !day.uncertain && !day.confirmed_by.length)) {
      throw new Error('Missing or invalid daily readings');
    }
    function passage(id) {
      const p = daily.passages[id];
      if (!p || !p.label || !p.book_name || !Array.isArray(p.verses) || !p.verses.length ||
          p.verses.some(v => typeof v.text !== 'string' || !v.text.trim())) throw new Error('Missing passage text');
      if (p.book >= 40 && p.book <= 43) {
        const voice = config.lang === 'ru' ? 'prudovsky' : 'kozlov_uk';
        if (!p.audio || p.audio.translation !== translation || p.audio.voice !== voice ||
            !Array.isArray(p.audio.chapters) || JSON.stringify(p.audio.chapters) !== JSON.stringify([...new Set(p.verses.map(v => v.chapter))]) ||
            !Array.isArray(p.audio.segments) || p.audio.segments.length !== p.verses.length ||
            p.audio.segments.some((segment, index) => !segment || segment.chapter !== p.verses[index].chapter ||
              !Number.isFinite(segment.begin) || !Number.isFinite(segment.end) || segment.begin < 0 || segment.end <= segment.begin)) {
          throw new Error('Missing Gospel chapter or timecodes');
        }
      }
      return p;
    }
    day.items.forEach(item => {
      ['gospel', 'apostle'].forEach(key => { if (item[key] !== undefined && item[key] !== null) passage(item[key]); });
      ['gospel_composite', 'ot'].forEach(key => { if (item[key]) item[key].forEach(passage); });
      if (item.hours) item.hours.forEach(hour => { passage(hour.gospel); passage(hour.apostle); });
    });
    return day;
  }
  function renderReadings(document, day, texts, date, strings, audioConfig, lang) {
    const playlist = [], lines = [];
    const fragment = document.createDocumentFragment();
    const add = (tag, text, parent = fragment) => {
      const node = document.createElement(tag); node.textContent = text; parent.appendChild(node); return node;
    };
    const stamp = add('time', humanDate(date, lang)); stamp.dateTime = date;
    if (day.uncertain) add('p', strings.uncertain);
    if (day.note) {
      if (!(day.note in strings)) throw new Error('Unknown daily note');
      add('p', strings[day.note]);
    }
    let firstPassage = null;
    let controls = null;
    const hasGospel = day.items.some(item => item.gospel || item.gospel_composite || item.hours);
    if (hasGospel) {
      if (!audioConfig || typeof audioConfig.base_url !== 'string' || typeof audioConfig.site_key !== 'string' ||
          !audioConfig.site_key || /\s/.test(audioConfig.site_key)) throw new Error('Missing Gospel audio configuration');
      const wrapper = add('div', ''); wrapper.className = 'gospel-audio-controls';
      add('p', strings.audio_narrator, wrapper);
      const button = add('button', strings.audio_play, wrapper); button.type = 'button';
      const progress = add('progress', '', wrapper); progress.setAttribute('aria-label', strings.audio_progress);
      const time = add('output', '', wrapper);
      const error = add('p', '', wrapper); error.hidden = true; error.setAttribute('role', 'alert');
      const status = add('span', '', wrapper); status.className = 'sr-only'; status.setAttribute('aria-live', 'polite');
      controls = {button, progress, time, error, status, wrapper};
    }
    function show(id, title, gospel = false) {
      const p = texts.passages[id];
      add('h4', `${title}: ${p.label}`);
      const paragraph = add('p', '');
      p.verses.forEach((v, index) => {
        const line = add('span', '', paragraph);
        const label = `${v.chapter}:${v.first}${v.last === v.first ? '' : `–${v.last}`}`;
        const verse = add('span', label + ' ', line); verse.className = 'text-gray-400';
        line.appendChild(document.createTextNode(v.text + ' '));
        if (gospel) {
          line.className = 'gospel-audio-line';
          line.setAttribute('data-audio-label', `${p.book_name} ${label}`);
          const segment = p.audio.segments[index];
          const path = `${audioConfig.base_url}/api/audio/${p.audio.translation}/${p.audio.voice}/${String(p.book).padStart(2, '0')}/${String(segment.chapter).padStart(2, '0')}.mp3`;
          const url = new URL(path); url.searchParams.set('api_key', audioConfig.site_key);
          playlist.push({...segment, url: url.href}); lines.push(line);
        }
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
      if (item.gospel) show(item.gospel, strings.gospel, true);
      if (item.gospel_composite) item.gospel_composite.forEach(id => show(id, strings.gospel, true));
      if (item.apostle) show(item.apostle, strings.apostle);
      if (item.ot) item.ot.forEach(id => show(id, strings.ot));
      if (item.hours) item.hours.forEach(hour => {
        add('h4', strings.hour.replace('{hour}', String(hour.hour)));
        show(hour.gospel, strings.gospel, true); show(hour.apostle, strings.apostle);
      });
    });
    if (firstPassage) {
      const v = firstPassage.verses[0];
      add('p', strings.app_hint.replace('{book}', firstPassage.book_name).replace('{chapter}', String(v.chapter)).replace('{verse}', String(v.first)));
    }
    fragment.gospelAudio = controls ? {controls, playlist, lines} : null;
    return fragment;
  }
  function mount(root, document, fetcher, now = () => new Date()) {
    const config = JSON.parse(root.querySelector('[data-gospel-config]').textContent);
    const status = root.querySelector('[data-gospel-status]');
    const readings = root.querySelector('[data-gospel-readings]');
    let activeDate = null, token = 0, timer = null, playback = null;
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
      if (playback) { playback.dispose(); playback = null; }
      readings.replaceChildren(); status.hidden = false; status.setAttribute('role', 'status'); status.textContent = config.strings.loading;
      try {
        const year = clock.getFullYear();
        if (year < config.start_year || year > config.end_year) throw new RangeError(config.strings.out_of_range);
        const daily = await asset(date.slice(0, 4) + '/' + date.slice(5));
        const day = selectDay(daily, date, config);
        const rendered = renderReadings(document, day, daily, date, config.strings, config.audio, config.lang);
        if (request !== token) return;
        readings.replaceChildren(rendered);
        if (rendered.gospelAudio) {
          const api = typeof module !== 'undefined' && module.exports ? require('./gospel-audio.js') : window.GospelAudio;
          if (!api) throw new Error('Gospel audio module missing');
          const {controls, playlist, lines} = rendered.gospelAudio;
          playback = api.mountAudio(controls, playlist, lines, config.strings);
        }
        status.textContent = date; status.hidden = true;
      } catch (error) {
        if (request !== token) return;
        status.textContent = error instanceof RangeError ? error.message : config.strings.error;
        status.setAttribute('role', 'alert');
        console.error('gospel-today:', error);
      }
    }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    refresh();
    return {refresh, dispose: () => { clearTimeout(timer); if (playback) playback.dispose(); }};
  }
  const api = {humanDate, localDate, midnightDelay, selectDay, renderReadings, mount};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof document !== 'undefined') document.querySelectorAll('[data-gospel-today]').forEach(root => mount(root, document, window.fetch.bind(window)));
}());
