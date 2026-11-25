/**
 * Mangari Unified Reader Engine (ZIP/CBZ & PDF.js)
 * Suporte completo a:
 * - Renderização nativa de PDF com PDF.js em canvas responsivos
 * - Alternância de Modos: Rolagem Vertical (Contínuo) / Página Única
 * - Ajuste de Largura / Zoom com persistência em localStorage (100%, 850px, Original)
 * - Modo Foco / Imersão (auto-recolhimento ao rolar para baixo, toque/clique de alternância)
 * - Navegação via cliques nas metades da tela e setas do teclado (ArrowLeft, ArrowRight, F para tela cheia)
 * - Salvamento assíncrono de progresso (ReadingProgress) com debounce (~1s) e CSRF token
 * - Restauração automática da última página lida
 * - IntersectionObserver no modo contínuo para precisão de leitura
 */

document.addEventListener('DOMContentLoaded', function () {
    const reader = document.querySelector('[data-reader]');
    if (!reader) return;

    const isPdfMode = reader.dataset.readerType === 'pdf';
    const pdfUrl = reader.dataset.pdfUrl;
    const progressUrl = reader.dataset.progressUrl;
    const initialPage = Math.max(1, parseInt(reader.dataset.initialPage, 10) || 1);

    // Elementos da interface
    const toolbar = document.getElementById('reader-toolbar');
    const optionsBar = document.getElementById('reader-options-bar');
    const progressBar = document.getElementById('reader-progress-bar');
    const pageLabel = document.getElementById('current-page');
    const statusMsg = document.getElementById('reader-status');
    const completionStatus = document.getElementById('completion-status');
    const endCard = document.getElementById('chapter-end-card');
    const pagesContainer = document.getElementById('reader-pages');

    const previousBtn = document.getElementById('previous-page');
    const nextBtn = document.getElementById('next-page');
    const modeButtons = document.querySelectorAll('[data-mode]');
    const widthButtons = document.querySelectorAll('[data-width]');
    const fullscreenBtn = document.getElementById('fullscreen-btn');

    // Estado da aplicação
    let totalPages = parseInt(reader.dataset.pageCount, 10) || 1;
    let activePage = initialPage;
    let mode = localStorage.getItem('mangari_reader_mode') || 'vertical';
    let widthPreset = localStorage.getItem('mangari_reader_width') || 'comfortable';
    let isToolbarVisible = true;
    let lastScrollY = window.scrollY;
    let saveTimeout = null;
    let saveAbortController = null;
    let observer = null;
    let pdfDoc = null;
    let pagesRendered = false;

    // =========================================================================
    // 1. Inicialização de Largura e Modos
    // =========================================================================

    const applyWidthPreset = (preset) => {
        widthPreset = preset;
        localStorage.setItem('mangari_reader_width', preset);

        if (preset === 'full') {
            reader.style.setProperty('--reader-max-width', '100%');
        } else if (preset === 'original') {
            reader.style.setProperty('--reader-max-width', '1200px');
        } else {
            // 'comfortable' padrão
            reader.style.setProperty('--reader-max-width', '850px');
        }

        widthButtons.forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.width === preset);
        });
    };

    const updateUIState = () => {
        // Indicador de texto da página
        if (pageLabel) {
            pageLabel.textContent = `Página ${activePage} / ${totalPages}`;
        }
        // Barra fina laranja no topo
        if (progressBar) {
            const pct = totalPages > 0 ? (activePage / totalPages) * 100 : 0;
            progressBar.style.width = `${pct}%`;
        }
        // Desabilitar botões nos extremos no modo página única
        if (previousBtn) {
            previousBtn.disabled = mode === 'single' && activePage <= 1;
            previousBtn.style.opacity = previousBtn.disabled ? '0.4' : '1';
        }
        if (nextBtn) {
            nextBtn.disabled = mode === 'single' && activePage >= totalPages;
            nextBtn.style.opacity = nextBtn.disabled ? '0.4' : '1';
        }
    };

    // =========================================================================
    // 2. Persistência de Progresso (ReadingProgress) via Debounce (~1s)
    // =========================================================================

    const saveProgress = (forceCompleted = false) => {
        if (!progressUrl) return;

        const isCompleted = forceCompleted || activePage >= totalPages;

        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(async () => {
            if (saveAbortController) {
                saveAbortController.abort();
            }
            saveAbortController = new AbortController();

            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

            try {
                const response = await fetch(progressUrl, {
                    method: 'POST',
                    credentials: 'same-origin',
                    signal: saveAbortController.signal,
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                    },
                    body: JSON.stringify({
                        current_page: activePage,
                        is_completed: isCompleted,
                    }),
                });

                const data = await response.json();
                if (response.ok && data.saved) {
                    if (statusMsg) {
                        statusMsg.textContent = 'Progresso salvo.';
                        setTimeout(() => {
                            if (statusMsg.textContent === 'Progresso salvo.') {
                                statusMsg.textContent = '';
                            }
                        }, 2500);
                    }
                    if (isCompleted && completionStatus) {
                        completionStatus.textContent = '✓ Capítulo concluído';
                    }
                }
            } catch (err) {
                if (err.name !== 'AbortError' && statusMsg) {
                    statusMsg.textContent = 'Erro ao sincronizar progresso.';
                }
            }
        }, 1000);
    };

    // =========================================================================
    // 3. Controle e Navegação de Páginas
    // =========================================================================

    const getPageElements = () => {
        return Array.from(document.querySelectorAll('.reader-page-item'));
    };

    const goToPage = (pageNumber, smoothScroll = true) => {
        const pageItems = getPageElements();
        activePage = Math.max(1, Math.min(totalPages, pageNumber));

        if (mode === 'single') {
            pageItems.forEach((item, index) => {
                const isCurrent = index + 1 === activePage;
                item.hidden = !isCurrent;
            });
            window.scrollTo({ top: 0, behavior: smoothScroll ? 'smooth' : 'auto' });
        } else if (pageItems[activePage - 1]) {
            pageItems[activePage - 1].scrollIntoView({
                behavior: smoothScroll ? 'smooth' : 'auto',
                block: 'start',
            });
        }

        updateUIState();
        saveProgress(activePage >= totalPages);
    };

    const setMode = (newMode) => {
        mode = newMode;
        localStorage.setItem('mangari_reader_mode', mode);
        reader.classList.toggle('single-page-mode', mode === 'single');

        modeButtons.forEach((btn) => {
            const isMatch = btn.dataset.mode === mode;
            btn.setAttribute('aria-pressed', String(isMatch));
            btn.classList.toggle('active', isMatch);
        });

        const pageItems = getPageElements();

        if (mode === 'single') {
            if (observer) {
                observer.disconnect();
            }
            pageItems.forEach((item, index) => {
                item.hidden = index + 1 !== activePage;
            });
            window.scrollTo({ top: 0, behavior: 'auto' });
        } else {
            pageItems.forEach((item) => {
                item.hidden = false;
            });
            setupIntersectionObserver();
            if (pageItems[activePage - 1]) {
                setTimeout(() => {
                    pageItems[activePage - 1].scrollIntoView({ behavior: 'auto', block: 'start' });
                }, 50);
            }
        }

        updateUIState();
    };

    // =========================================================================
    // 4. IntersectionObserver para Leitura Contínua
    // =========================================================================

    const setupIntersectionObserver = () => {
        if (!('IntersectionObserver' in window) || mode !== 'vertical') return;

        if (observer) observer.disconnect();

        observer = new IntersectionObserver((entries) => {
            const visibleEntries = entries.filter((entry) => entry.isIntersecting);
            if (!visibleEntries.length) return;

            // Pega o elemento com maior área visível
            visibleEntries.sort((a, b) => b.intersectionRatio - a.intersectionRatio);
            const bestEntry = visibleEntries[0];
            const pageNum = parseInt(bestEntry.target.dataset.page, 10);

            if (pageNum && pageNum !== activePage) {
                activePage = pageNum;
                updateUIState();
                saveProgress(activePage >= totalPages);
            }
        }, {
            threshold: [0.2, 0.5, 0.8],
            rootMargin: '-5% 0px -25% 0px',
        });

        const pageItems = getPageElements();
        pageItems.forEach((page) => observer.observe(page));
    };

    // =========================================================================
    // 5. Modo Foco / Imersão
    // =========================================================================

    const setToolbarVisible = (visible) => {
        isToolbarVisible = visible;
        if (toolbar) toolbar.classList.toggle('reader-hidden', !visible);
        if (optionsBar) optionsBar.classList.toggle('reader-hidden', !visible);
    };

    const toggleToolbar = () => {
        setToolbarVisible(!isToolbarVisible);
    };

    // Auto-ocultar no scroll para baixo (modo vertical contínuo)
    window.addEventListener('scroll', () => {
        if (mode !== 'vertical') return;

        const currentY = window.scrollY;
        const diff = currentY - lastScrollY;

        if (diff > 40 && currentY > 120 && isToolbarVisible) {
            setToolbarVisible(false);
        } else if (diff < -30 && !isToolbarVisible) {
            setToolbarVisible(true);
        }
        lastScrollY = currentY;
    }, { passive: true });

    // Reexibir ao aproximar o mouse do topo da janela
    document.addEventListener('mousemove', (e) => {
        if (e.clientY <= 50 && !isToolbarVisible) {
            setToolbarVisible(true);
        }
    });

    // Clique nas páginas:
    // - No modo página única: metade esquerda volta página, metade direita avança página, centro alterna modo foco.
    // - No modo vertical: clique rápido alterna modo foco.
    pagesContainer?.addEventListener('click', (e) => {
        // Ignora cliques em botões de erro/tentar novamente
        if (e.target.closest('button, a, select')) return;

        if (mode === 'single') {
            const rect = pagesContainer.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const width = rect.width;

            if (clickX < width * 0.3) {
                // Metade esquerda -> Página anterior
                goToPage(activePage - 1);
            } else if (clickX > width * 0.7) {
                // Metade direita -> Próxima página
                goToPage(activePage + 1);
            } else {
                // Centro -> Alternar toolbar
                toggleToolbar();
            }
        } else {
            toggleToolbar();
        }
    });

    // =========================================================================
    // 6. Navegação via Teclado e Atalhos (ArrowLeft, ArrowRight, F, M)
    // =========================================================================

    document.addEventListener('keydown', (e) => {
        if (e.altKey || e.ctrlKey || e.metaKey) return;
        if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;

        // Setas Esquerda/Direita (ou A/D) para avançar/voltar páginas e capítulos
        if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') {
            if (mode === 'single') {
                e.preventDefault();
                if (activePage < totalPages) {
                    goToPage(activePage + 1);
                } else {
                    // Extremidade final: se houver próximo capítulo, navega
                    const nextChapLink = document.querySelector('.reader-toolbar-right a.reader-control-btn.primary, a#end-card-next-chap');
                    if (nextChapLink && nextChapLink.href) {
                        window.location.href = nextChapLink.href;
                    }
                }
            }
        } else if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') {
            if (mode === 'single') {
                e.preventDefault();
                if (activePage > 1) {
                    goToPage(activePage - 1);
                } else {
                    // Extremidade inicial: se houver capítulo anterior, navega
                    const prevChapLink = document.querySelector('.reader-toolbar-right a.reader-control-btn[title="Capítulo Anterior"]');
                    if (prevChapLink && prevChapLink.href) {
                        window.location.href = prevChapLink.href;
                    }
                }
            }
        } else if (e.key === 'f' || e.key === 'F') {
            // Tecla F: alternar o Modo Foco (ocultar/mostrar barras superiores)
            e.preventDefault();
            toggleToolbar();
        } else if (e.key === 'm' || e.key === 'M') {
            // Tecla M: alternar entre Rolagem Vertical e Página Única
            e.preventDefault();
            const targetMode = mode === 'vertical' ? 'single' : 'vertical';
            setMode(targetMode);
        } else if (e.key === 'Escape' && !isToolbarVisible) {
            setToolbarVisible(true);
        }
    });

    const toggleFullscreen = () => {
        if (!document.fullscreenElement) {
            reader.requestFullscreen?.().catch(() => {});
        } else {
            document.exitFullscreen?.().catch(() => {});
        }
    };

    fullscreenBtn?.addEventListener('click', toggleFullscreen);

    // Sincroniza a classe .is-fullscreen no leitor com o evento fullscreenchange
    document.addEventListener('fullscreenchange', () => {
        const isFs = document.fullscreenElement === reader;
        reader.classList.toggle('is-fullscreen', isFs);
        if (fullscreenBtn) {
            fullscreenBtn.classList.toggle('active', isFs);
            fullscreenBtn.setAttribute('aria-pressed', String(isFs));
        }
    });

    // =========================================================================
    // 7. Eventos dos Botões de Navegação e Opções
    // =========================================================================

    previousBtn?.addEventListener('click', () => goToPage(activePage - 1));
    nextBtn?.addEventListener('click', () => goToPage(activePage + 1));

    modeButtons.forEach((btn) => {
        btn.addEventListener('click', () => setMode(btn.dataset.mode));
    });

    widthButtons.forEach((btn) => {
        btn.addEventListener('click', () => applyWidthPreset(btn.dataset.width));
    });

    // Fallbacks e recarregamento confiável para imagens ZIP/CBZ
    const setupImageFallbacks = () => {
        const pageItems = getPageElements();
        pageItems.forEach((item) => {
            const img = item.querySelector('img');
            const fallback = item.querySelector('.reader-page-fallback');
            const retryBtn = fallback?.querySelector('.retry-page-btn');

            if (!img) return;

            const handleSuccess = () => {
                item.classList.remove('has-error', 'is-error');
                if (fallback) {
                    fallback.hidden = true;
                    fallback.classList.add('is-hidden');
                    fallback.style.display = 'none';
                }
                img.style.display = 'block';
                img.style.opacity = '1';
            };

            const handleError = () => {
                // Apenas exibe erro se a imagem realmente não puder ser renderizada
                if (img.naturalWidth === 0) {
                    item.classList.add('has-error');
                    if (fallback) {
                        fallback.hidden = false;
                        fallback.classList.remove('is-hidden');
                        fallback.style.display = 'flex';
                    }
                }
            };

            // Se a imagem já concluiu com sucesso antes do listener
            if (img.complete && img.naturalWidth > 0) {
                handleSuccess();
            } else if (img.complete && img.naturalWidth === 0) {
                handleError();
            } else {
                // Estado inicial enquanto carrega
                handleSuccess();
            }

            img.addEventListener('load', handleSuccess);
            img.addEventListener('error', handleError);

            retryBtn?.addEventListener('click', (e) => {
                e.stopPropagation();
                handleSuccess();
                const baseUrl = item.dataset.pageUrl || img.src.split('?')[0];
                const separator = baseUrl.includes('?') ? '&' : '?';
                img.src = `${baseUrl}${separator}retry=${Date.now()}`;
            });
        });
    };

    // =========================================================================
    // 8. Renderizador PDF via PDF.js (<canvas> responsivo dentro do tema escuro)
    // =========================================================================

    const initPdfViewer = async () => {
        const loadingState = document.getElementById('pdf-loading-state');
        const fallbackState = document.getElementById('pdf-fallback-state');

        // Garante que o fallback comece sempre oculto
        if (fallbackState) {
            fallbackState.hidden = true;
            fallbackState.classList.add('is-hidden');
            fallbackState.style.display = 'none';
        }

        const showPdfFallback = () => {
            if (loadingState) {
                loadingState.hidden = true;
                loadingState.style.display = 'none';
            }
            if (fallbackState) {
                fallbackState.hidden = false;
                fallbackState.classList.remove('is-hidden');
                fallbackState.style.display = 'flex';
            }
        };

        if (!window.pdfjsLib) {
            showPdfFallback();
            return;
        }

        try {
            const loadingTask = window.pdfjsLib.getDocument({
                url: pdfUrl,
                withCredentials: true,
            });

            pdfDoc = await loadingTask.promise;
            totalPages = pdfDoc.numPages;
            reader.dataset.pageCount = totalPages;

            if (loadingState) loadingState.remove();
            if (fallbackState) {
                fallbackState.hidden = true;
                fallbackState.classList.add('is-hidden');
                fallbackState.style.display = 'none';
            }

            // Criar elementos de página com <canvas> para cada página do PDF
            pagesContainer.innerHTML = '';
            for (let i = 1; i <= totalPages; i++) {
                const figure = document.createElement('figure');
                figure.className = 'reader-page-item';
                figure.dataset.page = i;

                const canvas = document.createElement('canvas');
                canvas.id = `pdf-page-${i}`;
                figure.appendChild(canvas);

                pagesContainer.appendChild(figure);
            }

            // Renderizar páginas sob demanda ou de forma sequencial
            await renderAllPdfPages();

            pagesRendered = true;
            applyWidthPreset(widthPreset);
            setMode(mode);

            // Rolar para a página inicial se > 1
            if (activePage > 1) {
                setTimeout(() => goToPage(activePage, false), 150);
            } else {
                updateUIState();
                saveProgress();
            }
        } catch (err) {
            console.error('Falha ao carregar o PDF com PDF.js:', err);
            showPdfFallback();
        }
    };

    const renderAllPdfPages = async () => {
        if (!pdfDoc) return;

        // Suporte a telas HiDPI/Retina
        const pixelRatio = window.devicePixelRatio || 1;

        for (let i = 1; i <= totalPages; i++) {
            const page = await pdfDoc.getPage(i);
            const canvas = document.getElementById(`pdf-page-${i}`);
            if (!canvas) continue;

            const context = canvas.getContext('2d');
            const unscaledViewport = page.getViewport({ scale: 1.0 });

            // Base de renderização nítida (~1200px largura base ou viewport natural)
            const targetWidth = Math.max(1000, unscaledViewport.width);
            const scale = targetWidth / unscaledViewport.width;
            const viewport = page.getViewport({ scale: scale });

            canvas.width = viewport.width * pixelRatio;
            canvas.height = viewport.height * pixelRatio;
            canvas.style.width = '100%';
            canvas.style.height = 'auto';

            context.scale(pixelRatio, pixelRatio);

            const renderContext = {
                canvasContext: context,
                viewport: viewport,
            };

            await page.render(renderContext).promise;
        }
    };

    // =========================================================================
    // 9. Execução Inicial
    // =========================================================================

    applyWidthPreset(widthPreset);

    if (isPdfMode) {
        initPdfViewer();
    } else {
        setupImageFallbacks();
        setMode(mode);

        if (activePage > 1) {
            setTimeout(() => goToPage(activePage, false), 150);
        } else {
            updateUIState();
            saveProgress();
        }
    }
});