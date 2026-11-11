/* Show the server-calculated shipping components in checkout. */
(function () {
    'use strict';

    function money(value) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
        }).format(Number(value || 0));
    }

    function loadBreakdown() {
        const panel = document.getElementById('autohaus_shipping_breakdown');
        if (!panel) return;

        fetch('/shop/shipping/quote', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {}}),
        })
            .then((response) => response.json())
            .then((payload) => {
                const data = payload.result || payload;
                const breakdown = data.breakdown || {};
                if (data.status !== 'ok' || !Object.keys(breakdown).length) return;

                panel.querySelector('[data-shipping-base]').textContent = money(breakdown.base_rate);
                panel.querySelector('[data-shipping-weight]').textContent = Number(breakdown.weight_lb || 0).toFixed(2);
                panel.querySelector('[data-shipping-markup]').textContent = money(breakdown.markup_total);
                panel.querySelector('[data-shipping-total]').textContent = money(breakdown.total);
                panel.hidden = false;
            })
            .catch(() => {
                // The regular checkout remains usable if the optional quote fails.
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadBreakdown);
    } else {
        loadBreakdown();
    }
})();
