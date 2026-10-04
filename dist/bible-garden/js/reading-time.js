/* Chapter-based plans; optional audio settings affect only daily listening time. */
(function () {
    'use strict';
    const DAY = 86400000;
    function integer(value) {
        if (!Number.isSafeInteger(value) || value < 1) throw new RangeError('Expected positive integer chapters');
        return value;
    }
    function date(value) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new RangeError('Invalid date');
        const result = new Date(`${value}T00:00:00Z`);
        if (!Number.isFinite(result.getTime()) || result.toISOString().slice(0,10)!==value) throw new RangeError('Invalid date');
        return result;
    }
    function calendar(total, start, driver, value) {
        integer(total);
        const first = date(start);
        let chapters;
        if (driver==='chapters') chapters = integer(Number(value));
        else if (driver==='finish') {
            const days = (date(value)-first)/DAY+1;
            integer(days);
            chapters = Math.ceil(total/days);
        } else throw new Error('Invalid calendar driver');
        const days = Math.ceil(total/chapters);
        const finish = new Date(first.getTime()+(days-1)*DAY);
        if (!Number.isFinite(finish.getTime()) || finish.getUTCFullYear()>9999) throw new RangeError('Finish date out of range');
        return {chapters, days, finish:finish.toISOString().slice(0,10)};
    }
    function scopeBooks(data, scope) {
        if (!['bible','ot','nt'].includes(scope)) throw new Error('Invalid scope');
        return data.books.filter((book)=>scope==='bible' || (book.id<=39)===(scope==='ot'));
    }
    function chapterTotal(data, scope) {
        return scopeBooks(data,scope).reduce((total,book)=>total+book.chapters,0);
    }
    function speed(value, second) {
        const low=second ? .5 : .6, high=second ? 2.5 : 2, step=second ? .1 : .2;
        if (!Number.isFinite(value) || value<low || value>high || Math.abs((value-low)/step-Math.round((value-low)/step))>1e-7) throw new Error('Invalid speed');
        return value;
    }
    function calculate(data, settings) {
        if (settings.voice==='') return null;
        const requested=scopeBooks(data,settings.scope).map((book)=>book.id);
        const records=[data.voices[settings.voice]];
        if (settings.multi) records.push(data.voices[settings.voice_b]);
        if (records.some((record)=>!record)) throw new Error('Unknown voice');
        const books=requested.filter((book)=>records.every((record)=>Object.hasOwn(record.books,String(book))));
        const missing=requested.filter((book)=>!books.includes(book));
        const recorded=books.reduce((total,book)=>total+Math.min(...records.map((record)=>record.books[book].chapters)),0);
        if (!recorded) throw new Error('No recorded chapters in supported scope');
        const unit=settings.multi?settings.unit:settings.pause_unit;
        if (!(settings.multi?['verse','paragraph','section','chapter']:['none','verse','paragraph','section']).includes(unit)) throw new Error('Invalid unit');
        const wait=unit==='none'?0:settings.pause;
        if (!Number.isFinite(wait) || wait<0 || wait>60) throw new Error('Invalid pause');
        let seconds=0;
        records.forEach((record,index)=>{
            const playback=speed(index?settings.speed_b:settings.speed,index>0);
            for (const book of books) {
                const item=record.books[book];
                seconds+=(settings.multi?item.units[unit].seconds:item.seconds)/playback;
                if (unit!=='none') seconds+=item.units[unit].count*wait;
            }
        });
        return {minutes_per_chapter:seconds/recorded/60, recorded, missing};
    }
    function format(template, values) {
        return template.replace(/\{([a-z]+)\}/g,(_match,key)=>{
            if (!Object.hasOwn(values,key)) throw new Error(`Missing format field ${key}`);
            return String(values[key]);
        });
    }
    const api={calendar,scopeBooks,chapterTotal,calculate,date};
    if (typeof module!=='undefined' && module.exports) module.exports=api;
    if (typeof document==='undefined') return;
    for (const root of document.querySelectorAll('.reading-time')) {
        const {data,strings:t,lang}=JSON.parse(root.querySelector('[data-reading-time-data]').textContent);
        const form=root.querySelector('form'), output=root.querySelector('.reading-time-result');
        const el=(name)=>form.elements.namedItem(name);
        const now=new Date();
        const start=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
        const dates=new Intl.DateTimeFormat(lang,{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
        const plurals=new Intl.PluralRules(lang);
        const noun=(number,key)=>t[key][plurals.select(number)];
        let driver='chapters';
        el('finish').min=start;
        function show(selector, visible) {
            for (const node of form.querySelectorAll(selector)) node.hidden=!visible;
        }
        function update(event) {
            if (event && event.target.name==='finish') driver='finish';
            if (event && event.target.name==='chapters_day') driver='chapters';
            const selected=el('voice').value!=='';
            const multi=selected && el('multi').checked;
            show('.reading-time-audio',selected);
            show('[data-normal]',!multi);
            show('[data-multi]',multi);
            show('[data-pause]',multi || el('pause_unit').value!=='none');
            for (const field of form.querySelectorAll('input,select')) field.disabled=Boolean(field.closest('[hidden]'));
            output.replaceChildren();
            let plan;
            try {
                plan=calendar(chapterTotal(data,el('scope').value),start,driver,el(driver==='chapters'?'chapters_day':'finish').value);
            } catch (error) {
                if (!(error instanceof RangeError)) throw error;
                output.textContent=t.invalid;
                return;
            }
            el('chapters_day').value=plan.chapters;
            if (driver==='chapters') el('finish').value=plan.finish;
            if (!form.checkValidity()) { output.textContent=t.invalid; return; }
            const values=Object.fromEntries(dates.formatToParts(date(plan.finish)).filter((part)=>['day','month','year'].includes(part.type)).map((part)=>[part.type,part.value]));
            const summary=document.createElement('p');
            summary.className='reading-time-summary';
            summary.textContent=format(t.result,{count:plan.chapters,chapters:noun(plan.chapters,'chapter_units'),date:format(t.date,values)});
            output.append(summary);
            if (!selected) return;
            const settings={scope:el('scope').value,voice:el('voice').value,multi,voice_b:el('voice_b').value,pause_unit:el('pause_unit').value,unit:el('unit').value,speed:Number(el('speed').value),speed_b:Number(el('speed_b').value),pause:Number(el('pause').value)};
            const audio=calculate(data,settings);
            const minutes=Math.round(audio.minutes_per_chapter*plan.chapters);
            summary.append(document.createTextNode(' · '+format(t.minutes_day,{minutes,unit:noun(minutes,'minute_units')})));
            const total=chapterTotal(data,settings.scope);
            if (audio.recorded!==total || audio.missing.length) {
                const note=document.createElement('p');
                note.className='reading-time-note';
                note.textContent=format(t.coverage,{recorded:audio.recorded,total});
                if (audio.missing.length) note.append(document.createTextNode(' '+t.missing+': '+audio.missing.map((book)=>data.books[book-1].names[lang]).join(', ')+'.'));
                output.append(note);
            }
        }
        form.addEventListener('input',update);
        form.addEventListener('submit',(event)=>event.preventDefault());
        form.hidden=false; output.hidden=false;
        update();
    }
}());
