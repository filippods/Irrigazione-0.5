// scripts.js - Script principale dell'applicazione

// Variabili globali
let isLoadingPage = false;
let userData = {};
let connectionStatusInterval = null;
let currentPage = null;

// Funzione per mostrare notifiche (toast)
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    // Rimuovi eventuali toast esistenti con lo stesso messaggio
    const existingToasts = container.querySelectorAll('.toast');
    existingToasts.forEach(toast => {
        if (toast.textContent === message) {
            toast.remove();
        }
    });
    
    // Crea un nuovo toast
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    // Aggiungi icona basata sul tipo
    let iconHtml = '';
    switch(type) {
        case 'success':
            iconHtml = '<i class="fas success-icon"></i>';
            break;
        case 'error':
            iconHtml = '<i class="fas error-icon"></i>';
            break;
        case 'warning':
            iconHtml = '<i class="fas warning-icon"></i>';
            break;
        default:
            iconHtml = '<i class="fas info-icon"></i>';
    }
    
    toast.innerHTML = `${iconHtml}<span>${message}</span>`;
    
    // Aggiungi al container
    container.appendChild(toast);
    
    // Renderizza e avvia l'animazione
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);
    
    // Rimuovi dopo la durata specificata
    const timerId = setTimeout(() => {
        toast.classList.remove('show');
        
        // Rimuovi l'elemento dopo che l'animazione è completata
        setTimeout(() => {
            if (container.contains(toast)) {
                container.removeChild(toast);
            }
        }, 300);
    }, duration);
    
    // Permetti di chiudere il toast cliccandolo
    toast.addEventListener('click', () => {
        clearTimeout(timerId);
        toast.classList.remove('show');
        
        setTimeout(() => {
            if (container.contains(toast)) {
                container.removeChild(toast);
            }
        }, 300);
    });
}

// Funzione per caricare i dati da user_settings.json una sola volta
function loadUserData(callback) {
    fetch('/data/user_settings.json')
        .then(response => {
            if (!response.ok) throw new Error('Errore nel caricamento dei dati di user_settings');
            return response.json();
        })
        .then(data => {
            userData = data;
            console.log("Dati utente caricati:", userData);
            if (callback) callback(userData);
        })
        .catch(error => {
            console.error('Errore nel caricamento dei dati di user_settings:', error);
            showToast('Errore nel caricamento delle impostazioni', 'error');
        });
}

// Funzione per caricare e visualizzare una pagina
function loadPage(pageName, callback) {
    if (isLoadingPage) return;
    isLoadingPage = true;
    closeMenu();
	
    if (pageName === 'create_program.html') {
        // Rimuovi sempre l'ID quando vai alla pagina di creazione
        localStorage.removeItem('editProgramId');
        sessionStorage.removeItem('editing_intent');
    } else if (pageName !== 'modify_program.html') {
        // Se stiamo andando a una pagina che non è né creazione né modifica,
        // possiamo pulire l'ID (a meno che non stiamo salvando un form)
        if (!pageName.includes('save') && !pageName.includes('update')) {
            localStorage.removeItem('editProgramId');
            sessionStorage.removeItem('editing_intent');
        }
    }
    
    // Segna la pagina corrente nel menu
    updateActiveMenuItem(pageName);
    
    // Memorizza la pagina corrente
    currentPage = pageName;
    
    // Chiudi il menu dopo la selezione (su dispositivi mobili)
    closeMenu();
    
    // Mostra un indicatore di caricamento
    const contentElement = document.getElementById('content');
    if (contentElement) {
        contentElement.innerHTML = '<div class="loading-indicator" style="text-align:center;padding:50px;">Caricamento...</div>';
    }

    fetch(pageName)
        .then(response => {
            if (!response.ok) throw new Error(`Errore HTTP: ${response.status}`);
            return response.text();
        })
        .then(html => {
            if (contentElement) {
                contentElement.innerHTML = html;

                // Ferma il polling prima di caricare qualsiasi altra pagina
                stopConnectionStatusPolling();

                // Carica gli script associati alla pagina
                const scriptSrc = pageName.replace('.html', '.js');
                
                // Rimuovi eventuali script precedenti della stessa pagina
                const oldScripts = document.querySelectorAll(`script[src="${scriptSrc}"]`);
                oldScripts.forEach(script => script.remove());
                
                // Carica il nuovo script
                loadScript(scriptSrc, () => {
                    // Inizializza la pagina basandosi sul nome del file
                    switch (pageName) {
                        case 'manual.html':
                            if (typeof initializeManualPage === 'function') {
                                initializeManualPage(userData);
                            }
                            break;
                        case 'create_program.html':
                            if (typeof initializeCreateProgramPage === 'function') {
                                initializeCreateProgramPage();
                            }
                            break;
                        case 'modify_program.html':
                            if (typeof initializeModifyProgramPage === 'function') {
                                initializeModifyProgramPage();
                            }
                            break;
                        case 'settings.html':
                            if (typeof initializeSettingsPage === 'function') {
                                initializeSettingsPage(userData);
                            }
                            // Avvia il polling dello stato della connessione solo se sei nella pagina Impostazioni
                            startConnectionStatusPolling();
                            break;
                        case 'view_programs.html':
                            if (typeof initializeViewProgramsPage === 'function') {
                                initializeViewProgramsPage();
                            }
                            break;
                        case 'logs.html':
                            if (typeof initializeLogsPage === 'function') {
                                initializeLogsPage();
                            }
                            break;
                    }

                    if (callback && typeof callback === 'function') {
                        callback();
                    }
                });
            }
        })
        .catch(error => {
            console.error('Errore nel caricamento della pagina:', error);
            if (contentElement) {
                contentElement.innerHTML = `
                    <div style="text-align:center;padding:30px;color:#ff3333;">
                        <div style="font-size:48px;margin-bottom:20px;">⚠️</div>
                        <h2>Errore di caricamento</h2>
                        <p>Impossibile caricare la pagina ${pageName}</p>
                        <button onclick="window.location.reload()" class="button primary" style="margin-top:20px;">
                            Ricarica pagina
                        </button>
                    </div>
                `;
            }
            showToast(`Errore nel caricamento di ${pageName}`, 'error');
        })
        .finally(() => {
            isLoadingPage = false;
        });
}

// Funzione per caricare uno script
function loadScript(url, callback) {
    // Prima rimuovi qualsiasi script esistente con lo stesso URL
    const existingScripts = document.querySelectorAll(`script[src="${url}"]`);
    existingScripts.forEach(script => script.remove());
    
    // Ora crea un nuovo script
    const script = document.createElement('script');
    script.src = url;
    script.onload = callback;
    script.onerror = () => {
        console.error(`Errore nel caricamento dello script: ${url}`);
        callback();  // Chiamiamo comunque il callback per non bloccare
    };
    document.head.appendChild(script);
}

// Funzione per aggiornare l'elemento del menu attivo
function updateActiveMenuItem(pageName) {
    const menuItems = document.querySelectorAll('.menu li');
    menuItems.forEach(item => {
        const itemPage = item.getAttribute('data-page');
        if (itemPage === pageName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}

// Versione corretta per scripts.js - solo la parte che necessita di correzione

function toggleMenu() {
    const menu = document.getElementById('menu');
    const overlay = document.getElementById('menu-overlay');
    
    if (!menu || !overlay) return;
    
    menu.classList.toggle('active');
    overlay.classList.toggle('active');
}

function closeMenu() {
    const menu = document.getElementById('menu');
    const overlay = document.getElementById('menu-overlay');
    
    if (!menu || !overlay) return;
    
    menu.classList.remove('active');
    overlay.classList.remove('active');
}

// Funzione per aggiornare data e ora
function updateDateTime() {
    const dateElement = document.getElementById('date');
    const timeElement = document.getElementById('time');

    if (!dateElement || !timeElement) return;

    const now = new Date();
    
    // Formatta la data come "giorno mese anno"
    const options = { day: 'numeric', month: 'long', year: 'numeric' };
    const formattedDate = now.toLocaleDateString('it-IT', options);
    
    // Formatta l'ora come "ore:minuti:secondi"
    const formattedTime = now.toLocaleTimeString('it-IT', { 
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit'
    });

    dateElement.textContent = formattedDate;
    timeElement.textContent = formattedTime;
}

// Funzioni per il polling dello stato della connessione
function startConnectionStatusPolling() {
    if (connectionStatusInterval) {
        clearInterval(connectionStatusInterval);
    }
    
    // Esegui subito
    fetchConnectionStatus();
    
    // Poi esegui ogni 30 secondi
    connectionStatusInterval = setInterval(fetchConnectionStatus, 30000);
    console.log("Polling dello stato della connessione avviato");
}

function stopConnectionStatusPolling() {
    if (connectionStatusInterval) {
        clearInterval(connectionStatusInterval);
        connectionStatusInterval = null;
        console.log("Polling dello stato della connessione fermato");
    }
}

function fetchConnectionStatus() {
    fetch('/get_connection_status')
        .then(response => {
            if (!response.ok) throw new Error('Errore nel caricamento dello stato della connessione');
            return response.json();
        })
        .then(data => {
            const statusElement = document.getElementById('connection-status');
            if (statusElement) {
                let statusHtml = '';
                
                if (data.mode === 'client') {
                    statusHtml = `
                        <div style="background-color:#e6f7ff;border-radius:8px;padding:15px;margin-top:15px;border:1px solid #91d5ff;">
                            <h3 style="margin:0 0 10px 0;color:#0099ff;">Connesso alla rete WiFi</h3>
                            <p><strong>SSID:</strong> ${data.ssid}</p>
                            <p><strong>IP:</strong> ${data.ip}</p>
                        </div>
                    `;
                } else if (data.mode === 'AP') {
                    statusHtml = `
                        <div style="background-color:#fff7e6;border-radius:8px;padding:15px;margin-top:15px;border:1px solid #ffd591;">
                            <h3 style="margin:0 0 10px 0;color:#fa8c16;">Access Point attivo</h3>
                            <p><strong>SSID:</strong> ${data.ssid}</p>
                            <p><strong>IP:</strong> ${data.ip}</p>
                        </div>
                    `;
                } else {
                    statusHtml = `
                        <div style="background-color:#fff1f0;border-radius:8px;padding:15px;margin-top:15px;border:1px solid #ffa39e;">
                            <h3 style="margin:0 0 10px 0;color:#f5222d;">Nessuna connessione attiva</h3>
                        </div>
                    `;
                }
                
                statusElement.innerHTML = statusHtml;
                statusElement.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Errore nel caricamento dello stato della connessione:', error);
            // Non mostrare toast per evitare troppi popup
        });
}

// Funzione per fermare tutti i programmi in esecuzione
function stopAllPrograms() {
    // Aggiungi classe loading al pulsante
    const stopBtn = document.querySelector('.stop-all-button');
    if (stopBtn) {
        stopBtn.classList.add('loading');
    }
    
    fetch('/stop_program', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (stopBtn) {
            stopBtn.classList.remove('loading');
        }
        
        if (data.success) {
            showToast('Arresto totale eseguito con successo', 'success');
            
            // Se siamo nella pagina di visualizzazione programmi, aggiorniamola
            if (currentPage === 'view_programs.html' && typeof fetchProgramState === 'function') {
                fetchProgramState();
            }
            
            // Se siamo nella pagina manuale, aggiorniamola
            if (currentPage === 'manual.html' && typeof fetchZonesStatus === 'function') {
                fetchZonesStatus();
            }
        } else {
            showToast(`Errore durante l'arresto totale: ${data.error || 'Errore sconosciuto'}`, 'error');
        }
    })
    .catch(error => {
        if (stopBtn) {
            stopBtn.classList.remove('loading');
        }
        console.error('Errore di rete durante l\'arresto totale:', error);
        showToast('Errore di rete durante l\'arresto totale', 'error');
    });
}

// Funzione per l'inizializzazione della pagina
function initializePage() {
    // Aggiorna data e ora
    updateDateTime();
    setInterval(updateDateTime, 1000);

    // Carica i dati utente e dopo carica la pagina predefinita
    loadUserData(() => {
        // Carica la pagina predefinita (controllo manuale)
        loadPage('manual.html');
    });
    
    // Esponi funzioni globali
    window.showToast = showToast;
}

// Inizializzazione quando il DOM è completamente caricato
document.addEventListener('DOMContentLoaded', () => {
    // Inizializza la pagina principale
    initializePage();

    // Gestisci i click sui link di navigazione
    document.querySelectorAll('.menu li').forEach(item => {
        item.addEventListener('click', (event) => {
            const targetPage = event.currentTarget.getAttribute('data-page');
            if (targetPage) {
                loadPage(targetPage);
            }
        });
    });

    // Previeni il trascinamento delle immagini
    document.addEventListener('dragstart', (e) => {
        if (e.target.tagName === 'IMG') {
            e.preventDefault();
        }
    });
});

// Gestione errori globali
window.addEventListener('error', (event) => {
    console.error('Errore JavaScript:', event.error);
    showToast('Si è verificato un errore. Controlla la console del browser.', 'error');
});