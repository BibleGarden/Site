(() => {
    const button = document.querySelector('.checklist-print');
    if (!button) return;
    button.hidden = false;
    button.addEventListener('click', () => window.print());
})();
