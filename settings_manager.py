"""
Modulo per la gestione delle impostazioni utente.
Gestisce il caricamento, salvataggio e ripristino delle impostazioni utente.
"""
import ujson
import uos
import gc
from log_manager import log_event

# Configurazione predefinita
FACTORY_SETTINGS = {
    "client_enabled": False,
    "wifi": {"ssid": "", "password": ""},
    "ap": {"ssid": "IrrigationSystem", "password": "12345678"},
    "zones": [
        {"id": 0, "status": "show", "pin": 14, "name": "Zona 1"},
        {"id": 1, "status": "show", "pin": 15, "name": "Zona 2"},
        {"id": 2, "status": "show", "pin": 16, "name": "Zona 3"},
        {"id": 3, "status": "show", "pin": 17, "name": "Zona 4"},
        {"id": 4, "status": "show", "pin": 18, "name": "Zona 5"},
        {"id": 5, "status": "show", "pin": 19, "name": "Zona 6"},
        {"id": 6, "status": "show", "pin": 20, "name": "Zona 7"},
        {"id": 7, "status": "show", "pin": 21, "name": "Zona 8"}
    ],
    "max_active_zones": 3,
    "activation_delay": 5,
    "safety_relay": {"pin": 13},
    "automatic_programs_enabled": False,
    "max_zone_duration": 180  # 3 ore in minuti
}

def ensure_directory_exists(path):
    """
    Crea la directory se non esiste
    
    Args:
        path: Percorso della directory da creare
    """
    try:
        dirs = path.split('/')
        current_dir = ""
        for d in dirs:
            if d:
                current_dir += f"/{d}"
                try:
                    uos.stat(current_dir)
                except OSError:
                    try:
                        uos.mkdir(current_dir)
                    except OSError:
                        pass
    except Exception as e:
        print(f"Errore nella creazione della directory {path}: {e}")

def load_user_settings():
    """
    Carica le impostazioni da user_settings.json, garantendo valori di default se mancano.
    
    Returns:
        dict: Impostazioni utente
    """
    ensure_directory_exists('/data')
    
    try:
        with open('/data/user_settings.json', 'r') as f:
            settings = ujson.load(f)
            
            # Garantisce che tutte le chiavi necessarie siano presenti
            settings.setdefault('zones', FACTORY_SETTINGS['zones'])
            settings.setdefault('max_active_zones', 3)
            settings.setdefault('activation_delay', 5)
            settings.setdefault('safety_relay', {"pin": 13})
            settings.setdefault('ap', {"ssid": "IrrigationSystem", "password": "12345678"})
            settings.setdefault('wifi', {"ssid": "", "password": ""})
            settings.setdefault('automatic_programs_enabled', False)
            settings.setdefault('client_enabled', False)
            settings.setdefault('max_zone_duration', 180)  # 3 ore in minuti
            
            return settings
    except (OSError, ValueError) as e:
        log_event(f"Errore durante il caricamento delle impostazioni utente: {e}", "ERROR")
        print(f"Errore durante il caricamento delle impostazioni utente: {e}")
        
        # Crea un nuovo file con le impostazioni di fabbrica
        factory_reset()
        
        return FACTORY_SETTINGS.copy()

def save_user_settings(settings):
    """
    Salva le impostazioni su user_settings.json
    
    Args:
        settings: Dizionario delle impostazioni da salvare
        
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    ensure_directory_exists('/data')
    
    try:
        # Validazione delle impostazioni
        if not isinstance(settings, dict):
            log_event("Tentativo di salvare impostazioni non valide", "ERROR")
            return False

        # Assicurati che tutte le chiavi siano presenti
        for key, value in FACTORY_SETTINGS.items():
            if key not in settings:
                settings[key] = value
                
        # Validazione delle zone
        if 'zones' in settings:
            for i, zone in enumerate(settings['zones']):
                if 'id' not in zone:
                    zone['id'] = i
                if 'status' not in zone:
                    zone['status'] = 'show'
                if 'pin' not in zone:
                    zone['pin'] = 14 + i
                if 'name' not in zone:
                    zone['name'] = f"Zona {i+1}"
        
        with open('/data/user_settings.json', 'w') as f:
            ujson.dump(settings, f)
            log_event("Impostazioni utente salvate con successo", "INFO")
            print("Impostazioni salvate con successo.")
            
        # Forza garbage collection
        gc.collect()
        return True
    except OSError as e:
        log_event(f"Errore durante il salvataggio delle impostazioni utente: {e}", "ERROR")
        print(f"Errore durante il salvataggio delle impostazioni utente: {e}")
        return False

def reset_user_settings():
    """
    Ripristina le impostazioni utente ai valori di fabbrica
    
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    try:
        save_user_settings(FACTORY_SETTINGS.copy())
        log_event("Impostazioni utente ripristinate ai valori di fabbrica", "INFO")
        print("Impostazioni di fabbrica ripristinate.")
        return True
    except Exception as e:
        log_event(f"Errore durante il ripristino delle impostazioni: {e}", "ERROR")
        print(f"Errore durante il ripristino delle impostazioni: {e}")
        return False

def reset_factory_data():
    """
    Ripristina tutti i dati ai valori di fabbrica
    
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    try:
        # Ripristina impostazioni utente
        reset_user_settings()
        
        # Cancella i programmi
        ensure_directory_exists('/data')
        with open('/data/program.json', 'w') as f:
            ujson.dump({}, f)
            
        # Cancella lo stato dei programmi
        with open('/data/program_state.json', 'w') as f:
            ujson.dump({"program_running": False, "current_program_id": None}, f)
            
        log_event("Tutti i dati ripristinati ai valori di fabbrica", "INFO")
        print("Dati di fabbrica ripristinati.")
        return True
    except Exception as e:
        log_event(f"Errore durante il ripristino dei dati di fabbrica: {e}", "ERROR")
        print(f"Errore durante il ripristino dei dati di fabbrica: {e}")
        return False

def factory_reset():
    """
    Ripristina le impostazioni di fabbrica
    
    Returns:
        boolean: True se l'operazione è riuscita, False altrimenti
    """
    try:
        save_user_settings(FACTORY_SETTINGS.copy())
        log_event("Impostazioni di fabbrica ripristinate", "INFO")
        print("Impostazioni di fabbrica ripristinate.")
        return True
    except Exception as e:
        log_event(f"Errore durante il ripristino delle impostazioni di fabbrica: {e}", "ERROR")
        print(f"Errore durante il ripristino delle impostazioni di fabbrica: {e}")
        return False