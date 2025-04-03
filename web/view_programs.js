// view_programs.js - Script per la pagina di visualizzazione programmi

// Variabili globali
var programStatusInterval = null;
var programsData = {};
var zoneNameMap = {};

// Inizializza la pagina
function initializeViewProgramsPage() {
    console.log("Inizializzazione pagina visualizzazione programmi");
    
    // Carica i dati e mostra i programmi
    loadUserSettingsAndPrograms();
    
    // Avvia il polling dello stato dei programmi
    startProgramStatusPolling();
    
    // Ascoltatori per la pulizia quando l'utente lascia la pagina
    window.addEventListener('pagehide', cleanupViewProgramsPage);
    
    // Esponi la funzione di aggiornamento stato programma globalmente
    window.fetchProgramState = fetchProgramState;
}

// Avvia il polling dello stato dei programmi
function startProgramStatusPolling() {
    // Esegui subito
    fetchProgramState();
    
    // Imposta l'intervallo a 3 secondi
    programStatusInterval = setInterval(fetchProgramState, 3000);
    console.log("Polling dello stato dei programmi avviato");
}

// Ferma il polling dello stato dei programmi
function stopProgramStatusPolling() {
    if (programStatusInterval) {
        clearInterval(programStatusInterval);
        programStatusInterval = null;
        console.log("Polling dello stato dei programmi fermato");
    }
}

// Pulisci le risorse quando l'utente lascia la pagina
function cleanupViewProgramsPage() {
    stopProgramStatusPolling();
}

// Ottiene lo stato del programma corrente
function fetchProgramState() {
    fetch('/get_program_state')
        .then(response => {
            if (!response.ok) throw new Error('Errore nel recupero dello stato del programma');
            return response.json();
        })
        .then(state => {
            updateProgramsUI(state);
        })
        .catch(error => {
            console.error('Errore nel recupero dello stato del programma:', error);
        });
}

// Aggiorna l'interfaccia in base allo stato del programma
function updateProgramsUI(state) {
    const currentProgramId = state.current_program_id;
    const programRunning = state.program_running;
    
    // Aggiorna tutte le card dei programmi
    document.querySelectorAll('.program-card').forEach(card => {
        const cardProgramId = card.getAttribute('data-program-id');
        const isActive = programRunning && cardProgramId === currentProgramId;
        
        // Aggiorna classe attiva
        if (isActive) {
            card.classList.add('active-program');
            
            // Aggiungi indicatore se non esiste
            if (!card.querySelector('.active-indicator')) {
                const programHeader = card.querySelector('.program-header');
                if (programHeader) {
                    const indicator = document.createElement('div');
                    indicator.className = 'active-indicator';
                    indicator.textContent = 'In esecuzione';
                    programHeader.appendChild(indicator);
                }
            }
        } else {
            card.classList.remove('active-program');
            
            // Rimuovi indicatore se esiste
            const indicator = card.querySelector('.active-indicator');
            if (indicator) {
                indicator.remove();
            }
        }
        
        // Aggiorna pulsanti
        const startBtn = card.querySelector('.btn-start');
        const stopBtn = card.querySelector('.btn-stop');
        
        if (startBtn && stopBtn) {
            if (isActive) {
                // Questo programma è attivo
                startBtn.classList.add('disabled');
                startBtn.disabled = true;
                stopBtn.classList.remove('disabled');
                stopBtn.disabled = false;
            } else if (programRunning) {
                // Un altro programma è attivo
                startBtn.classList.add('disabled');
                startBtn.disabled = true;
                stopBtn.classList.add('disabled');
                stopBtn.disabled = true;
            } else {
                // Nessun programma è attivo
                startBtn.classList.remove('disabled');
                startBtn.disabled = false;
                stopBtn.classList.add('disabled');
                stopBtn.disabled = true;
            }
        }
    });
}

// Carica le impostazioni utente e i programmi
function loadUserSettingsAndPrograms() {
    // Mostra l'indicatore di caricamento
    const programsContainer = document.getElementById('programs-container');
    if (programsContainer) {
        programsContainer.innerHTML = '<div class="loading">Caricamento programmi...</div>';
    }
    
    // Uso Promise.all per fare richieste parallele
    Promise.all([
        fetch('/data/user_settings.json').then(response => {
            if (!response.ok) throw new Error('Errore nel caricamento delle impostazioni utente');
            return response.json();
        }),
        fetch('/data/program.json').then(response => {
            if (!response.ok) throw new Error('Errore nel caricamento dei programmi');
            return response.json();
        }),
        fetch('/get_program_state').then(response => {
            if (!response.ok) throw new Error('Errore nel caricamento dello stato del programma');
            return response.json();
        })
    ])
    .then(([settings, programs, state]) => {
        const loadedUserSettings = settings;
        
        // Crea una mappa di ID zona -> nome zona
        zoneNameMap = {};
        if (settings.zones && Array.isArray(settings.zones)) {
            settings.zones.forEach(zone => {
                if (zone && zone.id !== undefined) {
                    zoneNameMap[zone.id] = zone.name || `Zona ${zone.id + 1}`;
                }
            });
        }
        
        // Aggiorna lo stato dei programmi automatici
        updateAutoProgramsStatus(settings.automatic_programs_enabled || false);
        
        // Salva i programmi per riferimento futuro
        programsData = programs || {};
        
        // Ora che abbiamo tutti i dati necessari, possiamo renderizzare i programmi
        renderProgramCards(programsData, state);
    })
    .catch(error => {
        console.error('Errore nel caricamento dei dati:', error);
        if (typeof showToast === 'function') {
            showToast('Errore nel caricamento dei dati', 'error');
        }
        
        // Mostra un messaggio di errore
        if (programsContainer) {
            programsContainer.innerHTML = `
                <div class="empty-state">
                    <h3>Errore nel caricamento dei programmi</h3>
                    <p>${error.message}</p>
                    <button class="btn" onclick="loadUserSettingsAndPrograms()">Riprova</button>
                </div>
            `;
        }
    });
}

// Aggiorna lo stato dei programmi automatici nella UI
function updateAutoProgramsStatus(enabled) {
    const statusEl = document.getElementById('auto-status');
    if (statusEl) {
        if (enabled) {
            statusEl.className = 'auto-status on';
            statusEl.querySelector('span').textContent = 'Programmi automatici attivi';
        } else {
            statusEl.className = 'auto-status off';
            statusEl.querySelector('span').textContent = 'Programmi automatici disattivati';
        }
    }
}

// Renderizza le card dei programmi
function renderProgramCards(programs, state) {
    const container = document.getElementById('programs-container');
    if (!container) return;
    
    const programIds = programs ? Object.keys(programs) : [];
    
    if (!programs || programIds.length === 0) {
        // Nessun programma trovato
        container.innerHTML = `
            <div class="empty-state">
                <h3>Nessun programma configurato</h3>
                <p>Crea il tuo primo programma di irrigazione per iniziare a usare il sistema.</p>
                <button class="btn" onclick="loadPage('create_program.html')">Crea Programma</button>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    
    // Per ogni programma, crea una card
    programIds.forEach(programId => {
        const program = programs[programId];
        if (!program) return; // Salta se il programma è nullo
        
        // Assicurati che l'ID del programma sia disponibile nell'oggetto
        if (program.id === undefined) {
            program.id = programId;
        }
        
        const isActive = state.program_running && state.current_program_id === String(programId);
        
        // Costruisci la visualizzazione dei mesi
        const monthsHtml = buildMonthsGrid(program.months || []);
        
        // Costruisci la visualizzazione delle zone
        const zonesHtml = buildZonesGrid(program.steps || []);
        
        // Card del programma
        const programCard = document.createElement('div');
        programCard.className = `program-card ${isActive ? 'active-program' : ''}`;
        programCard.setAttribute('data-program-id', programId);
        
        programCard.innerHTML = `
            <div class="program-header">
                <h3>${program.name || 'Programma senza nome'}</h3>
                ${isActive ? '<div class="active-indicator">In esecuzione</div>' : ''}
            </div>
            <div class="program-content">
                <div class="info-row">
                    <div class="info-label">Orario:</div>
                    <div class="info-value">${program.activation_time || 'Non impostato'}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Cadenza:</div>
                    <div class="info-value">${formatRecurrence(program.recurrence, program.interval_days)}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Ultima esecuzione:</div>
                    <div class="info-value">${program.last_run_date || 'Mai eseguito'}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Mesi attivi:</div>
                    <div class="info-value">
                        <div class="months-grid">
                            ${monthsHtml}
                        </div>
                    </div>
                </div>
                <div class="info-row">
                    <div class="info-label">Zone:</div>
                    <div class="info-value">
                        <div class="zones-grid">
                            ${zonesHtml}
                        </div>
                    </div>
                </div>
            </div>
            <div class="program-actions">
                <div class="action-row">
                    <button class="btn btn-start ${isActive ? 'disabled' : ''}" 
                            onclick="startProgram('${programId}')" 
                            ${isActive ? 'disabled' : ''}>
                        <span class="btn-icon">▶</span> Avvia ora
                    </button>
                    <button class="btn btn-stop ${!isActive ? 'disabled' : ''}" 
                            onclick="stopProgram()" 
                            ${!isActive ? 'disabled' : ''}>
                        <span class="btn-icon">■</span> Stop
                    </button>
                </div>
                <div class="action-row">
                    <button class="btn btn-edit" onclick="editProgram('${programId}')">
                        <span class="btn-icon">✎</span> Modifica
                    </button>
                    <button class="btn btn-delete" onclick="deleteProgram('${programId}')">
                        <span class="btn-icon">🗑</span> Elimina
                    </button>
                </div>
            </div>
        `;
        
        container.appendChild(programCard);
    });
    
    // Aggiungi controllo programmi automatici globale
    const autoControlContainer = document.createElement('div');
    autoControlContainer.className = 'auto-control';
    autoControlContainer.style.gridColumn = '1/-1';
    autoControlContainer.style.margin = '20px 0';
    autoControlContainer.style.padding = '15px';
    autoControlContainer.style.backgroundColor = '#f9f9f9';
    autoControlContainer.style.borderRadius = '12px';
    autoControlContainer.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.05)';
    autoControlContainer.style.textAlign = 'center';
    
    // Verifica se i programmi automatici sono abilitati dalle impostazioni utente
    const autoEnabled = window.userData && window.userData.automatic_programs_enabled;
    
    autoControlContainer.innerHTML = `
        <h3 style="margin-bottom:15px">Controllo Globale Programmi Automatici</h3>
        <div class="auto-switch" style="display:inline-flex;border-radius:24px;overflow:hidden;box-shadow:0 2px 4px rgba(0,0,0,0.1)">
            <button class="auto-btn on ${autoEnabled ? 'active' : ''}" onclick="toggleAutomaticPrograms(true)">
                Automatici ON
            </button>
            <button class="auto-btn off ${!autoEnabled ? 'active' : ''}" onclick="toggleAutomaticPrograms(false)">
                Automatici OFF
            </button>
        </div>
    `;
    
    container.appendChild(autoControlContainer);
}

// Formatta la cadenza per la visualizzazione
function formatRecurrence(recurrence, interval_days) {
    if (!recurrence) return 'Non impostata';
    
    switch (recurrence) {
        case 'giornaliero':
            return 'Ogni giorno';
        case 'giorni_alterni':
            return 'Giorni alterni';
        case 'personalizzata':
            return `Ogni ${interval_days || 1} giorn${interval_days === 1 ? 'o' : 'i'}`;
        default:
            return recurrence;
    }
}

// Costruisce la griglia dei mesi
function buildMonthsGrid(activeMonths) {
    const months = [
        'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 
        'Maggio', 'Giugno', 'Luglio', 'Agosto', 
        'Settembre', 'Ottobre', 'Novembre', 'Dicembre'
    ];
    
    // Crea un Set per controlli di appartenenza più efficienti
    const activeMonthsSet = new Set(activeMonths || []);
    
    return months.map(month => {
        const isActive = activeMonthsSet.has(month);
        return `
            <div class="month-tag ${isActive ? 'active' : 'inactive'}">
                ${month.substring(0, 3)}
            </div>
        `;
    }).join('');
}

// Costruisce la griglia delle zone
function buildZonesGrid(steps) {
    if (!steps || steps.length === 0) {
        return '<div class="zone-tag" style="grid-column: 1/-1; text-align: center;">Nessuna zona configurata</div>';
    }
    
    return steps.map(step => {
        if (!step || step.zone_id === undefined) return '';
        
        const zoneName = zoneNameMap[step.zone_id] || `Zona ${step.zone_id + 1}`;
        return `
            <div class="zone-tag">
                ${zoneName}
                <span class="duration">${step.duration || 0} min</span>
            </div>
        `;
    }).join('');
}

// Funzione per avviare un programma
function startProgram(programId) {
    const startBtn = document.querySelector(`.program-card[data-program-id="${programId}"] .btn-start`);
    if (startBtn) {
        startBtn.classList.add('disabled');
        startBtn.disabled = true;
    }
    
    fetch('/start_program', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ program_id: programId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (typeof showToast === 'function') {
                showToast('Programma avviato con successo', 'success');
            }
            // Aggiorna immediatamente l'interfaccia
            fetchProgramState();
        } else {
            if (typeof showToast === 'function') {
                showToast(`Errore nell'avvio del programma: ${data.error || 'Errore sconosciuto'}`, 'error');
            }
        }
    })
    .catch(error => {
        console.error("Errore durante l'avvio del programma:", error);
        if (typeof showToast === 'function') {
            showToast("Errore di rete durante l'avvio del programma", 'error');
        }
    })
    .finally(() => {
        if (startBtn) {
            startBtn.classList.remove('disabled');
            startBtn.disabled = false;
        }
    });
}

// Funzione per arrestare un programma
function stopProgram() {
    const stopBtns = document.querySelectorAll('.btn-stop');
    stopBtns.forEach(btn => {
        btn.classList.add('disabled');
        btn.disabled = true;
    });
    
    fetch('/stop_program', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (typeof showToast === 'function') {
                showToast('Programma arrestato con successo', 'success');
            }
            // Aggiorna immediatamente l'interfaccia
            fetchProgramState();
        } else {
            if (typeof showToast === 'function') {
                showToast(`Errore nell'arresto del programma: ${data.error || 'Errore sconosciuto'}`, 'error');
            }
        }
    })
    .catch(error => {
        console.error("Errore durante l'arresto del programma:", error);
        if (typeof showToast === 'function') {
            showToast("Errore di rete durante l'arresto del programma", 'error');
        }
    })
    .finally(() => {
        stopBtns.forEach(btn => {
            btn.classList.remove('disabled');
            btn.disabled = false;
        });
    });
}

// Funzione editProgram in view_programs.js

function editProgram(programId) {
    // Salva l'ID del programma in localStorage per recuperarlo nella pagina di modifica
    localStorage.setItem('editProgramId', programId);
    
    // Vai alla pagina dedicata alla modifica
    loadPage('modify_program.html');
}

// Funzione per eliminare un programma
function deleteProgram(programId) {
    if (!confirm('Sei sicuro di voler eliminare questo programma? Questa operazione non può essere annullata.')) {
        return;
    }
    
    fetch('/delete_program', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: programId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (typeof showToast === 'function') {
                showToast('Programma eliminato con successo', 'success');
            }
            // Ricarica i programmi
            loadUserSettingsAndPrograms();
        } else {
            if (typeof showToast === 'function') {
                showToast(`Errore nell'eliminazione del programma: ${data.error || 'Errore sconosciuto'}`, 'error');
            }
        }
    })
    .catch(error => {
        console.error("Errore durante l'eliminazione del programma:", error);
        if (typeof showToast === 'function') {
            showToast("Errore di rete durante l'eliminazione del programma", 'error');
        }
    });
}

// Funzione per attivare/disattivare i programmi automatici
function toggleAutomaticPrograms(enable) {
    // Disabilita i pulsanti durante la richiesta
    const autoBtns = document.querySelectorAll('.auto-btn');
    autoBtns.forEach(btn => btn.disabled = true);
    
    fetch('/toggle_automatic_programs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enable })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Aggiorna lo stato globale
            if (window.userData) {
                window.userData.automatic_programs_enabled = enable;
            }
            
            updateAutoProgramsStatus(enable);
            
            // Aggiorna lo stato attivo dei pulsanti
            document.querySelectorAll('.auto-btn.on').forEach(btn => {
                btn.classList.toggle('active', enable);
            });
            document.querySelectorAll('.auto-btn.off').forEach(btn => {
                btn.classList.toggle('active', !enable);
            });
            
            if (typeof showToast === 'function') {
                showToast(`Programmi automatici ${enable ? 'attivati' : 'disattivati'} con successo`, 'success');
            }
        } else {
            if (typeof showToast === 'function') {
                showToast(`Errore: ${data.error || 'Errore sconosciuto'}`, 'error');
            }
        }
    })
    .catch(error => {
        console.error('Errore durante la modifica dello stato dei programmi automatici:', error);
        if (typeof showToast === 'function') {
            showToast('Errore di rete', 'error');
        }
    })
    .finally(() => {
        // Riabilita i pulsanti
        autoBtns.forEach(btn => btn.disabled = false);
    });
}

// Inizializzazione al caricamento del documento
document.addEventListener('DOMContentLoaded', initializeViewProgramsPage);