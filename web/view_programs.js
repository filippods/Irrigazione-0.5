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
        
        // Get the automatic status (default to true for backward compatibility)
        const isAutomatic = program.automatic_enabled !== false;
        
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
                <!-- Row for automatic execution toggle -->
                <div class="info-row auto-execution-row">
                    <div class="info-value" style="display: flex; align-items: center; justify-content: space-between;">
                        <div id="auto-icon-${programId}" class="auto-status ${isAutomatic ? 'on' : 'off'}">
                            <i></i>
                            <span>Attivazione automatica: ${isAutomatic ? 'ON' : 'OFF'}</span>
                        </div>
                        <label class="toggle-switch">
                            <input type="checkbox" id="auto-switch-${programId}" 
                                   class="auto-program-toggle" 
                                   data-program-id="${programId}" 
                                   ${isAutomatic ? 'checked' : ''}
                                   onchange="toggleProgramAutomatic('${programId}', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
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

// Function to toggle the automatic status of a program
function toggleProgramAutomatic(programId, enable) {
    fetch('/toggle_program_automatic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ program_id: programId, enable: enable })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (typeof showToast === 'function') {
                showToast(`Automazione del programma ${enable ? 'attivata' : 'disattivata'} con successo`, 'success');
            }
            
            // Update the UI to reflect the new state
            const autoSwitch = document.getElementById(`auto-switch-${programId}`);
            if (autoSwitch) {
                autoSwitch.checked = enable;
            }
            
            // Aggiorna l'icona nella card
            const autoIcon = document.getElementById(`auto-icon-${programId}`);
            if (autoIcon) {
                autoIcon.className = enable ? 'auto-status on' : 'auto-status off';
                autoIcon.querySelector('span').textContent = `Attivazione automatica: ${enable ? 'ON' : 'OFF'}`;
            }
        } else {
            if (typeof showToast === 'function') {
                showToast(`Errore: ${data.error || 'Errore sconosciuto'}`, 'error');
            }
        }
    })
    .catch(error => {
        console.error('Errore di rete:', error);
        if (typeof showToast === 'function') {
            showToast('Errore di rete', 'error');
        }
    });
}

// Inizializzazione al caricamento del documento
document.addEventListener('DOMContentLoaded', initializeViewProgramsPage);