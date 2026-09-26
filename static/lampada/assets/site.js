(() => {
    const supportedLanguages = new Set(['en', 'ru', 'uk']);
    function normalizeLanguage(value) {
        const language = value?.toLowerCase().split('-')[0];
        return language === 'ua' ? 'uk' : language;
    }
    const queryLanguage = normalizeLanguage(new URLSearchParams(window.location.search).get('lang'));
    const storedLanguage = normalizeLanguage(localStorage.getItem('lampada-site-language'));
    const browserLanguages = (navigator.languages || [navigator.language]).map(normalizeLanguage);

    function chooseLanguage() {
        for (const candidate of [queryLanguage, storedLanguage, ...browserLanguages, 'en']) {
            if (supportedLanguages.has(candidate)) {
                return candidate;
            }
        }
        return 'en';
    }

    function setLanguage(language) {
        if (!supportedLanguages.has(language)) {
            return;
        }

        document.documentElement.lang = language;
        localStorage.setItem('lampada-site-language', language);

        document.querySelectorAll('[data-i18n]').forEach((element) => {
            const translation = element.dataset[language];
            if (translation !== undefined) {
                element.textContent = translation;
            }
        });

        document.querySelectorAll('[data-aria-en][data-aria-ru]').forEach((element) => {
            const label = element.getAttribute(`data-aria-${language}`);
            if (label) {
                element.setAttribute('aria-label', label);
            }
        });

        document.querySelectorAll('[data-lang]').forEach((button) => {
            const active = button.dataset.lang === language;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });

        const title = document.body.getAttribute(`data-title-${language}`);
        if (title) {
            document.title = title;
        }

        const description = document.querySelector('meta[name="description"]');
        const descriptionText = description?.dataset[language];
        if (description && descriptionText) {
            description.setAttribute('content', descriptionText);
        }
    }

    document.querySelectorAll('[data-lang]').forEach((button) => {
        button.addEventListener('click', () => setLanguage(button.dataset.lang));
    });

    setLanguage(chooseLanguage());
})();
