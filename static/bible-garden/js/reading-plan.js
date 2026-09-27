(() => {
    const plan = document.querySelector('[data-reading-plan="bible-in-a-year"]');
    if (!plan) return;

    const input = plan.querySelector('.reading-plan-start-date');
    const blocks = plan.querySelector('.reading-plan-blocks');
    const rows = [...blocks.querySelectorAll('tr[data-day]')];
    const header = blocks.querySelector('thead').cloneNode(true);
    const blockLength = Number(plan.dataset.blockLength);
    if (rows.length !== 365 || !Number.isInteger(blockLength) || blockLength < 1) {
        throw new Error('Invalid reading plan calendar markup');
    }
    const locale = { en: 'en', ru: 'ru', uk: 'uk' }[plan.lang];
    const dateFormatter = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', timeZone: 'UTC' });
    const monthFormatter = new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric', timeZone: 'UTC' });
    const storageKey = 'bible-garden-reading-plan-start';

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

    function calendarGroups(start) {
        const groups = [];
        rows.forEach((row, index) => {
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

    function numberedGroups() {
        rows.forEach((row) => { row.querySelector('.reading-plan-date').textContent = ''; });
        const groups = [];
        for (let offset = 0; offset < rows.length; offset += blockLength) {
            const groupRows = rows.slice(offset, offset + blockLength);
            const bounds = { first: groupRows[0].dataset.day, last: groupRows[groupRows.length - 1].dataset.day };
            groups.push({
                rows: groupRows,
                label: fillTemplate(plan.dataset.daysLabel, bounds),
                caption: fillTemplate(plan.dataset.captionDays, bounds),
            });
        }
        return groups;
    }

    function renderGroups(groups) {
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
            table.appendChild(header.cloneNode(true));
            const tbody = document.createElement('tbody');
            group.rows.forEach((row) => tbody.appendChild(row));
            table.appendChild(tbody);
            body.appendChild(table);
            details.appendChild(body);
            fragment.appendChild(details);
        });
        blocks.replaceChildren(fragment);
    }

    function update(value) {
        const start = parseDate(value);
        renderGroups(start ? calendarGroups(start) : numberedGroups());
    }

    const today = new Date();
    const localToday = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    let saved = null;
    try {
        saved = localStorage.getItem(storageKey);
    } catch (error) {
        console.warn('Reading plan date storage is unavailable', error);
    }
    input.value = parseDate(saved) ? saved : localToday;
    update(input.value);
    input.addEventListener('change', () => {
        update(input.value);
        try {
            localStorage.setItem(storageKey, input.value);
        } catch (error) {
            console.warn('Reading plan date storage is unavailable', error);
        }
    });

    plan.querySelector('.reading-plan-print').addEventListener('click', () => window.print());
    let previousOpen = [];
    window.addEventListener('beforeprint', () => {
        const months = [...blocks.querySelectorAll('.reading-plan-month')];
        previousOpen = months.map((month) => month.open);
        months.forEach((month) => { month.open = true; });
    });
    window.addEventListener('afterprint', () => {
        blocks.querySelectorAll('.reading-plan-month').forEach((month, index) => { month.open = previousOpen[index]; });
    });
})();
