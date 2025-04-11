"""
Modulo per la gestione delle zone di irrigazione.
Gestisce l'attivazione e la disattivazione delle zone, rispettando i limiti impostati dall'utente.
"""
import time
import machine
from machine import Pin
import uasyncio as asyncio
from settings_manager import load_user_settings
from log_manager import log_event
from program_state import program_running, load_program_state

# Variabili globali con tipi più specifici per migliorare la chiarezza e l'efficienza
active_zones = {}  # Dict[int, Dict[str, any]]
zone_pins = {}     # Dict[int, Pin]
safety_relay = None  # Pin or None

def initialize_pins():
    """
    Inizializza i pin del sistema di irrigazione.
    
    Returns:
        boolean: True se almeno una zona è stata inizializzata, False altrimenti
    """
    global zone_pins, safety_relay
    
    settings = load_user_settings()
    if not settings:
        log_event("Errore: Impossibile caricare le impostazioni utente", "ERROR")
        print("Errore: Impossibile caricare le impostazioni utente.")
        return False

    zones = settings.get('zones', [])
    pins = {}

    # Inizializza i pin per le zone
    initialized_zones = 0
    for zone in zones:
        if not isinstance(zone, dict):
            continue
            
        zone_id = zone.get('id')
        pin_number = zone.get('pin')
        if pin_number is None or zone_id is None:
            continue
            
        try:
            pin = Pin(pin_number, Pin.OUT)
            pin.value(1)  # Relè spento (logica attiva bassa)
            pins[zone_id] = pin
            initialized_zones += 1
            log_event(f"Zona {zone_id} inizializzata sul pin {pin_number}", "INFO")
            print(f"Zona {zone_id} inizializzata sul pin {pin_number}.")
        except Exception as e:
            log_event(f"Errore durante l'inizializzazione del pin per la zona {zone_id}: {e}", "ERROR")
            print(f"Errore durante l'inizializzazione del pin per la zona {zone_id}: {e}")

    # Inizializza il pin per il relè di sicurezza
    safety_relay_pin = settings.get('safety_relay', {}).get('pin')
    safety_relay_obj = None
    
    if safety_relay_pin is not None:
        try:
            safety_relay_obj = Pin(safety_relay_pin, Pin.OUT)
            safety_relay_obj.value(1)  # Relè spento (logica attiva bassa)
            log_event(f"Relè di sicurezza inizializzato sul pin {safety_relay_pin}", "INFO")
            print(f"Relè di sicurezza inizializzato sul pin {safety_relay_pin}.")
        except Exception as e:
            log_event(f"Errore durante l'inizializzazione del relè di sicurezza: {e}", "ERROR")
            print(f"Errore durante l'inizializzazione del relè di sicurezza: {e}")
            safety_relay_obj = None

    zone_pins = pins
    safety_relay = safety_relay_obj
    
    return initialized_zones > 0

def get_zones_status():
    """
    Ritorna lo stato attuale di tutte le zone.
    
    Returns:
        list: Lista di dizionari con lo stato di ogni zona
    """
    global active_zones
    zones_status = []
    
    try:
        settings = load_user_settings()
        if not settings or not isinstance(settings, dict):
            log_event("Errore: Impostazioni non valide durante il recupero dello stato delle zone", "ERROR")
            return []
            
        configured_zones = settings.get('zones', [])
        if not configured_zones or not isinstance(configured_zones, list):
            return []
            
        current_time = time.time()  # Ottimizzazione: chiamare time.time() una sola volta
        
        for zone in configured_zones:
            if not zone or not isinstance(zone, dict):
                continue
                
            zone_id = zone.get('id')
            if zone_id is None:
                continue
                
            if zone.get('status') != 'show':
                continue
                
            is_active = zone_id in active_zones
            
            zone_info = {
                'id': zone_id,
                'name': zone.get('name', f'Zona {zone_id + 1}'),
                'active': is_active,
                'remaining_time': 0
            }
            
            # Calcola il tempo rimanente se la zona è attiva
            if is_active:
                zone_data = active_zones.get(zone_id, {})
                start_time = zone_data.get('start_time', 0)
                duration = zone_data.get('duration', 0) * 60  # In secondi
                
                try:
                    elapsed = int(current_time - start_time)
                    remaining = max(0, duration - elapsed)
                    zone_info['remaining_time'] = remaining
                except Exception as e:
                    log_event(f"Errore nel calcolo del tempo rimanente per la zona {zone_id}: {e}", "ERROR")
                    zone_info['remaining_time'] = 0
                
            zones_status.append(zone_info)
        
        return zones_status
    except Exception as e:
        log_event(f"Errore nel get_zones_status: {e}", "ERROR")
        return []

def get_active_zones_count():
    """
    Ritorna il numero di zone attualmente attive.
    
    Returns:
        int: Numero di zone attive
    """
    global active_zones
    return len(active_zones)

def start_zone(zone_id, duration):
    """
    Attiva una zona di irrigazione.
    
    Args:
        zone_id: ID della zona da attivare
        duration: Durata dell'attivazione in minuti
        
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    global active_zones, zone_pins, safety_relay
    
    # Converti in interi
    try:
        zone_id = int(zone_id)
        duration = int(duration)
    except (ValueError, TypeError):
        log_event(f"Errore: Tipo di dati non valido per zone_id o duration", "ERROR")
        return False
    
    # Ricarica lo stato per avere dati aggiornati prima della verifica critica
    load_program_state()
    
    # Verifica se un programma è in esecuzione
    if program_running:
        log_event(f"Impossibile avviare la zona {zone_id}: un programma è già in esecuzione", "WARNING")
        print(f"Impossibile avviare la zona {zone_id}: un programma è già in esecuzione.")
        return False

    # Controlla se la zona esiste
    if zone_id not in zone_pins:
        log_event(f"Errore: Zona {zone_id} non trovata", "ERROR")
        print(f"Errore: Zona {zone_id} non trovata.")
        return False
    
    # Controlla che la durata sia valida
    settings = load_user_settings()
    max_duration = settings.get('max_zone_duration', 180)
    if duration <= 0 or duration > max_duration:
        log_event(f"Errore: Durata non valida per la zona {zone_id}", "ERROR")
        print(f"Errore: Durata non valida per la zona {zone_id}.")
        return False
    
    # Verifica il limite massimo di zone attive
    max_active_zones = settings.get('max_active_zones', 1)
    
    if len(active_zones) >= max_active_zones and zone_id not in active_zones:
        log_event(f"Impossibile avviare la zona {zone_id}: Numero massimo di zone attive raggiunto ({max_active_zones})", "WARNING")
        print(f"Impossibile avviare la zona {zone_id}: Numero massimo di zone attive raggiunto ({max_active_zones}).")
        return False

    # Operazione multipass: prima prepara tutto, poi esegue le azioni irreversibili
    # Questo riduce la possibilità di stati inconsistenti
    
    # FASE 1: Preparazione
    # Se la zona è già attiva, prepara la cancellazione del task precedente
    old_task = None
    if zone_id in active_zones and 'task' in active_zones[zone_id]:
        try:
            old_task = active_zones[zone_id]['task']
        except Exception as e:
            log_event(f"Errore accesso al task precedente: {e}", "WARNING")
    
    # FASE 2: Esecuzione delle operazioni
    # Accende il relè di sicurezza se non è già acceso e non ci sono zone attive
    if safety_relay and not active_zones:
        try:
            safety_relay.value(0)  # Attiva il relè di sicurezza (logica attiva bassa)
            log_event("Relè di sicurezza attivato", "INFO")
        except Exception as e:
            log_event(f"Errore durante l'attivazione del relè di sicurezza: {e}", "ERROR")
            return False

    # Attiva il relè per la zona specificata
    try:
        zone_pins[zone_id].value(0)  # Attiva la zona (logica attiva bassa)
        log_event(f"Zona {zone_id} avviata per {duration} minuti", "INFO")
    except Exception as e:
        log_event(f"Errore durante l'attivazione della zona {zone_id}: {e}", "ERROR")
        
        # Disattiva il relè di sicurezza se era stato appena attivato
        if safety_relay and not active_zones:
            try:
                safety_relay.value(1)  # Disattiva il relè di sicurezza (logica attiva bassa)
            except:
                pass  # Non loggare errori qui per evitare cascate di errori
        return False

    # FASE 3: Gestione del timer e dello stato
    # Cancella il vecchio task se esiste e non è già cancellato
    if old_task:
        try:
            if not old_task.cancelled():
                old_task.cancel()
        except Exception as e:
            log_event(f"Errore cancellazione task precedente: {e}", "WARNING")

    # Crea un nuovo task per lo spegnimento automatico
    task = asyncio.create_task(_zone_timer(zone_id, duration))
    
    # Registra la zona come attiva
    active_zones[zone_id] = {
        'start_time': time.time(),
        'duration': duration,  # Durata in minuti
        'task': task
    }
    
    return True

async def _zone_timer(zone_id, duration):
    """
    Timer asincrono per arrestare automaticamente la zona dopo la durata specificata.
    
    Args:
        zone_id: ID della zona
        duration: Durata in minuti
    """
    try:
        await asyncio.sleep(duration * 60)  # Durata in minuti convertita in secondi
        
        # Verificare che la zona sia ancora attiva prima di disattivarla
        # per evitare situazioni di race condition
        if zone_id in active_zones:
            await _safe_stop_zone(zone_id)
    except asyncio.CancelledError:
        # Normale quando la zona viene disattivata manualmente
        pass
    except Exception as e:
        log_event(f"Errore nel timer della zona {zone_id}: {e}", "ERROR")

async def _safe_stop_zone(zone_id):
    """
    Versione sicura e asincrona di stop_zone che può essere chiamata dal timer.
    
    Args:
        zone_id: ID della zona da disattivare
    """
    global active_zones, zone_pins, safety_relay
    
    # Verifica che i parametri di input siano validi
    try:
        zone_id = int(zone_id)
    except:
        log_event(f"Errore: zone_id non valido in _safe_stop_zone", "ERROR")
        return

    if zone_id not in zone_pins:
        return
    
    # Assicurati che la zona sia ancora attiva
    if zone_id not in active_zones:
        return

    # Disattiva il relè della zona
    try:
        zone_pins[zone_id].value(1)  # Disattiva la zona (logica attiva bassa)
        log_event(f"Zona {zone_id} arrestata automaticamente", "INFO")
    except Exception as e:
        log_event(f"Errore durante l'arresto automatico zona {zone_id}: {e}", "ERROR")
        return
    
    # Memorizza quante zone attive c'erano prima di rimuovere questa
    was_last_active = len(active_zones) == 1
    
    # Rimuovi la zona dalle zone attive
    del active_zones[zone_id]
    
    # Spegne il relè di sicurezza se questa era l'ultima zona attiva
    if safety_relay and was_last_active:
        try:
            safety_relay.value(1)  # Disattiva il relè di sicurezza (logica attiva bassa)
            log_event("Relè di sicurezza disattivato", "INFO")
        except Exception as e:
            log_event(f"Errore durante lo spegnimento del relè di sicurezza: {e}", "ERROR")

def stop_zone(zone_id):
    """
    Disattiva una zona di irrigazione.
    
    Args:
        zone_id: ID della zona da disattivare
        
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    global active_zones, zone_pins, safety_relay
    
    # Converti zone_id in intero e verifica che sia valido
    try:
        zone_id = int(zone_id)
    except (ValueError, TypeError):
        log_event(f"Errore: Tipo di dati non valido per zone_id in stop_zone", "ERROR")
        return False

    if zone_id not in zone_pins:
        log_event(f"Errore: Zona {zone_id} non trovata per l'arresto", "ERROR")
        return False

    # FASE 1: Controlla se la zona è attiva
    zone_data = None
    was_last_active = False
    
    if zone_id in active_zones:
        zone_data = active_zones[zone_id]
        was_last_active = len(active_zones) == 1
    
    # FASE 2: Disattiva il relè della zona
    try:
        zone_pins[zone_id].value(1)  # Disattiva la zona (logica attiva bassa)
        log_event(f"Zona {zone_id} arrestata", "INFO")
    except Exception as e:
        log_event(f"Errore durante l'arresto della zona {zone_id}: {e}", "ERROR")
        return False

    # FASE 3: Gestione dello stato e del task
    # Rimuovi la zona dalle zone attive
    if zone_id in active_zones:
        del active_zones[zone_id]
        
        # Cancella il task se esiste
        if zone_data and 'task' in zone_data and zone_data['task']:
            try:
                task = zone_data['task']
                # Verifica se il task non è il task corrente per evitare "can't cancel self"
                current_task = asyncio.current_task()
                if task is not current_task and not task.cancelled():
                    task.cancel()
            except Exception as e:
                log_event(f"Errore cancellazione task zona {zone_id}: {e}", "WARNING")

    # FASE 4: Spegni il relè di sicurezza se questa era l'ultima zona attiva
    if safety_relay and was_last_active and not active_zones:
        try:
            safety_relay.value(1)  # Disattiva il relè di sicurezza (logica attiva bassa)
            log_event("Relè di sicurezza disattivato", "INFO")
        except Exception as e:
            log_event(f"Errore spegnimento relè sicurezza: {e}", "ERROR")
            return False
            
    return True

def stop_all_zones():
    """
    Disattiva tutte le zone attive.
    
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    global active_zones, zone_pins, safety_relay
    
    # Se non ci sono zone attive, non fare nulla
    if not active_zones:
        return True
        
    success = True
    had_errors = False
    
    # Ottimizzazione: crea una copia delle chiavi per evitare errori durante l'iterazione
    zone_ids = list(active_zones.keys())
    
    # FASE 1: Prova a disattivare ogni zona normalmente
    for zone_id in zone_ids:
        if not stop_zone(zone_id):
            had_errors = True
            success = False
    
    # FASE 2: Se ci sono ancora zone attive, forza la disattivazione
    if active_zones:
        log_event("Zone ancora attive dopo il primo tentativo. Forzatura disattivazione.", "WARNING")
        remaining_ids = list(active_zones.keys())
        
        for zone_id in remaining_ids:
            try:
                if zone_id in zone_pins:
                    zone_pins[zone_id].value(1)  # Disattiva la zona (logica attiva bassa)
                
                # Cancella il task associato alla zona se possibile
                if zone_id in active_zones and 'task' in active_zones[zone_id]:
                    try:
                        task = active_zones[zone_id]['task']
                        if task and not task.cancelled():
                            task.cancel()
                    except Exception:
                        pass  # Ignora errori di cancellazione in questa fase
                
                # Rimuovi la zona dalle zone attive
                if zone_id in active_zones:
                    del active_zones[zone_id]
                
            except Exception as e:
                log_event(f"Errore disattivazione forzata zona {zone_id}: {e}", "ERROR")
                success = False
    
    # FASE 3: Disattiva sempre il relè di sicurezza, indipendentemente dal successo precedente
    if safety_relay:
        try:
            safety_relay.value(1)  # Disattiva il relè di sicurezza (logica attiva bassa)
            log_event("Relè di sicurezza disattivato durante arresto zone", "INFO")
        except Exception as e:
            log_event(f"Errore disattivazione relè sicurezza: {e}", "ERROR")
            success = False
    
    # FASE 4: Assicurati che active_zones sia vuoto in ogni caso
    if active_zones:
        log_event("Pulizia forzata dell'elenco zone attive", "WARNING")
        active_zones.clear()
    
    # Se non ci sono stati errori, ma avevamo rilevato problemi,
    # aggiungi un log informativo che conferma la risoluzione
    if success and had_errors:
        log_event("Tutte le zone sono state arrestate con successo dopo errori iniziali", "INFO")
    elif success:
        log_event("Tutte le zone arrestate correttamente", "INFO")
    
    return success