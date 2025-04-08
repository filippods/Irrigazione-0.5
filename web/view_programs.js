// view_programs.js - Script per la pagina di visualizzazione programmi

// =================== VARIABILI GLOBALI ===================
let programStatusInterval = null;      // Intervallo per il polling dello stato
let programsData = {};                 // Cache dei dati dei programmi
let zoneNameMap = {};                  // Mappatura ID zona -> nome zona
let lastKnownState = null;             // Ultimo stato conosciuto (per confronti)
let pollingAccelerated = false;        // Flag per indicare se il polling è accelerato
let retryInProgress = false;           // Flag per evitare richieste multiple contemporanee

// Costanti di configurazione
const NORMAL_POLLING_INTERVAL = 5000;  // 5 secondi per il polling normale
const FAST_POLLING_INTERVAL = 1000;    // 1 secondo per il polling accelerato
const MAX_API_RETRIES = 3;             // Numero massimo di tentativi per le chiamate API

// =================== INIZIALIZZAZIONE ===================

/**
 * Inizializza la pagina di visualizzazione programmi
 */
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

/**
 * Pulisce le risorse quando l'utente lascia la pagina
 */
function cleanupViewProgramsPage() {
    stopProgramStatusPolling();
}

// =================== GESTIONE POLLING ===================

/**
 * Avvia il polling dello stato dei programmi
 */
function startProgramStatusPolling() {
    // Esegui subito
    fetchProgramState();
    
    // Imposta l'intervallo per il polling
    programStatusInterval = setInterval(fetchProgramState, NORMAL_POLLING_INTERVAL);
    console.log("Polling dello stato dei programmi avviato");
}

/**
 * Ferma il polling dello stato dei programmi
 */
function stopProgramStatusPolling() {
    if (programStatusInterval) {
        clearInterval(programStatusInterval);
        programStatusInterval = null;
        console.log("Polling dello stato dei programmi fermato");
    }
}

/**
 * Ottiene lo stato del programma corrente con gestione degli errori migliorata
 */
function fetchProgramState() {
    // Evita richieste sovrapposte se una è in corso e in retry
    if (retryInProgress) return;
    
    fetch('/get_program_state')
        .then(response => {
            if (!response.ok) throw new Error(`Errore HTTP: ${response.status}`);
            return response.json();
        })
        .then(state => {
            if (state && typeof state === 'object') {
                // Salva l'ultimo stato conosciuto per confronti
                const previousState = lastKnownState;
                lastKnownState = state;
                
                // Aggiorna l'UI con il nuovo stato
                updateProgramsUI(state);
                
                // Se c'è un programma in esecuzione, aggiorna l'UI con maggiori dettagli
                if (state.program_running && state.current_program_id) {
                    updateRunningProgramStatus(state);
                    
                    // Se siamo passati da non in esecuzione a in esecuzione, accelera il polling
                    if (previousState && !previousState.program_running && !pollingAccelerated) {
                        acceleratePolling();
                    }
                } else {
                    // Rimuovi eventuali indicatori di stato se non c'è un programma in esecuzione
                    hideRunningStatus();
                    
                    // Se siamo passati da in esecuzione a non in esecuzione, ripristina polling normale
                    if (previousState && previousState.program_running && pollingAccelerated) {
                        restoreNormalPolling();
                    }
                }
            } else {
                console.error("Formato di risposta non valido per lo stato del programma");
            }
        })
        .catch(error => {
            console.error('Errore nel recupero dello stato del programma:', error);
            // Non aggiorniamo l'UI in caso di errore per evitare visualizzazioni errate
        });
}

/**
 * Accelera temporaneamente il polling durante l'esecuzione iniziale di un programma
 */
function acceleratePolling() {
    if (pollingAccelerated) return;
    
    console.log("Accelerazione polling per monitoraggio stato");
    pollingAccelerated = true;
    
    // Ferma il polling normale
    stopProgramStatusPolling();
    
    // Imposta un intervallo più frequente
    programStatusInterval = setInterval(fetchProgramState, FAST_POLLING_INTERVAL);
    
    // Dopo 15 secondi, ripristina l'intervallo normale
    setTimeout(restoreNormalPolling, 15000);
}

/**
 * Ripristina il polling normale
 */
function restoreNormalPolling() {
    if (!pollingAccelerated) return;
    
    console.log("Ripristino polling normale");
    pollingAccelerated = false;
    
    // Ferma il polling accelerato
    stopProgramStatusPolling();
    
    // Ripristina l'intervallo normale
    programStatusInterval = setInterval(fetchProgramState, NORMAL_POLLING_INTERVAL);
}

// =================== CARICAMENTO DATI ===================

/**
 * Carica le impostazioni utente e i programmi
 */
function loadUserSettingsAndPrograms() {
    // Mostra l'indicatore di caricamento
    const programsContainer = document.getElementById('programs-container');
    if (programsContainer) {
        programsContainer.innerHTML = '<div class="loading">Caricamento programmi...</div>';
    }
    
    // Uso Promise.all per fare richieste parallele
    Promise.all([
        // Carica le impostazioni utente per ottenere i nomi delle zone
        fetch('/data/user_settings.json').then(response => {
            if (!response.ok) throw new Error('Errore nel caricamento delle impostazioni utente');
            return response.json();
        }),
        // Carica i programmi
        fetch('/data/program.json').then(response => {
            if (!response.ok) throw new Error('Errore nel caricamento dei programmi');
            return response.json();
        }),
        // Carica lo stato corrente
        fetch('/get_program_state').then(response => {
            if (!response.ok) throw new Error('Errore nel caricamento dello stato del programma');
            return response.json();
        })
    ])
    .then(([settings, programs, state]) => {
        // Salva l'ultimo stato conosciuto
        lastKnownState = state;
        
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
        
        // Mostra un messaggio di errore con pulsante di riprova
        const programsContainer = document.getElementById('programs-container');
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

// =================== RENDERING UI ===================

/**
 * Renderizza le card dei programmi
 * @param {Object} programs - Oggetto contenente i programmi
 * @param {Object} state - Oggetto contenente lo stato corrente
 */
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
                        <span class="btn-icon">▶</span> ON
                    </button>
                    <button class="btn btn-stop ${!isActive ? 'disabled' : ''}" 
                            onclick="stopProgram()" 
                            ${!isActive ? 'disabled' : ''}>
                        <span class="btn-icon">■</span> OFF
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
    
    // Se c'è un programma in esecuzione, aggiorna subito lo stato
    if (state.program_running && state.current_program_id) {
        updateRunningProgramStatus(state);
    }
}

/**
 * Aggiorna l'interfaccia in base allo stato del programma
 * @param {Object} state - Stato del programma
 */
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

/**
 * Aggiorna le informazioni dettagliate sul programma in esecuzione
 * @param {Object} state - Stato del programma
 */
function updateRunningProgramStatus(state) {
    // Ottieni il div per il programma attivo, se esiste
    const activeCard = document.querySelector(`.program-card[data-program-id="${state.current_program_id}"]`);
    
    if (!activeCard) return;
    
    // Se abbiamo informazioni sulla zona attiva, mostrale
    if (state.active_zone) {
        // Crea o aggiorna la sezione di stato di esecuzione
        let statusSection = activeCard.querySelector('.running-status-section');
        
        if (!statusSection) {
            // Crea la sezione se non esiste già
            statusSection = document.createElement('div');
            statusSection.className = 'running-status-section';
            statusSection.style.cssText = 'background-color: #e6fff5; padding: 10px; margin-top: 10px; border-radius: 8px; border: 1px solid #b3e6cc;';
            
            // Inseriscila prima delle azioni
            const programActions = activeCard.querySelector('.program-actions');
            if (programActions) {
                activeCard.insertBefore(statusSection, programActions);
            }
        }
        
        // Calcola il tempo rimanente in formato leggibile
        const remainingSeconds = state.active_zone.remaining_time || 0;
        const minutes = Math.floor(remainingSeconds / 60);
        const seconds = remainingSeconds % 60;
        const formattedTime = `${minutes}:${seconds.toString().padStart(2, '0')}`;
        
        // Determina l'avanzamento della zona attiva
        let progressPercentage = 0;
        const steps = programsData[state.current_program_id]?.steps || [];
        const currentStep = steps.find(step => step.zone_id === state.active_zone.id);
        
        if (currentStep) {
            const totalSeconds = currentStep.duration * 60;
            const elapsedSeconds = totalSeconds - remainingSeconds;
            progressPercentage = Math.min(Math.max((elapsedSeconds / totalSeconds) * 100, 0), 100);
        } else {
            // Fallback, dovrebbe sempre trovare lo step corrispondente
            progressPercentage = calculateProgressPercentage(remainingSeconds);
        }
        
        // Aggiorna il contenuto dello status section
        statusSection.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 5px;">Stato di Esecuzione:</div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span>Zona Attiva:</span>
                <span>${state.active_zone.name}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span>Tempo Rimanente:</span>
                <span>${formattedTime}</span>
            </div>
            <div style="height: 10px; background-color: #f0f0f0; border-radius: 5px; overflow: hidden; margin-top: 8px;">
                <div style="height: 100%; width: ${progressPercentage}%; 
                            background: linear-gradient(90deg, #0099ff, #00cc66); 
                            border-radius: 5px;"></div>
            </div>
        `;
    }
}

/**
 * Nasconde gli elementi di stato quando un programma non è in esecuzione
 */
function hideRunningStatus() {
    const statusSections = document.querySelectorAll('.running-status-section');
    statusSections.forEach(section => {
        section.remove();
    });
}

/**
 * Costruisce la griglia dei mesi
 * @param {Array} activeMonths - Array di mesi attivi
 * @returns {string} HTML per la griglia dei mesi
 */
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

/**
 * Costruisce la griglia delle zone
 * @param {Array} steps - Array di passi del programma
 * @returns {string} HTML per la griglia delle zone
 */
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

/**
 * Calcola la percentuale di avanzamento per la barra di progresso
 * @param {number} remainingSeconds - Secondi rimanenti 
 * @returns {number} Percentuale di avanzamento
 */
function calculateProgressPercentage(remainingSeconds) {
    // Questa è un'approssimazione, in quanto non conosciamo la durata totale della zona
    // quindi assumiamo che la maggior parte delle zone durano circa 10 minuti
    const estimatedTotalSeconds = 10 * 60;
    const elapsedPercentage = 100 - (remainingSeconds / estimatedTotalSeconds * 100);
    
    // Limita il valore tra 0 e 100
    return Math.min(Math.max(elapsedPercentage, 0), 100);
}

/**
 * Formatta la cadenza per la visualizzazione
 * @param {string} recurrence - Tipo di ricorrenza
 * @param {number} interval_days - Intervallo giorni per ricorrenza personalizzata
 * @returns {string} Descrizione formattata della ricorrenza
 */
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

// =================== AZIONI PROGRAMMI ===================

/**
 * Avvia un programma
 * @param {string} programId - ID del programma da avviare
 */
function startProgram(programId) {
    // Previeni clic multipli
    if (retryInProgress) return;
    retryInProgress = true;
    
    const startBtn = document.querySelector(`.program-card[data-program-id="${programId}"] .btn-start`);
    if (startBtn) {
        startBtn.classList.add('disabled');
        startBtn.disabled = true;
    }
    
    // Tenta più volte la richiesta in caso di errore di rete
    let retryCount = 0;
    
    function attemptStartProgram() {
        fetch('/start_program', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ program_id: programId })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Errore HTTP: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            retryInProgress = false;
            
            if (data.success) {
                if (typeof showToast === 'function') {
                    showToast('Programma avviato con successo', 'success');
                }
                // Aggiorna immediatamente l'interfaccia e accelera il polling
                fetchProgramState();
                acceleratePolling();
            } else {
                if (typeof showToast === 'function') {
                    showToast(`Errore nell'avvio del programma: ${data.error || 'Errore sconosciuto'}`, 'error');
                }
                
                // Riabilita il pulsante in caso di errore
                if (startBtn) {
                    startBtn.classList.remove('disabled');
                    startBtn.disabled = false;
                }
            }
        })
        .catch(error => {
            console.error("Errore durante l'avvio del programma:", error);
            
            // Tenta nuovamente se non abbiamo raggiunto il numero massimo di tentativi
            if (retryCount < MAX_API_RETRIES) {
                retryCount++;
                console.log(`Tentativo di avviare il programma ${retryCount}/${MAX_API_RETRIES}`);
                
                // Ritenta dopo un breve ritardo
                setTimeout(attemptStartProgram, 500 * retryCount);
            } else {
                retryInProgress = false;
                
                if (typeof showToast === 'function') {
                    showToast("Errore di rete durante l'avvio del programma", 'error');
                }
                
                // Riabilita il pulsante dopo il numero massimo di tentativi
                if (startBtn) {
                    startBtn.classList.remove('disabled');
                    startBtn.disabled = false;
                }
            }
        });
    }
    
    // Avvia il primo tentativo
    attemptStartProgram();
}

/**
 * Arresta il programma in esecuzione
 */
function stopProgram() {
    // Previeni clic multipli
    if (retryInProgress) return;
    retryInProgress = true;
    
    const stopBtns = document.querySelectorAll('.btn-stop');
    stopBtns.forEach(btn => {
        btn.classList.add('disabled');
        btn.disabled = true;
    });
    
    // Tenta più volte la richiesta in caso di errore di rete
    let retryCount = 0;
    
    function attemptStopProgram() {
        fetch('/stop_program', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Errore HTTP: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            retryInProgress = false;
            
            if (data.success) {
                if (typeof showToast === 'function') {
                    showToast('Programma arrestato con successo', 'success');
                }
                // Aggiorna immediatamente l'interfaccia
                fetchProgramState();
                // Riabilita i pulsanti dopo il successo
                stopBtns.forEach(btn => {
                    btn.classList.remove('disabled');
                    btn.disabled = false;
                });
            } else {
                if (typeof showToast === 'function') {
                    showToast(`Errore nell'arresto del programma: ${data.error || 'Errore sconosciuto'}`, 'error');
                }
                
                // Riabilita i pulsanti in caso di errore
                stopBtns.forEach(btn => {
                    btn.classList.remove('disabled');
                    btn.disabled = false;
                });
            }
        })
        .catch(error => {
            console.error("Errore durante l'arresto del programma:", error);
            
            // Tenta nuovamente se non abbiamo raggiunto il numero massimo di tentativi
            if (retryCount < MAX_API_RETRIES) {
                retryCount++;
                console.log(`Tentativo di arrestare il programma ${retryCount}/${MAX_API_RETRIES}`);
                
                // Ritenta dopo un breve ritardo (con aumenti progressivi)
                setTimeout(attemptStopProgram, 500 * retryCount);
            } else {
                retryInProgress = false;
                
                if (typeof showToast === 'function') {
                    showToast("Errore di rete durante l'arresto del programma", 'error');
                }
                
                // Riabilita i pulsanti dopo il numero massimo di tentativi
                stopBtns.forEach(btn => {
                    btn.classList.remove('disabled');
                    btn.disabled = false;
                });
            }
        });
    }
    
    // Avvia il primo tentativo
    attemptStopProgram();
}

/**
 * Vai alla pagina di modifica del programma
 * @param {string} programId - ID del programma da modificare
 */
function editProgram(programId) {
    // Salva l'ID del programma in localStorage per recuperarlo nella pagina di modifica
    localStorage.setItem('editProgramId', programId);
    
    // Vai alla pagina dedicata alla modifica
    loadPage('modify_program.html');
}

/**
 * Elimina un programma
 * @param {string} programId - ID del programma da eliminare
 */
function deleteProgram(programId) {
    if (!confirm('Sei sicuro di voler eliminare questo programma? Questa operazione non può essere annullata.')) {
        return;
    }
    
    // Mostra un indicatore di caricamento sulla card
    const programCard = document.querySelector(`.program-card[data-program-id="${programId}"]`);
    if (programCard) {
        // Aggiunge un overlay di caricamento
        const loadingOverlay = document.createElement('div');
        loadingOverlay.className = 'loading-overlay';
        loadingOverlay.style.cssText = `
            position: absolute; 
            top: 0; 
            left: 0; 
            width: 100%; 
            height: 100%; 
            background-color: rgba(255,255,255,0.7); 
            display: flex; 
            justify-content: center; 
            align-items: center;
            z-index: 100;
            border-radius: 12px;
        `;
        loadingOverlay.innerHTML = '<div class="loading" style="position: static; transform: scale(0.6);"></div>';
        programCard.style.position = 'relative';
        programCard.appendChild(loadingOverlay);
    }
    
    // Disabilita pulsanti di azione
    const actionButtons = programCard ? programCard.querySelectorAll('.btn') : [];
    actionButtons.forEach(btn => {
        btn.disabled = true;
    });
    
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
            // Effetto di dissolvenza prima di rimuovere la card
            if (programCard) {
                programCard.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                programCard.style.opacity = '0';
                programCard.style.transform = 'scale(0.9)';
                
                // Rimuovi la card dopo l'animazione
                setTimeout(() => {
                    programCard.remove();
                    
                    // Se era l'unico programma, mostra il messaggio "nessun programma"
                    const container = document.getElementById('programs-container');
                    if (container && !container.querySelector('.program-card')) {
                        container.innerHTML = `
                            <div class="empty-state">
                                <h3>Nessun programma configurato</h3>
                                <p>Crea il tuo primo programma di irrigazione per iniziare a usare il sistema.</p>
                                <button class="btn" onclick="loadPage('create_program.html')">Crea Programma</button>
                            </div>
                        `;
                    }
                }, 500);
            } else {
                // Ricarica i programmi se non troviamo la card
                loadUserSettingsAndPrograms();
            }
        } else {
            // Rimuovi l'overlay di caricamento
            if (programCard) {
                const loadingOverlay = programCard.querySelector('.loading-overlay');
                if (loadingOverlay) {
                    loadingOverlay.remove();
                }
            }
            
            // Riabilita i pulsanti
            actionButtons.forEach(btn => {
                btn.disabled = false;
            });
            
            if (typeof showToast === 'function') {
                showToast(`Errore nell'eliminazione del programma: ${data.error || 'Errore sconosciuto'}`, 'error');
            }
        }
    })
    .catch(error => {
        console.error("Errore durante l'eliminazione del programma:", error);
        
        // Rimuovi l'overlay di caricamento
        if (programCard) {
            const loadingOverlay = programCard.querySelector('.loading-overlay');
            if (loadingOverlay) {
                loadingOverlay.remove();
            }
        }
        
        // Riabilita i pulsanti
        actionButtons.forEach(btn => {
            btn.disabled = false;
        });
        
        if (typeof showToast === 'function') {
            showToast("Errore di rete durante l'eliminazione del programma", 'error');
        }
    });
}

/**
 * Attiva o disattiva l'automatizzazione di un programma
 * @param {string} programId - ID del programma
 * @param {boolean} enable - true per attivare, false per disattivare
 */
function toggleProgramAutomatic(programId, enable) {
    // Previeni manipolazioni durante il processo
    const toggle = document.getElementById(`auto-switch-${programId}`);
    if (toggle) toggle.disabled = true;
    
    fetch('/toggle_program_automatic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ program_id: programId, enable: enable })
    })
    .then(response => response.json())
    .then(data => {
        if (toggle) toggle.disabled = false;
        
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
            
            // Aggiorna i dati salvati localmente
            if (programsData[programId]) {
                programsData[programId].automatic_enabled = enable;
            }
        } else {
            if (typeof showToast === 'function') {
                showToast(`Errore: ${data.error || 'Errore sconosciuto'}`, 'error');
            }
            
            // Ripristina lo stato dell'interruttore in caso di errore
            const autoSwitch = document.getElementById(`auto-switch-${programId}`);
            if (autoSwitch) {
                autoSwitch.checked = !enable; // Inverti lo stato
            }
        }
    })
    .catch(error => {
        if (toggle) toggle.disabled = false;
        
        console.error('Errore di rete:', error);
        if (typeof showToast === 'function') {
            showToast('Errore di rete', 'error');
        }
        
        // Ripristina lo stato dell'interruttore in caso di errore
        const autoSwitch = document.getElementById(`auto-switch-${programId}`);
        if (autoSwitch) {
            autoSwitch.checked = !enable; // Inverti lo stato
        }
    });
}

// Inizializzazione al caricamento del documento
document.addEventListener('DOMContentLoaded', initializeViewProgramsPage);