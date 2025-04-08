"""
Modulo per la gestione delle impostazioni utente.
Gestisce il caricamento, il salvataggio e il reset delle impostazioni.
"""
import ujson
import uos as os
import gc

# Rimuoviamo l'importazione diretta di log_manager che causa il ciclo
# from log_manager import log_event

# Funzione per il logging che evita importazioni circolari
def _log_event(message, level="INFO"):
    try:
        # Importazione locale per evitare dipendenze circolari
        from log_manager import log_event
        log_event(message, level)
    except ImportError:
        # Fallback di logging se l'importazione fallisce
        print(f"[{level}] {message}")

# Percorsi dei file
USER_SETTINGS_FILE = '/data/user_settings.json'
FACTORY_SETTINGS_FILE = '/data/factory_settings.json'
PROGRAM_FILE = '/data/program.json'

def ensure_directory_exists(path):
    """
    Assicura che una directory esista, creandola se necessario.
    
    Args:
        path: Percorso della directory
        
    Returns:
        boolean: True se la directory esiste o è stata creata, False altrimenti
    """
    if path == '':
        return True
    
    try:
        # Se il percorso termina con "/", rimuovilo
        if path.endswith('/'):
            path = path[:-1]
            
        # Verifica se la directory esiste
        try:
            os.stat(path)
            return True
        except OSError:
            # La directory non esiste, crea le directory necessarie
            components = path.split('/')
            current_path = ''
            
            for component in components:
                if component:
                    current_path += '/' + component
                    try:
                        os.stat(current_path)
                    except OSError:
                        try:
                            os.mkdir(current_path)
                        except OSError as e:
                            _log_event(f"Errore nella creazione della directory {current_path}: {e}", "ERROR")
                            return False
            return True
    except Exception as e:
        _log_event(f"Errore durante la verifica/creazione della directory {path}: {e}", "ERROR")
        return False

def load_user_settings():
    """
    Carica le impostazioni utente dal file JSON.
    Se il file non esiste, viene creato con valori predefiniti.
    
    Returns:
        dict: Dizionario delle impostazioni
    """
    try:
        try:
            # Tenta di aprire il file delle impostazioni
            with open(USER_SETTINGS_FILE, 'r') as f:
                settings = ujson.load(f)
                return settings
        except OSError:
            # Il file non esiste, crea impostazioni predefinite
            default_settings = create_default_settings()
            save_user_settings(default_settings)
            return default_settings
        except ValueError:
            # Il file esiste ma non è un JSON valido
            _log_event(f"File {USER_SETTINGS_FILE} danneggiato, ripristino impostazioni predefinite", "WARNING")
            default_settings = create_default_settings()
            save_user_settings(default_settings)
            return default_settings
    except Exception as e:
        _log_event(f"Errore durante il caricamento delle impostazioni utente: {e}", "ERROR")
        try:
            # Tenta un ultimo sforzo per fornire impostazioni valide
            return create_default_settings()
        except:
            # In caso di errore critico, restituisci un dizionario vuoto
            return {}

def save_user_settings(settings):
    """
    Salva le impostazioni utente in un file JSON.
    
    Args:
        settings: Dizionario delle impostazioni da salvare
        
    Returns:
        boolean: True se il salvataggio è riuscito, False altrimenti
    """
    try:
        # Assicurati che la directory esista
        ensure_directory_exists('/data')
        
        # Salva le impostazioni
        with open(USER_SETTINGS_FILE, 'w') as f:
            ujson.dump(settings, f)
        
        # Forza la garbage collection dopo operazioni su file
        gc.collect()
        
        return True
    except Exception as e:
        _log_event(f"Errore durante il salvataggio delle impostazioni utente: {e}", "ERROR")
        return False

def create_default_settings():
    """
    Crea impostazioni predefinite.
    
    Returns:
        dict: Dizionario delle impostazioni predefinite
    """
    return {
        'safety_relay': {
            'pin': 13
        },
        'zones': [
            {'id': 0, 'status': 'show', 'pin': 14, 'name': 'Giardino'},
            {'id': 1, 'status': 'show', 'pin': 15, 'name': 'Terrazzo'},
            {'id': 2, 'status': 'show', 'pin': 16, 'name': 'Cancelletto'},
            {'id': 3, 'status': 'show', 'pin': 17, 'name': 'Zona 4'},
            {'id': 4, 'status': 'show', 'pin': 18, 'name': 'Zona 5'},
            {'id': 5, 'status': 'show', 'pin': 19, 'name': 'Zona 6'},
            {'id': 6, 'status': 'show', 'pin': 20, 'name': 'Zona 7'},
            {'id': 7, 'status': 'show', 'pin': 21, 'name': 'Zona 8'}
        ],
        'automatic_programs_enabled': True,
        'max_active_zones': 3,
        'wifi': {
            'ssid': '',
            'password': ''
        },
        'activation_delay': 5,
        'client_enabled': False,
        'ap': {
            'ssid': 'IrrigationSystem',
            'password': '12345678'
        },
        'max_zone_duration': 180
    }

def reset_user_settings():
    """
    Resetta le impostazioni utente ai valori predefiniti.
    
    Returns:
        boolean: True se il reset è riuscito, False altrimenti
    """
    try:
        default_settings = create_default_settings()
        success = save_user_settings(default_settings)
        
        if success:
            _log_event("Impostazioni utente resettate ai valori predefiniti", "INFO")
        
        return success
    except Exception as e:
        _log_event(f"Errore durante il reset delle impostazioni utente: {e}", "ERROR")
        return False

def reset_factory_data():
    """
    Resetta tutti i dati ai valori di fabbrica.
    Resetta impostazioni utente e programmi.
    
    Returns:
        boolean: True se il reset è riuscito, False altrimenti
    """
    try:
        # Reset impostazioni utente
        user_settings_ok = reset_user_settings()
        
        # Reset programmi
        programs_ok = True
        try:
            with open(PROGRAM_FILE, 'w') as f:
                ujson.dump({}, f)
        except Exception as e:
            _log_event(f"Errore durante il reset dei programmi: {e}", "ERROR")
            programs_ok = False
        
        # Resetta lo stato del programma
        program_state_ok = True
        try:
            with open('/data/program_state.json', 'w') as f:
                ujson.dump({'program_running': False, 'current_program_id': None}, f)
        except Exception as e:
            _log_event(f"Errore durante il reset dello stato del programma: {e}", "ERROR")
            program_state_ok = False
        
        success = user_settings_ok and programs_ok and program_state_ok
        
        if success:
            _log_event("Tutti i dati resettati ai valori di fabbrica", "INFO")
        else:
            _log_event("Reset dati di fabbrica completato con errori", "WARNING")
        
        # Forza la garbage collection
        gc.collect()
        
        return success
    except Exception as e:
        _log_event(f"Errore durante il reset dei dati di fabbrica: {e}", "ERROR")
        return False