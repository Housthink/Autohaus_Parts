/** Dropdown de subcategorías en el filmstrip de categorías del shop.
 *
 * El filmstrip es un contenedor con scroll horizontal (overflow-x: auto), por
 * lo que un dropdown con `position: absolute` quedaría recortado. Aquí se
 * posiciona en `position: fixed` mientras está abierto para que flote por
 * encima del resto de la página.
 */
(() => {
    const filmstrip = document.querySelector('#o_wsale_categories_filmstrip.o_autohaus_cats');
    if (!filmstrip) return;

    let openItem = null;
    let openDropdown = null;

    const close = () => {
        if (openDropdown) {
            openDropdown.classList.remove('o_autohaus_cat_dropdown--open');
            openDropdown.style.position = '';
            openDropdown.style.top = '';
            openDropdown.style.left = '';
        }
        openItem = null;
        openDropdown = null;
    };

    const open = (item) => {
        const dropdown = item.querySelector(':scope > .o_autohaus_cat_dropdown');
        if (!dropdown) {
            close();
            return;
        }

        const rect = item.getBoundingClientRect();
        const width = dropdown.offsetWidth;
        const margin = 12;
        let left = rect.left;
        const maxLeft = window.innerWidth - width - margin;
        if (left > maxLeft) {
            left = Math.max(margin, maxLeft);
        }

        dropdown.style.position = 'fixed';
        dropdown.style.top = `${rect.bottom}px`;
        dropdown.style.left = `${left}px`;
        dropdown.classList.add('o_autohaus_cat_dropdown--open');

        openItem = item;
        openDropdown = dropdown;
    };

    // Delegación para seguir funcionando si Odoo re-renderiza el filmstrip.
    filmstrip.addEventListener('mouseover', (event) => {
        const item = event.target.closest('.o_autohaus_cats_list > li');
        if (!item || item === openItem) return;
        open(item);
    });

    filmstrip.addEventListener('mouseout', (event) => {
        if (!openItem) return;
        const related = event.relatedTarget;
        if (related && openItem.contains(related)) return;
        close();
    });

    window.addEventListener('scroll', () => {
        if (openItem) open(openItem);
    }, true);
})();
