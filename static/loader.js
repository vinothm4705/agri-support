document.addEventListener("DOMContentLoaded", function () {
    // Detect language from HTML lang attribute or default to English
    const lang = document.documentElement.lang || 'en';
    const loaderText = lang === 'ta' ? 'ஏற்றுகிறது...' : 'Loading...';

    // 1. Inject Loader HTML
    const loaderHTML = `
    <div class="global-loader" id="pageLoader">
        <div class="loader-content">
            <div class="loader-circle">
                <i class="fas fa-leaf loader-icon"></i>
                <div class="loader-ring"></div>
            </div>
            <div class="loader-text">${loaderText}</div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', loaderHTML);

    const loader = document.getElementById('pageLoader');

    // 2. Show Loader Function
    window.showLoader = function () {
        loader.classList.add('active');
    };

    window.hideLoader = function () {
        loader.classList.remove('active');
    };

    // 3. Handle Initial Load (Fade In Effect on page enter, then hide)
    // Actually, for a smoother feel, we start hidden unless we want a transition.
    // If we want a transition BETWEEN pages, we usually show it on link click.

    // 4. Handle Link Clicks (Navigation)
    document.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            const target = this.getAttribute('target');

            // Only show loader for internal links that are not hash links or new tabs
            if (href &&
                !href.startsWith('#') &&
                !href.startsWith('javascript') &&
                target !== '_blank' &&
                !e.ctrlKey &&
                !e.metaKey) {

                showLoader();
                // Allow navigation to proceed naturally
            }
        });
    });

    // 5. Handle Form Submissions
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function () {
            // Check if form is valid (if using required attributes)
            if (this.checkValidity()) {
                // Skip global loader if form has 'no-loader' class
                if (this.classList.contains('no-loader')) return;
                showLoader();
            }
        });
    });

    // 6. Handle Browser Back/Forward Cache (BFCache)
    // If user goes back, make sure loader is hidden
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            hideLoader();
        }
    });

    // 7. Language Switch Loader
    const langLoaderHTML = `
    <div class="lang-loader" id="langLoader">
        <div class="lang-globe">
            <i class="fas fa-globe-asia"></i>
        </div>
        <h3 id="langLoaderTitle">Changing Language...</h3>
        <p id="langLoaderSubtitle">Please wait...</p>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', langLoaderHTML);
    const langLoader = document.getElementById('langLoader');
    const langTitle = document.getElementById('langLoaderTitle');
    const langSubtitle = document.getElementById('langLoaderSubtitle');

    // Language display names
    const langNames = {
        'en': { en: 'English', ta: 'ஆங்கிலம்' },
        'ta': { en: 'Tamil', ta: 'தமிழ்' }
    };

    // Intercept language dropdown changes
    document.querySelectorAll('select[name="lang"]').forEach(select => {
        const form = select.closest('form');
        if (form) {
            form.classList.add('no-loader'); // Prevent global loader
            select.addEventListener('change', function () {
                const targetLang = this.value;
                const currentLang = document.documentElement.lang || 'en';

                // Show message in CURRENT language about switching to target
                if (currentLang === 'en') {
                    // Currently English, switching to Tamil
                    langTitle.textContent = 'Changing to Tamil...';
                    langSubtitle.textContent = 'Please wait';
                } else {
                    // Currently Tamil, switching to English
                    langTitle.textContent = 'ஆங்கிலத்திற்கு மாறுகிறது...';
                    langSubtitle.textContent = 'தயவுசெய்து காத்திருக்கவும்';
                }

                langLoader.classList.add('active');
                setTimeout(() => {
                    form.submit();
                }, 300);
            });
        }
    });

    // Intercept language selection buttons (from language.html)
    document.querySelectorAll('button[name="lang"]').forEach(btn => {
        btn.addEventListener('click', function (e) {
            e.preventDefault(); // Prevent immediate submission to allow animation
            const form = this.closest('form');

            if (form) {
                form.classList.add('no-loader'); // Prevent the standard green leaf loader

                const targetLang = this.value;
                if (targetLang === 'ta') {
                    langTitle.textContent = 'தமிழ் மொழியில் ஏற்றப்படுகிறது...';
                    langSubtitle.textContent = 'தயவுசெய்து காத்திருக்கவும்';
                } else {
                    langTitle.textContent = 'Loading in English...';
                    langSubtitle.textContent = 'Please wait';
                }

                // Add the pressed button's value as a hidden input so the backend receives it
                const hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'lang';
                hiddenInput.value = targetLang;
                form.appendChild(hiddenInput);

                langLoader.classList.add('active');

                setTimeout(() => {
                    form.submit();
                }, 300); // 300ms delay for smooth animation reveal
            }
        });
    });
});
