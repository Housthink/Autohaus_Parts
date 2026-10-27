/** Rename the native shop tag filter without overriding Odoo's dynamic QWeb templates. */
(() => {
    const MANUFACTURER = 'Fabricante';

    const renameManufacturerFilter = () => {
        let changed = false;

        document.querySelectorAll('button[aria-controls="o_wsale_tags_option_inner"] b').forEach((element) => {
            if (element.textContent.trim() !== MANUFACTURER) {
                element.textContent = MANUFACTURER;
                changed = true;
            }
        });

        document.querySelectorAll('b, button, .accordion-button').forEach((element) => {
            const label = element.textContent.trim();
            if (label === 'Tags' || label === 'Etiquetas') {
                element.textContent = MANUFACTURER;
                changed = true;
            }
        });

        return changed;
    };

    document.addEventListener('DOMContentLoaded', renameManufacturerFilter);

    if (document.body) {
        // Observe only when necessary: the observer only re-runs when a node
        // was actually renamed, so it never loops on its own mutations.
        let scheduled = false;
        const schedule = () => {
            if (scheduled) return;
            scheduled = true;
            queueMicrotask(() => {
                scheduled = false;
                renameManufacturerFilter();
            });
        };

        const observer = new MutationObserver((mutations) => {
            // Ignore the text-node mutations this script itself produces so it
            // can never re-trigger itself in an infinite loop.
            const relevant = mutations.some((mutation) =>
                mutation.addedNodes.length > 0 || mutation.removedNodes.length > 0
            );
            if (relevant) schedule();
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }
})();
