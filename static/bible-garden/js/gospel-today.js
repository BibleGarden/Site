/* One civil date and page calendar; independently selected text and aligned voice. */
(function () {
  'use strict';
  const STORAGE_KEY = 'bible-garden-readings-edition';
  const locales = {ru: 'ru-RU', uk: 'uk-UA'};
  function localDate(now) {
    if (!Number.isFinite(now.getTime())) throw new Error('Invalid clock');
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
  function humanDate(date, lang) {
    const value = new Date(date + 'T12:00:00Z');
    if (!(lang in locales) || !Number.isFinite(value.getTime()) || value.toISOString().slice(0, 10) !== date) throw new Error('Invalid date or language');
    return new Intl.DateTimeFormat(locales[lang], {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'}).format(value).replace(/ [гр]\.$/, '');
  }
  function midnightDelay(now) {
    return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime() - now.getTime() + 50;
  }
  function validChoice(choice, config) {
    return Array.isArray(choice) && choice.length === 2 && Object.hasOwn(config.editions, choice[0]) &&
      Object.hasOwn(config.editions[choice[0]].voices, choice[1]);
  }
  function savedChoice(config, storage) {
    let stored = null;
    try { stored = storage.getItem(STORAGE_KEY); } catch (_) { /* Browser privacy can deny persistence. */ }
    if (stored !== null) {
      let choice;
      try { choice = JSON.parse(stored); } catch (_) { throw new Error('Invalid saved reading choice'); }
      if (!validChoice(choice, config)) throw new Error('Unavailable saved reading choice');
      return choice;
    }
    return [...config.defaults[config.lang]];
  }
  function orderedReadings(day, strings) {
    const result = [];
    const push = (id, title, group) => {
      if (id === null || id === undefined) return;
      if (typeof id !== 'string' || !id) throw new Error('Invalid reading reference');
      result.push({id, title, group});
    };
    for (const item of day.items) {
      if (!Object.hasOwn(strings, item.kind)) throw new Error('Invalid reading kind');
      const group = item.name || strings[item.kind];
      push(item.apostle, strings.apostle, group);
      push(item.gospel, strings.gospel, group);
      (item.gospel_composite || []).forEach(id => push(id, strings.gospel, group));
      (item.ot || []).forEach(id => push(id, strings.ot, group));
      (item.hours || []).forEach(hour => {
        const title = `${group} · ${strings.hour.replace('{hour}', String(hour.hour))}`;
        push(hour.apostle, strings.apostle, title); push(hour.gospel, strings.gospel, title);
      });
    }
    return result;
  }
  function mappedRanges(ref, translation) {
    const ranges = [];
    for (const [c1,v1,c2,v2] of ref.ranges) {
      if (translation === 'ubh' && ref.book === 45 && c2 === 14 && v2 > 23) {
        if (c1 !== 14 || v2 > 26) throw new Error('Unmapped Romans reference');
        if (v1 <= 23) ranges.push([14,v1,14,23]);
        ranges.push([16,Math.max(v1,24)+1,16,v2+1]);
      } else ranges.push([c1,v1,c2,v2]);
    }
    return ranges;
  }
  function selectSchedule(schedule, date, config) {
    const year = Number(date.slice(0,4)), month = Number(date.slice(5,7));
    if (!schedule || schedule.schema_version !== 3 || schedule.calendar !== (config.lang === 'ru' ? 'julian' : 'newjulian') ||
        schedule.year !== year || schedule.month !== month || !schedule.days || !schedule.references) throw new Error('Invalid monthly schedule');
    const count = new Date(year,month,0).getDate();
    const dates = Array.from({length:count},(_,i)=>`${date.slice(0,7)}-${String(i+1).padStart(2,'0')}`);
    if (Object.keys(schedule.days).sort().join() !== dates.join()) throw new Error('Missing monthly dates');
    for (const ref of Object.values(schedule.references)) {
      if (!ref || !Number.isInteger(ref.book) || ref.book < 1 || ref.book > 66 || !Array.isArray(ref.ranges) || !ref.ranges.length ||
          ref.ranges.some(r=>!Array.isArray(r) || r.length!==4 || !r.every(v=>Number.isInteger(v) && v>0) || r[0]>r[2] || (r[0]===r[2] && r[1]>r[3]))) throw new Error('Invalid schedule reference');
    }
    const day = schedule.days[date];
    if (!day || !Array.isArray(day.items)) throw new Error('Missing schedule day');
    return day;
  }
  function chapterKeys(day, references, translation, strings) {
    const keys = new Set();
    for (const {id} of orderedReadings(day,strings)) {
      const ref = references[id];
      if (!ref) throw new Error('Missing reading reference');
      for (const [c1,,c2] of mappedRanges(ref,translation)) for (let c=c1;c<=c2;c++) keys.add(`${ref.book}/${c}`);
    }
    return [...keys];
  }
  function validateChapter(data, translation, book, chapter, config) {
    if (!data || Object.keys(data).sort().join() !== ['schema_version','translation','book','chapter','book_name','abbr','unavailable','verses','audio'].sort().join() || data.schema_version!==3 || data.translation!==translation || data.book!==book || data.chapter!==chapter ||
        typeof data.book_name !== 'string' || !data.book_name.trim() || typeof data.abbr !== 'string' || !data.abbr.trim() || !Array.isArray(data.verses) || !data.audio ||
        Object.keys(data.audio).sort().join()!==Object.keys(config.editions[translation].voices).sort().join() ||
        ![null,'missing_text','numbering'].includes(data.unavailable) || Boolean(data.verses.length)!==(data.unavailable===null)) throw new Error('Invalid chapter asset');
    let previous=0;
    for (const v of data.verses) {
      if (!Array.isArray(v) || v.length!==3 || !Number.isInteger(v[0]) || !Number.isInteger(v[1]) ||
          v[0]<=previous || v[1]<v[0] || typeof v[2]!=='string' || !v[2].trim()) throw new Error('Invalid chapter verse');
      previous=v[0];
    }
    for (const segments of Object.values(data.audio)) {
      if (!Array.isArray(segments) || segments.length!==data.verses.length || segments.some(v=>v!==null &&
          (!Array.isArray(v) || v.length!==2 || !v.every(Number.isFinite) || v[0]<0 || v[0]>=v[1]))) throw new Error('Invalid chapter alignment');
    }
    return data;
  }
  function assembleDay(schedule, chapters, date, config, choice) {
    const day=selectSchedule(schedule,date,config), passages={};
    for (const {id} of orderedReadings(day,config.strings)) {
      if (Object.hasOwn(passages,id)) continue;
      const ref=schedule.references[id], ranges=mappedRanges(ref,choice[0]);
      const first=chapters[`${ref.book}/${ranges[0][0]}`];
      if (!first) throw new Error('Missing chapter asset');
      const label=first.abbr+' '+ranges.map(([c1,v1,c2,v2])=>`${c1}:${v1}`+((c1===c2 && v1===v2)?'':`–${c1===c2?v2:c2+':'+v2}`)).join('; ');
      const p={book:ref.book,ranges:ref.ranges,display_ranges:ranges,label,book_name:first.book_name,verses:[],audio:Object.fromEntries(Object.keys(first.audio).map(v=>[v,[]]))};
      const seen=new Set(); let reason=null;
      for (const [c1,v1,c2,v2] of ranges) for (let c=c1;c<=c2;c++) {
        const data=chapters[`${ref.book}/${c}`];
        if (!data) throw new Error('Missing chapter asset');
        if (data.unavailable) {reason=data.unavailable==='numbering'?'numbering':reason || data.unavailable;continue;}
        const low=c===c1?v1:1, high=c===c2?v2:Math.max(...data.verses.map(v=>v[1]));
        const covered=new Set();
        data.verses.forEach(([first,last,text],i)=>{
          if (first>high || last<low) return;
          for (let n=Math.max(low,first);n<=Math.min(high,last);n++) covered.add(n);
          if (seen.has(`${c}/${first}`)) return;
          seen.add(`${c}/${first}`);p.verses.push([c,first,last,text]);
          for (const voice of Object.keys(p.audio)) p.audio[voice].push(data.audio[voice][i]);
        });
        if (high<low || covered.size!==high-low+1) reason=reason || 'missing_text';
      }
      if (reason) passages[id]={book:ref.book,ranges:ref.ranges,label,book_name:first.book_name,unavailable:reason};
      else {
        for (const voice of Object.keys(p.audio)) if (p.audio[voice].includes(null)) p.audio[voice]=null;
        passages[id]=p;
      }
    }
    return {schema_version:3,calendar:schedule.calendar,date,translation:choice[0],day,passages};
  }
  function selectDay(daily, date, config, choice) {
    humanDate(date, config.lang);
    const year = Number(date.slice(0, 4));
    if (year < config.start_year || year > config.end_year) throw new RangeError(config.strings.out_of_range);
    if (!validChoice(choice, config) || daily.schema_version !== 3 || daily.date !== date || daily.translation !== choice[0] ||
        daily.calendar !== (config.lang === 'ru' ? 'julian' : 'newjulian') || !daily.day || !daily.passages) throw new Error('Invalid daily assets');
    const day = daily.day;
    if (!day || !Array.isArray(day.items) || !day.items.length || typeof day.uncertain !== 'boolean' ||
        !Array.isArray(day.confirmed_by) || (config.lang === 'uk' && !day.uncertain && !day.confirmed_by.length)) throw new Error('Invalid calendar day');
    const allowed = ['kind','id','name','note','apostle','gospel','ot','gospel_composite','hours'];
    for (const item of day.items) {
      if (!item || typeof item !== 'object' || Object.keys(item).some(k => !allowed.includes(k)) ||
          !['ordinary','feast','special','triodion','pentecostarion','royal_hours'].includes(item.kind)) throw new Error('Invalid reading item');
      for (const key of ['ot','gospel_composite']) {
        if (Object.hasOwn(item,key) && (!Array.isArray(item[key]) || !item[key].length)) throw new Error('Empty reading list');
      }
      if (Object.hasOwn(item,'hours') && (!Array.isArray(item.hours) || item.hours.length !== 4 ||
          item.hours.map(h=>h.hour).join() !== '1,3,6,9' || item.hours.some(h=>!h.apostle || !h.gospel))) throw new Error('Invalid Royal Hours');
      if (!orderedReadings({items:[item]},config.strings).length) throw new Error('Empty reading item');
    }
    const edition = config.editions[choice[0]];
    for (const {id} of orderedReadings(day, config.strings)) {
      const p = daily.passages[id];
      if (!p || !Number.isInteger(p.book) || p.book < 1 || p.book > 66 || !Array.isArray(p.ranges)) throw new Error('Invalid passage');
      if (Object.hasOwn(p, 'unavailable')) {
        if (!['missing_text', 'numbering'].includes(p.unavailable)) throw new Error('Invalid coverage reason');
        continue;
      }
      if (!p.label || !p.book_name || !Array.isArray(p.verses) || !p.verses.length || p.verses.some(v =>
        !Array.isArray(v) || v.length !== 4 || !v.slice(0, 3).every(n => Number.isInteger(n) && n > 0) || v[1] > v[2] || typeof v[3] !== 'string' || !v[3].trim())) throw new Error('Invalid passage text');
      if (!p.audio || Object.keys(p.audio).sort().join() !== Object.keys(edition.voices).sort().join()) throw new Error('Invalid passage voices');
      for (const segments of Object.values(p.audio)) {
        if (segments === null) continue;
        if (!Array.isArray(segments) || segments.length !== p.verses.length || segments.some(s =>
          !Array.isArray(s) || s.length !== 2 || !s.every(Number.isFinite) || s[0] < 0 || s[0] >= s[1])) throw new Error('Invalid passage alignment');
      }
    }
    return day;
  }
  function renderReadings(document, day, daily, strings, audioConfig, choice) {
    if (!audioConfig || !Array.isArray(audioConfig.books) || audioConfig.books.length !== 66 || !audioConfig.books.every(n => Number.isInteger(n) && n > 0 && n <= 66)) throw new Error('Missing API book mapping');
    const playlist = [], lines = [], cards = [], jumps = [];
    const fragment = document.createDocumentFragment();
    const add = (tag, text, parent = fragment, cls = '') => {
      const node = document.createElement(tag); node.textContent = text; node.className = cls; parent.appendChild(node); return node;
    };
    if (day.uncertain) add('p', strings.uncertain, fragment, 'gospel-notice');
    if (day.note) {
      if (!Object.hasOwn(strings, day.note)) throw new Error('Unknown daily note');
      add('p', strings[day.note], fragment, 'gospel-notice');
    }
    const wrapper = add('div', '', fragment, 'gospel-audio-controls');
    const row = add('div', '', wrapper, 'gospel-player-row');
    const button = add('button', '▶', row, 'gospel-player-toggle'); button.type = 'button';
    const progress = add('input', '', row); progress.type = 'range'; progress.min = 0; progress.step = 0.1;
    progress.setAttribute('aria-label', strings.audio_progress);
    const time = add('output', '', row, 'gospel-player-time');
    const current = add('p', '', wrapper, 'gospel-player-current');
    const error = add('p', '', wrapper); error.hidden = true; error.setAttribute('role', 'alert');
    const status = add('span', '', wrapper, 'sr-only'); status.setAttribute('aria-live', 'polite');
    const controls = {button, progress, time, error, status, current, wrapper, jumps, cards, icon: true};
    let firstPassage = null, lastGroup = null;
    const noted = new Set();
    for (const item of day.items) {
      if (item.note && !noted.has(item.note)) {
        if (!Object.hasOwn(strings, item.note)) throw new Error('Unknown reading note');
        add('p', strings[item.note], fragment, 'gospel-notice'); noted.add(item.note);
      }
    }
    for (const reading of orderedReadings(day, strings)) {
      if (reading.group !== lastGroup) { add('h3', reading.group, fragment, 'gospel-reading-group'); lastGroup = reading.group; }
      const p = daily.passages[reading.id];
      const card = add('section', '', fragment, 'gospel-reading');
      card.lang = choice[0] === 'syn' || choice[0] === 'bti' ? 'ru' : choice[0] === 'ubh' || choice[0] === 'npu' ? 'uk' : 'en';
      const head = add('div', '', card, 'gospel-reading-heading');
      const reference = p.label || `${p.book} · ${p.ranges.map(r => `${r[0]}:${r[1]}–${r[2]}:${r[3]}`).join('; ')}`;
      const heading = add('div', '', head, 'gospel-reading-meta');
      add('span', reading.title, heading, 'gospel-reading-kind');
      add('h4', reference, heading);
      const available = !p.unavailable && p.audio[choice[1]] !== null;
      if (available) {
        const jump = add('button', '▶', head, 'gospel-reading-play'); jump.type = 'button';
        jump.setAttribute('aria-label', strings.reading_play.replace('{reading}', reference));
        jumps.push({button: jump, index: playlist.length});
      } else {
        add('p', strings[p.unavailable || 'missing_audio'], card, 'gospel-unavailable');
      }
      if (p.unavailable) continue;
      if (!firstPassage) firstPassage = p;
      const paragraph = add('p', '', card, 'gospel-reading-text');
      p.verses.forEach(([chapter, first, last, text], index) => {
        const line = add('span', '', paragraph, 'gospel-audio-line');
        const label = `${chapter}:${first}${last === first ? '' : `–${last}`}`;
        add('sup', label + ' ', line);
        line.appendChild(document.createTextNode(text + ' '));
        if (available) {
          line.setAttribute('data-audio-label', `${p.book_name} ${label}`);
          const [begin, end] = p.audio[choice[1]][index];
          const url = new URL(`${audioConfig.base_url}/api/audio/${choice[0]}/${choice[1]}/${String(audioConfig.books[p.book - 1]).padStart(2, '0')}/${String(chapter).padStart(2, '0')}.mp3`);
          url.searchParams.set('api_key', audioConfig.site_key);
          playlist.push({begin, end, url: url.href, reading: `${reading.title} · ${reference}`}); lines.push(line); cards.push(card);
        }
      });
    }
    if (!playlist.length) { wrapper.hidden = true; add('p', strings.nothing_playable, fragment, 'gospel-unavailable'); }
    fragment.gospelAudio = playlist.length ? {controls, playlist, lines} : null;
    fragment.appHint = firstPassage ? strings.app_hint.replace('{book}', firstPassage.book_name).replace('{chapter}', String(firstPassage.verses[0][0])).replace('{verse}', String(firstPassage.verses[0][1])) : '';
    return fragment;
  }
  function mount(root, document, fetcher, now = () => new Date(), storage) {
    if (storage === undefined) {
      try { storage = typeof window === 'undefined' ? null : window.localStorage; } catch (_) { storage = null; }
    }
    const config = JSON.parse(root.querySelector('[data-gospel-config]').textContent);
    const status = root.querySelector('[data-gospel-status]'), readings = root.querySelector('[data-gospel-readings]');
    const selectors = root.querySelector('[data-gospel-selectors]');
    const links = root.nextElementSibling;
    let choice, activeKey = null, token = 0, timer = null, playback = null, disposed = false;
    const cache = new Map();
    const selects = {};
    function showError(error) {
      status.hidden = false; status.textContent = error instanceof RangeError ? error.message : config.strings.error;
      status.setAttribute('role', 'alert'); console.error('gospel-today:', error);
    }
    function populate(select, entries, selected) {
      select.replaceChildren();
      entries.forEach(([value, name]) => { const option = document.createElement('option'); option.value = value; option.textContent = name; select.appendChild(option); });
      select.value = selected;
    }
    function syncSelectors() {
      const lang = config.editions[choice[0]].language;
      populate(selects.language, [['ru','Русский'],['uk','Українська'],['en','English']], lang);
      populate(selects.edition, Object.entries(config.editions).filter(([, e]) => e.language === lang).map(([key,e]) => [key,e.name]), choice[0]);
      populate(selects.narrator, Object.entries(config.editions[choice[0]].voices), choice[1]);
    }
    async function refresh() {
      if (disposed) return;
      const clock = now(), date = localDate(clock), key = `${date}/${choice.join('/')}`;
      clearTimeout(timer); timer = setTimeout(refresh, midnightDelay(clock));
      if (key === activeKey) return;
      activeKey = key;
      const request = ++token;
      if (playback) { playback.dispose(); playback = null; }
      readings.replaceChildren(); status.hidden = false; status.setAttribute('role', 'status'); status.textContent = config.strings.loading;
      root.querySelector('[data-gospel-date]').textContent = humanDate(date, config.lang);
      root.querySelector('[data-gospel-date]').dateTime = date;
      if (links) links.querySelector('[data-gospel-app-hint]').textContent = '';
      try {
        const year = clock.getFullYear();
        if (year < config.start_year || year > config.end_year) throw new RangeError(config.strings.out_of_range);
        const selected = [...choice];
        async function asset(path) {
          if (!cache.has(path)) {
            // Bounded cache shares chapters across dates and narrator changes.
            if (cache.size >= 32) cache.delete(cache.keys().next().value);
            cache.set(path, (async () => {
              const response=await fetcher(path);
              if (!response.ok) throw new Error(`Reading asset HTTP ${response.status}: ${path}`);
              return response.json();
            })());
          }
          return cache.get(path);
        }
        const schedule=await asset(`/data/gospel-today/schedule/${config.lang}/${year}/${date.slice(5,7)}.json`);
        if (request !== token || disposed) return;
        const scheduled=selectSchedule(schedule,date,config);
        const entries=await Promise.all(chapterKeys(scheduled,schedule.references,selected[0],config.strings).map(async key=>{
          const [book,chapter]=key.split('/').map(Number);
          const value=await asset(`/data/gospel-today/text/${selected[0]}/${String(book).padStart(2,'0')}/${String(chapter).padStart(2,'0')}.json`);
          return [key,validateChapter(value,selected[0],book,chapter,config)];
        }));
        const daily=assembleDay(schedule,Object.fromEntries(entries),date,config,selected);
        if (request !== token || disposed) return;
        const day = selectDay(daily, date, config, selected);
        const rendered = renderReadings(document, day, daily, config.strings, config.audio, selected);
        readings.replaceChildren(rendered);
        if (links) links.querySelector('[data-gospel-app-hint]').textContent = rendered.appHint;
        if (rendered.gospelAudio) {
          const api = typeof module !== 'undefined' && module.exports ? require('./gospel-audio.js') : window.GospelAudio;
          if (!api) throw new Error('Audio module missing');
          playback = api.mountAudio(rendered.gospelAudio.controls, rendered.gospelAudio.playlist, rendered.gospelAudio.lines, config.strings);
        }
        status.hidden = true;
      } catch (error) { if (request === token && !disposed) showError(error); }
    }
    function change(field) {
      if (field === 'language') choice = [...config.defaults[selects.language.value]];
      if (field === 'edition') choice = [selects.edition.value, Object.keys(config.editions[selects.edition.value].voices)[0]];
      if (field === 'narrator') choice[1] = selects.narrator.value;
      if (!validChoice(choice, config)) throw new Error('Invalid selected edition');
      try { storage.setItem(STORAGE_KEY, JSON.stringify(choice)); } catch (_) { /* Persistence is optional. */ }
      syncSelectors(); refresh();
    }
    try {
      choice = savedChoice(config, storage);
      for (const field of ['language','edition','narrator']) {
        const label = document.createElement('label'); label.textContent = config.strings[field];
        const select = document.createElement('select'); select.setAttribute('data-gospel-' + field, '');
        label.appendChild(select); selectors.appendChild(label); selects[field] = select;
        select.addEventListener('change', () => change(field));
      }
      syncSelectors(); selectors.hidden = false;
    } catch (error) { showError(error); return {refresh: () => {}, dispose: () => {}}; }
    const visibility = () => { if (!document.hidden) refresh(); };
    document.addEventListener('visibilitychange', visibility);
    refresh();
    return {refresh, dispose() { disposed = true; token++; clearTimeout(timer); document.removeEventListener('visibilitychange', visibility); if (playback) playback.dispose(); }};
  }
  const api = {humanDate, localDate, midnightDelay, validChoice, savedChoice, orderedReadings, selectDay, renderReadings, mount, STORAGE_KEY, mappedRanges, selectSchedule, chapterKeys, validateChapter, assembleDay};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof document !== 'undefined') document.querySelectorAll('[data-gospel-today]').forEach(root => mount(root, document, window.fetch.bind(window)));
}());
