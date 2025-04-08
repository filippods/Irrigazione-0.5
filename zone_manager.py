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
from program_state import program_running

# Variabili globali
active_zones = {}
zone_pins = {}
safety_relay = None

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
        pin_number = zone.get('pin')
        if pin_number is None:
            continue
            
        try:
            pin = Pin(pin_number, Pin.OUT)
            pin.value(1)  # Relè spento (logica attiva bassa)
            pins[zone['id']] = pin
            initialized_zones += 1
            log_event(f"Zona {zone['id']} inizializzata sul pin {pin_number}", "INFO")
            print(f"Zona {zone['id']} inizializzata sul pin {pin_number}.")
        except Exception as e:
            log_event(f"Errore durante l'inizializzazione del pin per la zona {zone['id']}: {e}", "ERROR")
            print(f"Errore durante l'inizializzazione del pin per la zona {zone['id']}: {e}")

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
        
        for zone in configured_zones:
            if not zone or not isinstance(zone, dict):
                continue
                
            zone_id = zone.get('id')
            if zone_id is None:
                continue
                
            if zone.get('status') != 'show':
                continue
                
            zone_info = {
                'id': zone_id,
                'name': zone.get('name', f'Zona {zone_id + 1}'),
                'active': zone_id in active_zones,
                'remaining_time': 0
            }
            
            # Calcola il tempo rimanente se la zona è attiva
            if zone_id in active_zones:
                zone_data = active_zones.get(zone_id, {})
                start_time = zone_data.get('start_time', 0)
                duration = zone_data.get('duration', 0) * 60  # In secondi
                
                try:
                    elapsed = int(time.time() - start_time)
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
    zone_id = int(zone_id)
    duration = int(duration)
    
    # Verifica se un programma è in esecuzione
    # Nota: Usiamo program_running importato direttamente all'inizio del file
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

    # Accende il relè di sicurezza se non è già acceso
    if safety_relay and not active_zones:
        try:
            safety_relay.value(0)  # Attiva il relè di sicurezza (logica attiva bassa)
            log_event("Relè di sicurezza attivato", "INFO")
            print("Relè di sicurezza attivato.")
        except Exception as e:
            log_event(f"Errore durante l'attivazione del relè di sicurezza: {e}", "ERROR")
            print(f"Errore durante l'attivazione del relè di sicurezza: {e}")
            return False

    # Attiva il relè per la zona specificata
    try:
        zone_pins[zone_id].value(0)  # Attiva la zona (logica attiva bassa)
        log_event(f"Zona {zone_id} avviata per {duration} minuti", "INFO")
        print(f"Zona {zone_id} avviata per {duration} minuti.")
    except Exception as e:
        log_event(f"Errore durante l'attivazione della zona {zone_id}: {e}", "ERROR")
        print(f"Errore durante l'attivazione della zona {zone_id}: {e}")
        return False

    # Se la zona è già attiva, cancella il task precedente
    if zone_id in active_zones and 'task' in active_zones[zone_id]:
        try:
            active_zones[zone_id]['task'].cancel()
        except Exception as e:
            log_event(f"Errore cancellazione task precedente: {e}", "WARNING")
            print(f"Errore cancellazione task precedente: {e}")

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
        if zone_id in active_zones:
            stop_zone(zone_id)
    except asyncio.CancelledError:
        log_event(f"Timer per la zona {zone_id} cancellato", "INFO")
        print(f"Timer per la zona {zone_id} cancellato.")
    except Exception as e:
        log_event(f"Errore nel timer della zona {zone_id}: {e}", "ERROR")
        print(f"Errore nel timer della zona {zone_id}: {e}")

def stop_zone(zone_id):
    """
    Disattiva una zona di irrigazione.
    
    Args:
        zone_id: ID della zona da disattivare
        
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    global active_zones, zone_pins, safety_relay
    
    # Converti in intero
    zone_id = int(zone_id)

    if zone_id not in zone_pins:
        log_event(f"Errore: Zona {zone_id} non trovata per l'arresto", "ERROR")
        print(f"Errore: Zona {zone_id} non trovata per l'arresto.")
        return False

    # Disattiva il relè della zona
    try:
        zone_pins[zone_id].value(1)  # Disattiva la zona (logica attiva bassa)
        log_event(f"Zona {zone_id} arrestata", "INFO")
        print(f"Zona {zone_id} arrestata.")
    except Exception as e:
        log_event(f"Errore durante l'arresto della zona {zone_id}: {e}", "ERROR")
        print(f"Errore durante l'arresto della zona {zone_id}: {e}")
        return False

    # Cancella il task associato alla zona
    if zone_id in active_zones:
        try:
            if 'task' in active_zones[zone_id] and active_zones[zone_id]['task']:
                active_zones[zone_id]['task'].cancel()
        except Exception as e:
            log_event(f"Errore durante la cancellazione del task per la zona {zone_id}: {e}", "WARNING")
            print(f"Errore durante la cancellazione del task per la zona {zone_id}: {e}")
        del active_zones[zone_id]

    # Spegne il relè di sicurezza se non ci sono altre zone attive
    if safety_relay and not active_zones:
        try:
            safety_relay.value(1)  # Disattiva il relè di sicurezza (logica attiva bassa)
            log_event("Relè di sicurezza disattivato", "INFO")
            print("Relè di sicurezza disattivato.")
        except Exception as e:
            log_event(f"Errore durante lo spegnimento del relè di sicurezza: {e}", "ERROR")
            print(f"Errore durante lo spegnimento del relè di sicurezza: {e}")
            return False
            
    return True

def stop_all_zones():
    """
    Disattiva tutte le zone attive.
    
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    global active_zones
    
    if not active_zones:
        return True
        
    success = True
    for zone_id in list(active_zones.keys()):
        if not stop_zone(zone_id):
            success = False
    
    log_event("Tutte le zone arrestate", "INFO")
    print("Tutte le zone arrestate.")
    return success