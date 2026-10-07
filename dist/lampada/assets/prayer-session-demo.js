/* Lampada prayer session demo. Private input never leaves instance memory. */
(() => {
    'use strict';
    function greetingPeriod(hour) {
        if (hour < 5) return 'night';
        if (hour < 12) return 'morning';
        if (hour < 18) return 'afternoon';
        return 'evening';
    }
    class Session {
        constructor(config) {
            if (!config || !Array.isArray(config.questions) || config.questions.length !== 3
                || config.questions.some(q => typeof q !== 'string' || !q.trim())
                || typeof config.sampleAnswer !== 'string' || !config.sampleAnswer.trim()
                || !Array.isArray(config.week) || config.week.length !== 7 || config.week.some(v => typeof v !== 'boolean')
                || !config.greetings || ['night','morning','afternoon','evening'].some(k => typeof config.greetings[k] !== 'string')
                || !config.weekLabels || ['one','few','many','other'].some(k => typeof config.weekLabels[k] !== 'string')
                || typeof config.language !== 'string' || typeof config.lit !== 'string' || typeof config.keepFlame !== 'string') {
                throw new Error('Invalid prayer demo configuration');
            }
            this.config = config;
            this.reset();
        }
        reset(preserveHome = false) {
            this.homeLit = preserveHome ? this.homeLit : this.config.week[6];
            this.screen = 'home';
            this.tab = 'question';
            this.entries = [{ question: 0, answer: null }];
            this.index = 0;
            this.favorite = false;
            this.draft = '';
            this.confirmCancel = false;
            this.takeaway = '';
            this.completed = false;
        }
        get entry() { return this.entries[this.index]; }
        get question() { return this.config.questions[this.entry.question]; }
        next() {
            if (this.index < this.entries.length - 1) this.index++;
            else if (this.entry.answer === null) {
                this.entry.question = this.index === 0 ? (this.entry.question === 0 ? 1 : 0) : (this.entry.question === 2 ? 1 : 2);
            }
            else if (this.entries.length === 1) {
                this.entries.push({ question: 2, answer: null });
                this.index++;
            }
        }
        previous() { if (this.index > 0) this.index--; }
        openAnswer() {
            this.draft = this.entry.answer === null ? '' : this.entry.answer;
            this.confirmCancel = false;
        }
        save() {
            if (!this.draft.trim()) throw new Error('Cannot save an empty demo answer');
            this.entry.answer = this.draft;
            this.confirmCancel = false;
        }
        discardDraft() {
            this.draft = this.entry.answer === null ? '' : this.entry.answer;
            this.confirmCancel = false;
        }
        cancel() {
            const saved = this.entry.answer === null ? '' : this.entry.answer;
            if (this.draft !== saved && !this.confirmCancel) {
                this.confirmCancel = true;
                return false;
            }
            this.discardDraft();
            return true;
        }
    }

    function connectAudio(player, onChange, onError) {
        let generation = 0;
        let pending = false;
        let failed = false;
        const notify = () => onChange(player.paused ? (player.currentTime > 0 ? 'resume' : 'listen') : 'pause', pending);
        const fail = () => {
            generation++;
            pending = false;
            failed = true;
            player.pause();
            player.currentTime = 0;
            onError();
            notify();
        };
        player.addEventListener('ended', () => {
            generation++;
            pending = false;
            player.currentTime = 0;
            notify();
        });
        player.addEventListener('error', fail);
        player.addEventListener('pause', notify);
        player.addEventListener('playing', notify);
        return {
            async toggle() {
                if (pending) return;
                if (!player.paused) { generation++; player.pause(); notify(); return; }
                const token = ++generation;
                pending = true;
                onChange('listen', true);
                try {
                    if (failed) { player.load(); failed = false; }
                    await player.play();
                    if (token !== generation) return;
                    pending = false;
                    notify();
                } catch (error) {
                    if (token === generation) fail();
                }
            },
            stop() {
                generation++;
                pending = false;
                player.pause();
                player.currentTime = 0;
                notify();
            },
        };
    }

    function init(root) {
        const one = selector => {
            const node = root.querySelector(selector);
            if (!node) throw new Error(`Missing prayer demo element: ${selector}`);
            return node;
        };
        const session = new Session(JSON.parse(one('[data-prayer-config]').textContent));
        const screens = [...root.querySelectorAll('[data-screen]')];
        const tabs = [...root.querySelectorAll('[data-tab]')];
        const panels = [...root.querySelectorAll('[data-panel]')];
        const input = one('[data-answer-input]');
        const takeaway = one('[data-takeaway]');
        const answerDialog = one('[data-answer-dialog]');
        const noticeDialog = one('[data-notice-dialog]');
        const questionText = one('[data-question-text]');
        const answerLabel = one('[data-answer-text]');
        const answerIcon = one('[data-answer-icon]');
        const nextIcon = one('[data-next-icon]');
        const save = one('[data-action="save"]');
        const cancel = one('[data-action="cancel"]');
        const status = one('[data-status]');
        const answerStatus = one('[data-answer-status]');
        if (typeof root.dataset.questionLabel !== 'string' || !root.dataset.questionLabel.trim()) throw new Error('Missing question label');
        const player = root.querySelector('[data-player]');
        if (typeof answerDialog.showModal !== 'function' || typeof noticeDialog.showModal !== 'function') {
            throw new Error('Prayer demo requires native dialog support');
        }
        const audio = player ? connectAudio(player, (label, pending) => {
            one('[data-audio-label]').textContent = root.dataset[`${label}Label`];
            setIcon(one('[data-audio-icon]'), label === 'pause' ? 'pause' : 'play');
            one('[data-action="listen"]').disabled = pending;
        }, () => {
            const error = one('[data-audio-error-text]');
            error.textContent = root.dataset.audioError;
            error.hidden = false;
        }) : null;
        function stopAudio() { if (audio) audio.stop(); }
        function setIcon(target, name) { target.replaceChildren(one(`[data-icon-${name}]`).content.cloneNode(true)); }
        function render() {
            screens.forEach(node => { node.hidden = node.dataset.screen !== session.screen; });
            tabs.forEach(node => {
                const selected = node.dataset.tab === session.tab;
                node.setAttribute('aria-selected', String(selected));
                node.tabIndex = selected ? 0 : -1;
            });
            panels.forEach(node => { node.hidden = node.dataset.panel !== session.tab; });
            questionText.textContent = session.question;
            answerLabel.textContent = session.entry.answer === null ? root.dataset.answerLabel : root.dataset.editLabel;
            one('[data-action="answer"]').classList.toggle('is-answered', session.entry.answer !== null);
            setIcon(answerIcon, session.entry.answer === null ? 'pen' : 'check');
            const frontier = session.index === session.entries.length - 1;
            setIcon(nextIcon, !frontier ? 'next' : session.entry.answer === null ? 'refresh' : 'plus');
            one('[data-action="previous"]').disabled = session.index === 0;
            one('[data-action="next"]').disabled = frontier && session.index === 1 && session.entry.answer !== null;
            one('[data-position]').textContent = session.entries.map((entry, i) => i === session.index ? '●' : '○').join(' ');
            one('[data-position]').setAttribute('aria-label', `${root.dataset.questionLabel}: ${session.index + 1} / ${session.entries.length}`);
            one('[data-action="favorite"]').setAttribute('aria-pressed', String(session.favorite));
            one('[data-favorite-text]').textContent = session.favorite ? root.dataset.savedQuoteLabel : root.dataset.saveQuoteLabel;
            one('[data-home-notice]').hidden = !session.completed;
            one('[data-complete-text]').textContent = session.takeaway.trim() ? root.dataset.saveFinishLabel : root.dataset.finishLabel;
            save.disabled = !session.draft.trim();
            cancel.textContent = session.confirmCancel ? root.dataset.confirmCancel : root.dataset.cancelLabel;
            one('[data-voice-hint]').hidden = Boolean(session.draft);
            one('[data-report]').setAttribute('aria-label', session.tab === 'question' ? root.dataset.reportQuestion : root.dataset.reportScripture);
            one('[data-greeting]').textContent = session.config.greetings[greetingPeriod(new Date().getHours())];
            screens.find(node => node.dataset.screen === 'home').classList.toggle('is-lit', session.homeLit);
            one('[data-home-title]').textContent = session.homeLit ? session.config.lit : session.config.keepFlame;
            const week = [...session.config.week];
            week[6] = session.homeLit;
            root.querySelectorAll('.pd-week span').forEach((dot, i) => {
                dot.classList.toggle('pd-filled', week[i]);
                dot.classList.toggle('pd-today', i === 6 && !week[i]);
            });
            const count = week.filter(Boolean).length;
            const weekly = one('[data-week-label]');
            weekly.hidden = count === 0;
            weekly.textContent = session.config.weekLabels[new Intl.PluralRules(session.config.language).select(count)].replace('{count}', String(count));

        }
        function changeScreen(screen) {
            stopAudio();
            session.screen = screen;
            render();
            if (screen === 'home') one('[data-action="start"]').focus();
            else one(`[data-focus="${screen}"]`).focus();
        }
        function cancelAnswer() {
            if (session.cancel()) { answerDialog.close(); render(); }
            else { render(); answerStatus.textContent = root.dataset.confirmCancel; }
        }
        const actions = {
            start: () => {
                session.reset(true); input.value = ''; takeaway.value = ''; status.textContent = ''; answerStatus.textContent = '';
                changeScreen('session');
            },
            finish: () => changeScreen('reflect'),
            return: () => changeScreen('session'),
            complete: () => { session.completed = true; session.homeLit = true; changeScreen('home'); status.textContent = one('[data-home-notice]').textContent; },
            previous: () => { session.previous(); render(); questionText.focus(); },
            next: () => { session.next(); render(); questionText.focus(); },
            answer: () => {
                stopAudio();
                status.textContent = ''; answerStatus.textContent = '';
                session.openAnswer();
                input.value = session.draft;
                one('[data-sheet-question]').textContent = session.question;
                one('[data-dialog-note]').hidden = true;
                render();
                answerDialog.showModal();
                answerDialog.querySelector('h3').focus();
            },
            sample: () => { session.draft = session.config.sampleAnswer; input.value = session.draft; session.confirmCancel = false; render(); input.focus(); },
            mic: () => { one('[data-dialog-note]').hidden = false; answerStatus.textContent = one('[data-dialog-note]').textContent; },
            save: () => { session.save(); answerDialog.close(); render(); status.textContent = root.dataset.savedLabel; },
            cancel: cancelAnswer,
            favorite: () => { session.favorite = !session.favorite; render(); },
            available: () => { stopAudio(); noticeDialog.showModal(); },
            'close-notice': () => noticeDialog.close(),
            restart: () => {
                stopAudio();
                if (answerDialog.open) answerDialog.close();
                if (noticeDialog.open) noticeDialog.close();
                session.reset(); input.value = ''; takeaway.value = ''; status.textContent = '';
                if (player) one('[data-audio-error-text]').hidden = true;
                changeScreen('home');
            },
        };
        if (audio) actions.listen = () => { one('[data-audio-error-text]').hidden = true; void audio.toggle(); };
        root.querySelectorAll('[data-action]').forEach(button => {
            if (!actions[button.dataset.action]) throw new Error(`Unknown demo action: ${button.dataset.action}`);
            button.addEventListener('click', actions[button.dataset.action]);
        });
        tabs.forEach((tab, index) => {
            tab.addEventListener('click', () => {
                if (tab.dataset.tab !== 'quote') stopAudio();
                session.tab = tab.dataset.tab;
                render();
            });
            tab.addEventListener('keydown', event => {
                let target;
                if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') target = 1 - index;
                else if (event.key === 'Home') target = 0;
                else if (event.key === 'End') target = 1;
                else return;
                event.preventDefault(); tabs[target].click(); tabs[target].focus();
            });
        });
        input.addEventListener('input', () => { session.draft = input.value; session.confirmCancel = false; render(); });
        takeaway.addEventListener('input', () => { session.takeaway = takeaway.value; render(); });
        answerDialog.addEventListener('cancel', event => { event.preventDefault(); cancelAnswer(); });
        answerDialog.addEventListener('close', () => {
            session.discardDraft(); input.value = session.draft; answerStatus.textContent = ''; render();
        });
        // Native dialog traps focus and restores the triggering button on close.
        root.querySelectorAll('[data-action], [data-tab], textarea').forEach(node => { node.disabled = false; });
        render();
        root.classList.add('pd-ready');
        window.addEventListener('pagehide', stopAudio);
        document.addEventListener('visibilitychange', () => { if (document.hidden) stopAudio(); });
        return session;
    }
    if (typeof module !== 'undefined' && module.exports) module.exports = { Session, connectAudio, init, greetingPeriod };
    if (typeof document !== 'undefined') document.querySelectorAll('[data-prayer-demo]').forEach(init);
})();
