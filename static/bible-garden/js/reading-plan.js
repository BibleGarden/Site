(() => {
    const plan = document.querySelector('.reading-plans[data-reading-plan]');
    if (!plan) return;

    const single = plan.dataset.readingPlan === 'chronological-bible-reading-plan';
    if (!single && plan.dataset.readingPlan !== 'bible-in-a-year') {
        throw new Error('Unknown reading plan calendar');
    }

    const input = plan.querySelector('.reading-plan-start-date');
    const switcher = plan.querySelector('.reading-plan-switcher');
    if (!input || (single ? switcher !== null : switcher === null)) {
        throw new Error('Invalid reading plan controls');
    }
    const radios = single ? [] : [...switcher.querySelectorAll('input[name="reading-plan-mode"]')];
    const blockLength = Number(plan.dataset.blockLength);
    const calendars = [...plan.querySelectorAll('.reading-plan[data-plan-kind]')].map((section) => {
        const blocks = section.querySelector('.reading-plan-blocks');
        return {
            section,
            blocks,
            rows: [...blocks.querySelectorAll('tr[data-day]')],
            header: blocks.querySelector('thead').cloneNode(true),
        };
    });
    if (calendars.length !== (single ? 1 : 2) || !Number.isInteger(blockLength) || blockLength < 1 ||
        calendars.some((calendar) => calendar.rows.length !== 365) ||
        calendars.map((calendar) => calendar.section.dataset.planKind).sort().join(',') !== (single ? 'chronological' : 'parallel,sequential')) {
        throw new Error('Invalid reading plan calendar markup');
    }

    const locale = { en: 'en', ru: 'ru', uk: 'uk' }[plan.lang];
    const dateFormatter = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', timeZone: 'UTC' });
    const monthFormatter = new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric', timeZone: 'UTC' });
    const dateStorageKey = single ? 'bible-garden-chronological-reading-plan-start' : 'bible-garden-reading-plan-start';
    const modeStorageKey = 'bible-garden-reading-plan-mode';

    function parseDate(value) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
        const date = new Date(`${value}T00:00:00Z`);
        if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) return null;
        return date;
    }

    function dayAt(start, offset) {
        const date = new Date(start);
        date.setUTCDate(start.getUTCDate() + offset);
        return date;
    }

    function fillTemplate(template, values) {
        return template.replace(/\{(month|first|last)\}/g, (_, key) => values[key]);
    }

    function calendarGroups(calendar, start) {
        const groups = [];
        calendar.rows.forEach((row, index) => {
            const date = dayAt(start, index);
            row.querySelector('.reading-plan-date').textContent = dateFormatter.format(date);
            const key = `${date.getUTCFullYear()}-${date.getUTCMonth()}`;
            if (!groups.length || groups[groups.length - 1].key !== key) {
                const monthPart = monthFormatter.formatToParts(date).find((part) => part.type === 'month');
                if (!monthPart) throw new Error(`Missing standalone month name for ${locale}`);
                const month = monthPart.value;
                const year = date.getUTCFullYear();
                groups.push({
                    key,
                    rows: [],
                    label: `${month[0].toLocaleUpperCase(locale)}${month.slice(1)} ${year}`,
                    month: `${month} ${year}`,
                });
            }
            groups[groups.length - 1].rows.push(row);
        });
        return groups.map((group) => ({
            rows: group.rows,
            label: group.label,
            caption: fillTemplate(plan.dataset.captionMonth, {
                month: group.month,
                first: group.rows[0].dataset.day,
                last: group.rows[group.rows.length - 1].dataset.day,
            }),
        }));
    }

    function numberedGroups(calendar) {
        calendar.rows.forEach((row) => { row.querySelector('.reading-plan-date').textContent = ''; });
        const groups = [];
        for (let offset = 0; offset < calendar.rows.length; offset += blockLength) {
            const groupRows = calendar.rows.slice(offset, offset + blockLength);
            const bounds = { first: groupRows[0].dataset.day, last: groupRows[groupRows.length - 1].dataset.day };
            groups.push({
                rows: groupRows,
                label: fillTemplate(plan.dataset.daysLabel, bounds),
                caption: fillTemplate(plan.dataset.captionDays, bounds),
            });
        }
        return groups;
    }

    function renderGroups(calendar, groups) {
        const fragment = document.createDocumentFragment();
        groups.forEach((group, index) => {
            const details = document.createElement('details');
            details.className = 'reading-plan-month';
            details.open = index === 0;
            const summary = document.createElement('summary');
            summary.textContent = group.label;
            details.appendChild(summary);
            const body = document.createElement('div');
            body.className = 'reading-plan-month-body';
            const table = document.createElement('table');
            const caption = document.createElement('caption');
            caption.className = 'sr-only';
            caption.textContent = group.caption;
            table.appendChild(caption);
            table.appendChild(calendar.header.cloneNode(true));
            const tbody = document.createElement('tbody');
            group.rows.forEach((row) => tbody.appendChild(row));
            table.appendChild(tbody);
            body.appendChild(table);
            details.appendChild(body);
            fragment.appendChild(details);
        });
        calendar.blocks.replaceChildren(fragment);
    }

    function updateDate(value) {
        const start = parseDate(value);
        calendars.forEach((calendar) => renderGroups(calendar, start ? calendarGroups(calendar, start) : numberedGroups(calendar)));
    }

    function updateSelection() {
        if (single) {
            calendars[0].section.hidden = false;
            return;
        }
        const selected = radios.find((radio) => radio.checked);
        if (!selected) throw new Error('No reading plan selected');
        calendars.forEach((calendar) => { calendar.section.hidden = calendar.section.dataset.planKind !== selected.value; });
    }

    const today = new Date();
    const localToday = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    let savedDate = null;
    let savedMode = null;
    try {
        savedDate = localStorage.getItem(dateStorageKey);
    } catch (error) {
        console.warn('Reading plan date storage is unavailable', error);
    }
    if (!single) {
        try {
            savedMode = localStorage.getItem(modeStorageKey);
        } catch (error) {
            console.warn('Reading plan mode storage is unavailable', error);
        }
    }
    input.value = parseDate(savedDate) ? savedDate : localToday;
    if (savedMode === 'parallel' || savedMode === 'sequential') {
        radios.find((radio) => radio.value === savedMode).checked = true;
    }
    updateDate(input.value);
    updateSelection();
    if (!single) switcher.hidden = false;

    input.addEventListener('change', () => {
        updateDate(input.value);
        try {
            localStorage.setItem(dateStorageKey, input.value);
        } catch (error) {
            console.warn('Reading plan date storage is unavailable', error);
        }
    });
    radios.forEach((radio) => radio.addEventListener('change', () => {
        if (!radio.checked) return;
        updateSelection();
        try {
            localStorage.setItem(modeStorageKey, radio.value);
        } catch (error) {
            console.warn('Reading plan mode storage is unavailable', error);
        }
    }));

    plan.querySelector('.reading-plan-print').addEventListener('click', () => window.print());
    let printedBlocks = null;
    let previousOpen = [];
    window.addEventListener('beforeprint', () => {
        printedBlocks = calendars.find((calendar) => !calendar.section.hidden).blocks;
        const months = [...printedBlocks.querySelectorAll('.reading-plan-month')];
        previousOpen = months.map((month) => month.open);
        months.forEach((month) => { month.open = true; });
    });
    window.addEventListener('afterprint', () => {
        if (!printedBlocks) return;
        printedBlocks.querySelectorAll('.reading-plan-month').forEach((month, index) => { month.open = previousOpen[index]; });
        printedBlocks = null;
    });
})();
