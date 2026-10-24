/** Rename the native shop tag filter without overriding Odoo's dynamic QWeb templates. */
(() => {
    const renameManufacturerFilter = () => {
        document.querySelectorAll('button[aria-controls="o_wsale_tags_option_inner"] b').forEach((element) => {
            element.textContent = 'Fabricante';
        });
        document.querySelectorAll('b, button, .accordion-button').forEach((element) => {
            const label = element.textContent.trim();
            if (label === 'Tags' || label === 'Etiquetas') {
                element.textContent = 'Fabricante';
            }
        });
    };

    document.addEventListener('DOMContentLoaded', renameManufacturerFilter);
    if (document.body) {
        new MutationObserver(renameManufacturerFilter).observe(document.body, {
            childList: true,
            subtree: true,
        });
    }
})();
