(() => {
    const plan = document.querySelector('[data-reading-plan="bible-in-a-year"]');
    if (!plan) return;

    const input = plan.querySelector('.reading-plan-start-date');
    const cells = [...plan.querySelectorAll('tr[data-day] .reading-plan-date')];
    const locale = { en: 'en', ru: 'ru', uk: 'uk' }[plan.lang];
    const formatter = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', timeZone: 'UTC' });
    const storageKey = 'bible-garden-reading-plan-start';

    function parseDate(value) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
        const start = new Date(`${value}T00:00:00Z`);
        if (Number.isNaN(start.getTime()) || start.toISOString().slice(0, 10) !== value) return null;
        return start;
    }

    function fillDates(value) {
        const start = parseDate(value);
        cells.forEach((cell, index) => {
            if (!start) {
                cell.textContent = '';
                return;
            }
            const date = new Date(start);
            date.setUTCDate(start.getUTCDate() + index);
            cell.textContent = formatter.format(date);
        });
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
    fillDates(input.value);
    input.addEventListener('change', () => {
        fillDates(input.value);
        try {
            localStorage.setItem(storageKey, input.value);
        } catch (error) {
            console.warn('Reading plan date storage is unavailable', error);
        }
    });

    plan.querySelector('.reading-plan-print').addEventListener('click', () => window.print());
    const months = [...plan.querySelectorAll('.reading-plan-month')];
    let previousOpen = [];
    window.addEventListener('beforeprint', () => {
        previousOpen = months.map((month) => month.open);
        months.forEach((month) => { month.open = true; });
    });
    window.addEventListener('afterprint', () => {
        months.forEach((month, index) => { month.open = previousOpen[index]; });
    });
})();
