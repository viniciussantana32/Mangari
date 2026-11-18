document.addEventListener('DOMContentLoaded', function () {
    const flashEls = document.querySelectorAll('.flash');
    flashEls.forEach((el) => {
        setTimeout(() => {
            el.style.opacity = '0.7';
        }, 200);
    });

    document.querySelectorAll('.cover-frame img, .hero-feature img').forEach((image) => {
        image.addEventListener('error', () => {
            image.hidden = true;
            image.parentElement.classList.add('image-failed');
        });
    });

    document.querySelectorAll('form[data-confirm]').forEach((form) => {
        form.addEventListener('submit', (event) => {
            if (!window.confirm(form.dataset.confirm)) event.preventDefault();
        });
    });

    // ==========================================
    // Busca Instantânea com Autocomplete (Header)
    // ==========================================
    const searchInput = document.getElementById('navSearchInput');
    const searchDropdown = document.getElementById('navSearchDropdown');
    const searchResults = document.getElementById('navSearchResults');
    const searchFooter = document.getElementById('navSearchFooter');
    const searchAllLink = document.getElementById('navSearchAllLink');
    const searchClear = document.getElementById('navSearchClear');
    const searchForm = document.getElementById('navSearchForm');

    if (searchInput && searchDropdown && searchResults) {
        let debounceTimeout = null;
        let selectedIndex = -1;

        function closeDropdown() {
            searchDropdown.style.display = 'none';
            selectedIndex = -1;
        }

        function formatStatus(status) {
            const map = {
                'RELEASING': { text: 'Em lançamento', class: 'status-releasing' },
                'FINISHED': { text: 'Finalizado', class: 'status-finished' },
                'NOT_YET_RELEASED': { text: 'Não lançado', class: 'status-default' },
                'CANCELLED': { text: 'Cancelado', class: 'status-default' },
                'HIATUS': { text: 'Em hiato', class: 'status-default' }
            };
            return map[status] || { text: status, class: 'status-default' };
        }

        function renderResults(items, query) {
            searchResults.innerHTML = '';
            selectedIndex = -1;

            if (!items || items.length === 0) {
                searchResults.innerHTML = `<div class="nav-search-empty">Nenhum mangá encontrado para "<strong>${escapeHtml(query)}</strong>"</div>`;
                if (searchFooter) searchFooter.style.display = 'none';
                searchDropdown.style.display = 'block';
                return;
            }

            items.forEach((item, idx) => {
                const statusObj = formatStatus(item.status);
                const itemEl = document.createElement('a');
                itemEl.href = item.detail_url;
                itemEl.className = 'nav-search-item';
                itemEl.dataset.index = idx;

                const thumbHtml = item.cover_url
                    ? `<img src="${escapeHtml(item.cover_url)}" alt="${escapeHtml(item.title)}" class="nav-search-thumb" onerror="this.outerHTML='<div class=\\'nav-search-thumb-fallback\\'>📖</div>'">`
                    : `<div class="nav-search-thumb-fallback">📖</div>`;

                itemEl.innerHTML = `
                    ${thumbHtml}
                    <div class="nav-search-info">
                        <div class="nav-search-title">${escapeHtml(item.title)}</div>
                        <div class="nav-search-meta">
                            <span class="nav-search-badge ${statusObj.class}">${statusObj.text}</span>
                        </div>
                    </div>
                `;

                searchResults.appendChild(itemEl);
            });

            if (searchFooter && searchAllLink) {
                searchAllLink.href = `/catalog?q=${encodeURIComponent(query)}`;
                searchFooter.style.display = 'block';
            }

            searchDropdown.style.display = 'block';
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function fetchSearchResults(query) {
            if (!query.trim()) {
                closeDropdown();
                if (searchClear) searchClear.style.display = 'none';
                return;
            }

            if (searchClear) searchClear.style.display = 'block';

            try {
                const res = await fetch(`/api/search?q=${encodeURIComponent(query.trim())}`);
                if (!res.ok) throw new Error('Search failed');
                const data = await res.json();
                renderResults(data, query.trim());
            } catch (err) {
                console.warn('Erro ao buscar autocomplete:', err);
            }
        }

        searchInput.addEventListener('input', function () {
            clearTimeout(debounceTimeout);
            const val = this.value;
            debounceTimeout = setTimeout(() => {
                fetchSearchResults(val);
            }, 300);
        });

        if (searchClear) {
            searchClear.addEventListener('click', function () {
                searchInput.value = '';
                searchClear.style.display = 'none';
                closeDropdown();
                searchInput.focus();
            });
        }

        // Navegação via teclado no dropdown (Setas Cima / Baixo e Enter)
        searchInput.addEventListener('keydown', function (e) {
            const items = searchResults.querySelectorAll('.nav-search-item');
            if (searchDropdown.style.display !== 'none' && items.length > 0) {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    selectedIndex = (selectedIndex + 1) % items.length;
                    updateItemSelection(items);
                    return;
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    selectedIndex = (selectedIndex - 1 + items.length) % items.length;
                    updateItemSelection(items);
                    return;
                } else if (e.key === 'Enter') {
                    if (selectedIndex >= 0 && items[selectedIndex]) {
                        e.preventDefault();
                        window.location.href = items[selectedIndex].href;
                        return;
                    }
                } else if (e.key === 'Escape') {
                    closeDropdown();
                    return;
                }
            }

            if (e.key === 'Enter') {
                if (searchForm && this.value.trim()) {
                    searchForm.submit();
                }
            }
        });

        function updateItemSelection(items) {
            items.forEach((item, idx) => {
                if (idx === selectedIndex) {
                    item.classList.add('is-selected');
                    item.scrollIntoView({ block: 'nearest' });
                } else {
                    item.classList.remove('is-selected');
                }
            });
        }

        // Fechar dropdown ao clicar fora
        document.addEventListener('click', function (e) {
            if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
                closeDropdown();
            }
        });

        // Reabrir se clicar no input com valor preenchido
        searchInput.addEventListener('focus', function () {
            if (this.value.trim() && searchResults.children.length > 0) {
                searchDropdown.style.display = 'block';
            }
        });
    }

    // ==========================================
    // Carrossel de Destaques da Home (Vanilla JS)
    // ==========================================
    const carouselContainer = document.getElementById('heroCarousel');
    if (carouselContainer) {
        const slides = carouselContainer.querySelectorAll('.hero-carousel-slide');
        const dots = carouselContainer.querySelectorAll('.carousel-dot');
        const prevBtn = document.getElementById('carouselPrevBtn');
        const nextBtn = document.getElementById('carouselNextBtn');
        const backdrops = document.querySelectorAll('.hero-backdrop-item');

        let currentIndex = 0;
        let autoplayTimer = null;
        const totalSlides = slides.length;
        const AUTOPLAY_INTERVAL = 5000; // 5 segundos

        function showSlide(index) {
            if (index < 0) {
                currentIndex = totalSlides - 1;
            } else if (index >= totalSlides) {
                currentIndex = 0;
            } else {
                currentIndex = index;
            }

            // Alterna slides do card
            slides.forEach((slide, idx) => {
                if (idx === currentIndex) {
                    slide.classList.add('active');
                } else {
                    slide.classList.remove('active');
                }
            });

            // Alterna indicadores (dots)
            dots.forEach((dot, idx) => {
                if (idx === currentIndex) {
                    dot.classList.add('active');
                } else {
                    dot.classList.remove('active');
                }
            });

            // Alterna backdrop de fundo (crossfade suave)
            backdrops.forEach((backdrop, idx) => {
                if (idx === currentIndex) {
                    backdrop.classList.add('active');
                } else {
                    backdrop.classList.remove('active');
                }
            });
        }

        function nextSlide() {
            showSlide(currentIndex + 1);
        }

        function prevSlide() {
            showSlide(currentIndex - 1);
        }

        function startAutoplay() {
            stopAutoplay();
            if (totalSlides > 1) {
                autoplayTimer = setInterval(nextSlide, AUTOPLAY_INTERVAL);
            }
        }

        function stopAutoplay() {
            if (autoplayTimer) {
                clearInterval(autoplayTimer);
                autoplayTimer = null;
            }
        }

        // Navegação por cliques
        if (nextBtn) {
            nextBtn.addEventListener('click', (e) => {
                e.preventDefault();
                nextSlide();
                startAutoplay();
            });
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', (e) => {
                e.preventDefault();
                prevSlide();
                startAutoplay();
            });
        }

        dots.forEach((dot) => {
            dot.addEventListener('click', (e) => {
                e.preventDefault();
                const targetIndex = parseInt(dot.getAttribute('data-index'), 10);
                showSlide(targetIndex);
                startAutoplay();
            });
        });

        // Pausar autoplay ao passar o mouse por cima
        carouselContainer.addEventListener('mouseenter', stopAutoplay);
        carouselContainer.addEventListener('mouseleave', startAutoplay);

        // Suporte a swipe simples no mobile
        let touchStartX = 0;
        let touchEndX = 0;

        carouselContainer.addEventListener('touchstart', (e) => {
            touchStartX = e.changedTouches[0].screenX;
            stopAutoplay();
        }, { passive: true });

        carouselContainer.addEventListener('touchend', (e) => {
            touchEndX = e.changedTouches[0].screenX;
            const diffX = touchEndX - touchStartX;
            if (Math.abs(diffX) > 40) {
                if (diffX < 0) {
                    nextSlide();
                } else {
                    prevSlide();
                }
            }
            startAutoplay();
        }, { passive: true });

        // Inicia rotação automática
        startAutoplay();
    }
});
