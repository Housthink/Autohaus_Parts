/** Autohaus header search autocomplete. */

(() => {
    const searchWrap = document.querySelector('.o_autohaus_search_wrap');
    const form = searchWrap?.querySelector('.o_autohaus_search');
    const input = form?.querySelector('.o_autohaus_search_input');
    const suggestions = searchWrap?.querySelector('.o_autohaus_search_suggestions');
    if (!searchWrap || !form || !input || !suggestions) return;

    let timer;
    let requestNumber = 0;

    const closeSuggestions = () => {
        suggestions.innerHTML = '';
        suggestions.classList.remove('is-visible');
    };

    const renderSuggestions = (results) => {
        suggestions.innerHTML = '';
        if (!results.length) {
            closeSuggestions();
            return;
        }
        results.forEach((item) => {
            const link = document.createElement('a');
            link.className = 'o_autohaus_search_suggestion';
            link.href = item.url;
            link.setAttribute('role', 'option');

            const image = document.createElement('img');
            image.src = item.image;
            image.alt = '';
            image.loading = 'lazy';

            const text = document.createElement('span');
            const name = document.createElement('strong');
            name.textContent = item.name;
            text.appendChild(name);
            if (item.sku) {
                const sku = document.createElement('small');
                sku.textContent = item.sku;
                text.appendChild(sku);
            }
            link.append(image, text);
            suggestions.appendChild(link);
        });
        suggestions.classList.add('is-visible');
    };

    const loadSuggestions = async () => {
        const query = input.value.trim();
        if (query.length < 2) {
            closeSuggestions();
            return;
        }
        const currentRequest = ++requestNumber;
        try {
            const response = await fetch(`/shop/autocomplete?q=${encodeURIComponent(query)}`);
            const payload = await response.json();
            if (currentRequest === requestNumber) renderSuggestions(payload.results || []);
        } catch (error) {
            if (currentRequest === requestNumber) closeSuggestions();
        }
    };

    input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(loadSuggestions, 180);
    });
    input.addEventListener('focus', loadSuggestions);
    document.addEventListener('click', (event) => {
        if (!searchWrap.contains(event.target)) closeSuggestions();
    });
})();
