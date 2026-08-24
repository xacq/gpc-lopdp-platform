/**
 * VINESA LOPDP Platform - Cookie Consent Manager
 * Manages informing users about technical cookies as required by Ecuadorian LOPDP.
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'vinesa_cookie_consent';

    function initCookieBanner() {
        const banner = document.getElementById('cookieBanner');
        const acceptBtn = document.getElementById('cookieAcceptBtn');

        if (!banner || !acceptBtn) {
            return;
        }

        const consent = localStorage.getItem(STORAGE_KEY);

        if (!consent) {
            // Display banner with smooth entrance
            banner.removeAttribute('hidden');
            requestAnimationFrame(() => {
                banner.classList.add('cookie-banner--visible');
            });
        }

        acceptBtn.addEventListener('click', function () {
            const consentData = {
                status: 'accepted',
                timestamp: new Date().toISOString(),
                version: '1.0'
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(consentData));

            banner.classList.remove('cookie-banner--visible');
            banner.classList.add('cookie-banner--hiding');

            setTimeout(() => {
                banner.setAttribute('hidden', '');
                banner.classList.remove('cookie-banner--hiding');
            }, 350);
        });

        // Global hook for reopening cookie notice from footer or anywhere else
        window.openCookieNotice = function () {
            banner.removeAttribute('hidden');
            requestAnimationFrame(() => {
                banner.classList.add('cookie-banner--visible');
                banner.focus();
            });
        };
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCookieBanner);
    } else {
        initCookieBanner();
    }
})();
