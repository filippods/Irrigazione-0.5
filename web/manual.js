// manual.js - Script per la pagina di controllo manuale

// Variabili globali
let maxActiveZones = 3;
let maxZoneDuration = 180; // durata massima in minuti
let progressIntervals = {};
let userSettings = {};
let zoneStatusInterval = null;

// Inizializza la pagina manuale
function initializeManualPage(userData) {
    console.log("Inizializzazione pagina controllo manuale");
    
    if (userData && Object.keys(userData).length > 0) {
        userSettings = userData;
        // Carica maxActiveZones dalle impostazioni utente
        maxActiveZones = userData.max_active_zones || 3;
        maxZoneDuration = userData.max_zone_duration || 180;
        renderZones(userData.zones || []);
    } else {
        // Se userData non è disponibile, carica le impostazioni dal server
        fetch('/data/user_settings.json')
            .then(response => {
                if (!response.ok) throw new Error('Errore nel caricamento delle impostazioni utente');
                return response.json();
            })
            .then(data => {
                userSettings = data;
                maxActiveZones = data.max_active_zones || 3;
                maxZoneDuration = data.max_zone_duration || 180;
                renderZones(data.zones || []);
            })
            .catch(error => {
                console.error('Errore nel caricamento delle impostazioni:', error);
                showToast('Errore nel caricamento delle impostazioni', 'error');
            });
    }
    
    // Avvia il polling per l'aggiornamento dello stato delle zone
    startZoneStatusPolling();
    
    // Pulisci quando si cambia pagina (window.onbeforeunload non funziona bene su ESP32)
    window.addEventListener('pagehide', cleanupManualPage);
}

// Funzione per avviare il polling dello stato delle zone
function startZoneStatusPolling() {
    // Esegui immediatamente e poi ogni 3 secondi
    fetchZonesStatus();
    zoneStatusInterval = setInterval(fetchZonesStatus, 3000);
    console.log("Polling zone avviato");
}

// Funzione per fermare il polling
function stopZoneStatusPolling() {
    if (zoneStatusInterval) {
        clearInterval(zoneStatusInterval);
        zoneStatusInterval = null;
        console.log("Polling zone fermato");
    }
}

// Pulisci quando si cambia pagina
function cleanupManualPage() {
    stopZoneStatusPolling();
    
    // Pulisci gli intervalli di progresso
    for (const id in progressIntervals) {
        if (progressIntervals[id]) {
            clearInterval(progressIntervals[id]);
        }
    }
    progressIntervals = {};
}

// Renderizza le zone basate sulle impostazioni utente
function renderZones(zones) {
    console.log("Renderizzazione zone:", zones);
    
    const container = document.getElementById('zone-container');
    if (!container) return;
    
    // Filtra solo le zone visibili (status: "show")
    const visibleZones = Array.isArray(zones) ? zones.filter(zone => zone && zone.status === "show") : [];
    
    if (visibleZones.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <h3>Nessuna zona configurata</h3>
                <p>Configura le zone nelle impostazioni per poterle controllare manualmente.</p>
                <button class="button primary" onclick="loadPage('settings.html')">
                    Vai alle impostazioni
                </button>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    
    visibleZones.forEach(zone => {
        if (!zone || zone.id === undefined) return;
        
        const zoneCard = document.createElement('div');
        zoneCard.className = 'zone-card';
        zoneCard.id = `zone-${zone.id}`;
        
        // Per impostare correttamente il valore di default e il massimo dell'input durata
        const defaultDuration = Math.min(10, maxZoneDuration);
        
        zoneCard.innerHTML = `
            <h3>${zone.name || `Zona ${zone.id + 1}`}</h3>
            <div class="input-container">
                <input type="number" id="duration-${zone.id}" placeholder="Durata (minuti)" 
                       min="1" max="${maxZoneDuration}" value="${defaultDuration}">
                <div class="toggle-switch">
                    <label class="switch">
                        <input type="checkbox" id="toggle-${zone.id}" class="zone-toggle" data-zone-id="${zone.id}">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>
            <div class="progress-container">
                <progress id="progress-${zone.id}" value="0" max="100"></progress>
                <div class="timer-display" id="timer-${zone.id}">00:00</div>
            </div>
        `;
        container.appendChild(zoneCard);
    });
    
    // Aggiungi i listener dopo aver creato gli elementi
    attachZoneToggleFunctions();
    
    // Carica subito lo stato delle zone
    fetchZonesStatus();
}

// Recupera lo stato delle zone dal server
function fetchZonesStatus() {
    fetch('/get_zones_status')
        .then(response => {
            if (!response.ok) throw new Error('Errore nel recupero dello stato delle zone');
            return response.json();
        })
        .then(zonesStatus => {
            console.log("Stato zone ricevuto:", zonesStatus);
            updateZonesUI(zonesStatus);
        })
        .catch(error => {
            console.error('Errore nel recupero dello stato delle zone:', error);
        });
}

// Aggiorna l'interfaccia in base allo stato delle zone
function updateZonesUI(zonesStatus) {
    if (!Array.isArray(zonesStatus)) return;
    
    zonesStatus.forEach(zone => {
        if (!zone || zone.id === undefined) return;
        
        const toggle = document.getElementById(`toggle-${zone.id}`);
        const zoneCard = document.getElementById(`zone-${zone.id}`);
        
        if (!toggle || !zoneCard) return;
        
        // Aggiorna lo stato del toggle senza innescare l'evento change
        const isCurrentlyChecked = toggle.checked;
        if (isCurrentlyChecked !== zone.active) {
            // Rimuovi temporaneamente l'event listener
            const originalOnChange = toggle.onchange;
            toggle.onchange = null;
            
            // Cambia lo stato
            toggle.checked = zone.active;
            
            // Ripristina l'event listener
            setTimeout(() => {
                toggle.onchange = originalOnChange;
            }, 0);
        }
        
        // Aggiorna la classe visiva della card
        if (zone.active) {
            zoneCard.classList.add('active');
        } else {
            zoneCard.classList.remove('active');
        }
        
        // Aggiorna la barra di progresso se la zona è attiva
        if (zone.active) {
            const progressBar = document.getElementById(`progress-${zone.id}`);
            const timerDisplay = document.getElementById(`timer-${zone.id}`);
            
            if (progressBar && timerDisplay) {
                // Se non c'è già un intervallo in corso per questa zona, creane uno
                if (!progressIntervals[zone.id]) {
                    // Trova la durata impostata nel campo input
                    const durationInput = document.getElementById(`duration-${zone.id}`);
                    // Durata in secondi
                    let duration = 0;
                    
                    if (durationInput) {
                        duration = parseInt(durationInput.value) * 60;
                    } else {
                        // Usa il tempo rimanente dal server
                        duration = zone.remaining_time;
                    }
                    
                    if (duration > 0) {
                        const remainingTime = zone.remaining_time;
                        const elapsedTime = duration - remainingTime;
                        updateProgressBar(zone.id, elapsedTime, duration, remainingTime);
                    }
                }
            }
        } else {
            // Se la zona non è attiva ma c'è un intervallo in corso, fermalo
            if (progressIntervals[zone.id]) {
                clearInterval(progressIntervals[zone.id]);
                delete progressIntervals[zone.id];
                
                // Resetta la barra di progresso
                const progressBar = document.getElementById(`progress-${zone.id}`);
                const timerDisplay = document.getElementById(`timer-${zone.id}`);
                
                if (progressBar && timerDisplay) {
                    progressBar.value = 0;
                    timerDisplay.textContent = '00:00';
                }
            }
        }
    });
}

// Aggiorna la barra di progresso
function updateProgressBar(zoneId, elapsedTime, totalTime, remainingTime) {
    const progressBar = document.getElementById(`progress-${zoneId}`);
    const timerDisplay = document.getElementById(`timer-${zoneId}`);
    
    if (!progressBar || !timerDisplay) return;
    
    // Imposta il valore iniziale
    const progressValue = (elapsedTime / totalTime) * 100;
    progressBar.value = progressValue;
    updateTimerDisplay(remainingTime, timerDisplay);
    
    // Cancella l'intervallo esistente se presente
    if (progressIntervals[zoneId]) {
        clearInterval(progressIntervals[zoneId]);
    }
    
    // Crea un nuovo intervallo
    progressIntervals[zoneId] = setInterval(() => {
        elapsedTime++;
        remainingTime--;
        
        if (remainingTime <= 0) {
            clearInterval(progressIntervals[zoneId]);
            delete progressIntervals[zoneId];
            progressBar.value = 0;
            timerDisplay.textContent = '00:00';
            
            // Aggiorna lo stato del toggle
            const toggle = document.getElementById(`toggle-${zoneId}`);
            if (toggle) toggle.checked = false;
            
            // Aggiorna la classe visiva della card
            const zoneCard = document.getElementById(`zone-${zoneId}`);
            if (zoneCard) zoneCard.classList.remove('active');
            
            return;
        }
        
        const newProgressValue = (elapsedTime / totalTime) * 100;
        progressBar.value = newProgressValue;
        updateTimerDisplay(remainingTime, timerDisplay);
    }, 1000);
}

// Aggiorna il display del timer
function updateTimerDisplay(timeInSeconds, displayElement) {
    const minutes = Math.floor(timeInSeconds / 60);
    const seconds = Math.floor(timeInSeconds % 60);
    const formattedTime = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    displayElement.textContent = formattedTime;
}

// Funzione per avviare una zona
function startZone(zoneId, duration) {
    console.log(`Tentativo di avvio zona ${zoneId} per ${duration} minuti`);
    
    // Verifica validità della durata
    if (isNaN(duration) || duration <= 0 || duration > maxZoneDuration) {
        showToast(`La durata deve essere tra 1 e ${maxZoneDuration} minuti`, 'warning');
        const toggle = document.getElementById(`toggle-${zoneId}`);
        if (toggle) toggle.checked = false;
        return;
    }
    
    // Aggiungi classe loading e disabilita il toggle
    const toggle = document.getElementById(`toggle-${zoneId}`);
    if (toggle) {
        toggle.disabled = true;
    }
    
    const zoneCard = document.getElementById(`zone-${zoneId}`);
    if (zoneCard) {
        zoneCard.classList.add('loading');
    }

    fetch('/start_zone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zone_id: zoneId, duration: duration })
    })
    .then(response => {
        // Riabilita il toggle
        if (toggle) toggle.disabled = false;
        if (zoneCard) zoneCard.classList.remove('loading');
        
        if (!response.ok) {
            throw new Error(`Errore HTTP: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log("Risposta dal server:", data);
        
        if (!data.success) {
            throw new Error(data.error || 'Errore durante l\'avvio della zona');
        }
        
        console.log(`Zona ${zoneId} avviata per ${duration} minuti.`);
        showToast(`Zona ${zoneId + 1} avviata per ${duration} minuti`, 'success');
        
        // La risposta positiva verrà gestita dall'aggiornamento automatico dello stato
        fetchZonesStatus();
    })
    .catch(error => {
        console.error('Errore durante l\'avvio della zona:', error);
        showToast(`Errore: ${error.message}`, 'error');
        
        // Riporta il toggle allo stato OFF
        if (toggle) toggle.checked = false;
        
        // Aggiorna lo stato per sicurezza
        fetchZonesStatus();
    });
}

// Funzione per fermare una zona
function stopZone(zoneId) {
    // Aggiungi classe loading e disabilita il toggle
    const toggle = document.getElementById(`toggle-${zoneId}`);
    if (toggle) {
        toggle.disabled = true;
    }
    
    const zoneCard = document.getElementById(`zone-${zoneId}`);
    if (zoneCard) {
        zoneCard.classList.add('loading');
    }
    
    fetch('/stop_zone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zone_id: zoneId })
    })
    .then(response => {
        // Riabilita il toggle
        if (toggle) toggle.disabled = false;
        if (zoneCard) zoneCard.classList.remove('loading');
        
        if (!response.ok) {
            throw new Error(`Errore HTTP: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (!data.success) {
            throw new Error(data.error || 'Errore durante l\'arresto della zona');
        }
        
        console.log(`Zona ${zoneId} arrestata.`);
        showToast(`Zona ${zoneId + 1} arrestata`, 'info');
        
        // La risposta positiva verrà gestita dall'aggiornamento automatico dello stato
        fetchZonesStatus();
    })
    .catch(error => {
        console.error('Errore durante l\'arresto della zona:', error);
        showToast(`Errore: ${error.message}`, 'error');
        
        // Ripristina lo stato precedente
        if (toggle) {
            toggle.checked = true;
            toggle.disabled = false;
        }
        
        // Aggiorna lo stato per sicurezza
        fetchZonesStatus();
    });
}

// Aggiungi i listener agli elementi toggle
function attachZoneToggleFunctions() {
    const zoneToggles = document.querySelectorAll('.zone-toggle');
    console.log('Numero di toggle zone trovati:', zoneToggles.length);
    
    zoneToggles.forEach(toggle => {
        toggle.addEventListener('change', event => {
            const zoneId = parseInt(event.target.getAttribute('data-zone-id'));
            const isChecked = event.target.checked;
            
            if (isChecked) {
                // Avvia la zona
                const durationInput = document.getElementById(`duration-${zoneId}`);
                const duration = durationInput ? parseInt(durationInput.value) : 0;
                
                if (isNaN(duration) || duration <= 0) {
                    showToast('Inserisci una durata valida in minuti', 'warning');
                    event.target.checked = false;
                    return;
                }
                
                startZone(zoneId, duration);
            } else {
                // Ferma la zona
                stopZone(zoneId);
            }
        });
    });
}

// Inizializzazione quando il documento è caricato
document.addEventListener('DOMContentLoaded', () => {
    // Se userSettings è già disponibile, inizializza la pagina
    if (window.userData && Object.keys(window.userData).length > 0) {
        initializeManualPage(window.userData);
    }
});