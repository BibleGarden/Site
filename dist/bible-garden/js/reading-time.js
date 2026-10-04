/* Reading-time arithmetic is shared by the UI and Node regression tests. */
(function () {
    'use strict';
    const DAY = 86400000;
    function positive(value) {
        if (!Number.isFinite(value) || value <= 0) throw new Error('Expected a positive number');
        return value;
    }
    function date(value) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Invalid date');
        const result = new Date(`${value}T00:00:00Z`);
        if (!Number.isFinite(result.getTime()) || result.toISOString().slice(0, 10) !== value) throw new Error('Invalid date');
        return result;
    }
    function calendar(seconds, start, mode, value) {
        positive(seconds);
        const first = date(start);
        let days, minutes;
        if (mode === 'daily') {
            minutes = positive(Number(value));
            days = Math.ceil(seconds / (minutes * 60));
        } else if (mode === 'deadline') {
            days = (date(value) - first) / DAY + 1;
            positive(days);
            minutes = seconds / days / 60;
        } else throw new Error('Invalid plan mode');
        const finish = new Date(first.getTime() + (days - 1) * DAY);
        if (!Number.isFinite(finish.getTime()) || finish.getUTCFullYear() > 9999) throw new RangeError('Finish date out of range');
        return {days, minutes, finish: finish.toISOString().slice(0, 10)};
    }
    function scopeBooks(scope, book) {
        const all = Array.from({length: 66}, (_, i) => i + 1);
        if (scope === 'bible') return all;
        if (scope === 'ot') return all.filter((b) => b <= 39);
        if (scope === 'nt') return all.filter((b) => b >= 40);
        if (scope === 'gospels') return [40, 41, 42, 43];
        if (scope === 'psalms') return [19];
        if (scope === 'book' && Number.isInteger(book) && book >= 1 && book <= 66) return [book];
        throw new Error('Invalid scope');
    }
    function speed(value, multi) {
        positive(value);
        const low = multi ? .5 : .6, high = multi ? 2.5 : 2, step = multi ? .1 : .2;
        if (value < low || value > high || Math.abs((value - low) / step - Math.round((value - low) / step)) > 1e-7) throw new Error('Invalid speed');
        return value;
    }
    function pause(value) {
        if (!Number.isFinite(value) || value < 0 || value > 60) throw new Error('Invalid pause');
        return value;
    }
    function calculate(data, settings) {
        const requested = scopeBooks(settings.scope, Number(settings.book));
        if (!['listen', 'silent'].includes(settings.mode)) throw new Error('Invalid mode');
        const records = settings.mode === 'silent' ? [data.translations[settings.translation]] : [data.voices[settings.voice]];
        const multi = settings.mode === 'listen' && settings.multi;
        if (multi) records.push(data.voices[settings.voice_b]);
        if (records.some((r) => !r)) throw new Error('Unknown voice or translation');
        const books = requested.filter((b) => records.every((r) => Object.hasOwn(r.books, String(b))));
        const missing = requested.filter((b) => !books.includes(b));
        let speech = 0, pauses = 0;
        if (settings.mode === 'silent') {
            const wpm = positive(settings.wpm);
            for (const b of books) speech += records[0].books[b].words / wpm * 60;
        } else {
            for (const [index, record] of records.entries()) {
                const playback = speed(multi ? settings[index ? 'speed_b' : 'speed_a'] : settings.speed, multi);
                const unit = multi ? settings.unit : settings.pause_unit;
                if (!(multi ? ['verse','paragraph','section','chapter'] : ['none','verse','paragraph','section']).includes(unit)) throw new Error('Invalid unit');
                const wait = pause(multi ? settings[index ? 'pause_b' : 'pause_a'] : settings.pause);
                for (const b of books) {
                    const item = record.books[b];
                    speech += (multi ? item.units[unit].seconds : item.seconds) / playback;
                    if (unit !== 'none') pauses += item.units[unit].count * wait;
                }
            }
        }
        return {speech, pauses, total: speech + pauses, missing, books};
    }
    function hMM(seconds) {
        const minutes = Math.ceil(seconds / 60);
        return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
    }
    const api = {calculate, calendar, scopeBooks, hMM, date};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (typeof document === 'undefined') return;
    for (const root of document.querySelectorAll('.reading-time')) {
        const {data, strings: t, lang} = JSON.parse(root.querySelector('[data-reading-time-data]').textContent);
        const form = root.querySelector('form');
        const output = root.querySelector('.reading-time-result');
        const formatter = new Intl.DateTimeFormat(lang, {dateStyle:'medium', timeZone:'UTC'});
        const decimal = new Intl.NumberFormat(lang, {maximumFractionDigits:1});
        const el = (name) => form.elements.namedItem(name);
        const now = new Date();
        el('start').value = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
        el('finish').value = new Date(date(el('start').value).getTime()+364*DAY).toISOString().slice(0,10);
        function show(selector, visible) {
            for (const node of form.querySelectorAll(selector)) node.hidden = !visible;
        }
        function line(label, value) {
            const row = document.createElement('p');
            const title = document.createElement('strong');
            title.textContent = `${label}: `;
            row.append(title, document.createTextNode(value));
            output.append(row);
        }
        function update() {
            const listen = el('mode').value === 'listen', multi = listen && el('multi').checked;
            show('[data-listen]',listen);
            show('[data-silent]',!listen);
            show('[data-normal]',listen && !multi);
            show('[data-multi]',multi);
            show('[data-book]',el('scope').value==='book');
            show('[data-pause]',el('pause_unit').value!=='none');
            show('[data-daily]',el('plan').value==='daily');
            show('[data-deadline]',el('plan').value==='deadline');
            for (const input of form.querySelectorAll('input, select')) input.disabled = Boolean(input.closest('[hidden]'));
            el('finish').min = el('start').value;
            output.replaceChildren();
            if (!form.checkValidity()) { line(t.invalid, ''); return; }
            const settings = Object.fromEntries(new FormData(form));
            settings.multi = multi;
            for (const name of ['book','wpm','speed','pause','speed_a','speed_b','pause_a','pause_b']) {
                settings[name] = Number(el(name).value);
            }
            const result = calculate(data,settings);
            if (result.missing.length) line(t.missing,result.missing.map((b) => data.books[b-1].names[lang]).join(', '));
            if (!result.books.length || result.total === 0) { line(t.empty, ''); return; }
            let plan;
            try {
                plan = calendar(result.total,el('start').value,el('plan').value,el(el('plan').value==='daily'?'minutes':'finish').value);
            } catch (error) {
                if (!(error instanceof RangeError)) throw error;
                line(t.invalid, '');
                return;
            }
            line(t.total,hMM(result.total));
            line(t.speech,hMM(result.speech));
            line(t.pauses,hMM(result.pauses));
            line(t.days,String(plan.days));
            line(t.finish,formatter.format(date(plan.finish)));
            if (el('plan').value==='deadline') line(t.minutes_day,decimal.format(Math.ceil(plan.minutes*10)/10));
        }
        form.addEventListener('input',update);
        form.addEventListener('submit',(event) => event.preventDefault());
        form.hidden = false;
        output.hidden = false;
        update();
    }
}());
