"""
Modulo per la gestione della connettività WiFi.
Gestisce la modalità client e la modalità access point.
"""
import network
import ujson
import time
import gc
import uos
from settings_manager import load_user_settings, save_user_settings
from log_manager import log_event
import uasyncio as asyncio

WIFI_RETRY_INTERVAL = 30  # Secondi tra un tentativo di riconnessione e l'altro
MAX_WIFI_RETRIES = 5      # Numero massimo di tentativi prima di passare alla modalità AP
AP_SSID_DEFAULT = "IrrigationSystem"
AP_PASSWORD_DEFAULT = "12345678"
WIFI_SCAN_FILE = '/data/wifi_scan.json'

def reset_wifi_module():
    """
    Disattiva e riattiva il modulo WiFi per forzare un reset completo.
    
    Returns:
        boolean: True se il reset è riuscito, False altrimenti
    """
    try:
        wlan_sta = network.WLAN(network.STA_IF)
        wlan_ap = network.WLAN(network.AP_IF)
        
        log_event("Reset del modulo WiFi in corso...", "INFO")
        print("Resetting WiFi module...")
        wlan_sta.active(False)
        wlan_ap.active(False)
        
        time.sleep(1)
        wlan_sta.active(True)
        log_event("Reset del modulo WiFi completato", "INFO")
        print("WiFi module reset completed.")
        return True
    except Exception as e:
        log_event(f"Errore durante il reset del modulo WiFi: {e}", "ERROR")
        print(f"Errore durante il reset del modulo WiFi: {e}")
        return False

def save_wifi_scan_results(network_list):
    """
    Salva i risultati della scansione Wi-Fi nel file wifi_scan.json.
    
    Args:
        network_list: Lista di reti WiFi trovate
    """
    try:
        # Assicurati che la directory data esista
        try:
            uos.stat('/data')
        except OSError:
            uos.mkdir('/data')
            
        with open(WIFI_SCAN_FILE, 'w') as f:
            ujson.dump(network_list, f)
        log_event(f"Risultati della scansione Wi-Fi salvati correttamente in {WIFI_SCAN_FILE}", "INFO")
        print(f"Risultati della scansione Wi-Fi salvati correttamente in {WIFI_SCAN_FILE}")
    except OSError as e:
        log_event(f"Errore durante il salvataggio dei risultati della scansione Wi-Fi: {e}", "ERROR")
        print(f"Errore durante il salvataggio dei risultati della scansione Wi-Fi: {e}")

def clear_wifi_scan_file():
    """
    Cancella il file wifi_scan.json.
    """
    try:
        with open(WIFI_SCAN_FILE, 'w') as f:
            ujson.dump([], f)  # Salviamo un array vuoto
            log_event(f"File {WIFI_SCAN_FILE} azzerato correttamente", "INFO")
            print(f"File {WIFI_SCAN_FILE} azzerato correttamente.")
    except Exception as e:
        log_event(f"Errore nell'azzerare il file {WIFI_SCAN_FILE}: {e}", "ERROR")
        print(f"Errore nell'azzerare il file {WIFI_SCAN_FILE}: {e}")
        
def connect_to_wifi(ssid, password):
    """
    Tenta di connettersi a una rete WiFi in modalità client.
    
    Args:
        ssid: SSID della rete WiFi
        password: Password della rete WiFi
        
    Returns:
        boolean: True se la connessione è riuscita, False altrimenti
    """
    wlan_sta = network.WLAN(network.STA_IF)
    log_event(f"Tentativo di connessione alla rete WiFi: {ssid}", "INFO")
    print(f"Trying to connect to WiFi SSID: {ssid}...")

    try:
        wlan_sta.active(True)
        retries = 0

        while not wlan_sta.isconnected() and retries < MAX_WIFI_RETRIES:
            wlan_sta.connect(ssid, password)
            for _ in range(10):  # Attendi fino a 10 secondi
                if wlan_sta.isconnected():
                    break
                time.sleep(1)
            retries += 1
            
            if not wlan_sta.isconnected() and retries < MAX_WIFI_RETRIES:
                log_event(f"Tentativo {retries} fallito, riprovo...", "WARNING")
                print(f"Tentativo {retries} fallito, riprovo...")

        if wlan_sta.isconnected():
            ip = wlan_sta.ifconfig()[0]
            log_event(f"Connesso con successo alla rete WiFi: {ssid} con IP {ip}", "INFO")
            print(f"Connected successfully to WiFi: {ip}")
            return True
        else:
            log_event(f"Impossibile connettersi alla rete WiFi: {ssid} dopo {MAX_WIFI_RETRIES} tentativi", "ERROR")
            print("Failed to connect to WiFi.")
            wlan_sta.active(False)
            return False
    except Exception as e:
        log_event(f"Errore durante la connessione alla rete WiFi: {e}", "ERROR")
        print(f"Errore durante la connessione alla rete WiFi: {e}")
        try:
            wlan_sta.active(False)
        except:
            pass
        return False

def start_access_point(ssid=None, password=None):
    """
    Avvia l'access point.
    
    Args:
        ssid: SSID dell'access point (opzionale)
        password: Password dell'access point (opzionale)
        
    Returns:
        boolean: True se l'access point è stato avviato, False altrimenti
    """
    try:
        settings = load_user_settings()  # Carica le impostazioni utente

        # Se SSID o password non sono passati come parametri, carica dalle impostazioni
        ap_config = settings.get('ap', {})
        ssid = ssid or ap_config.get('ssid', AP_SSID_DEFAULT)  # Default SSID se non presente
        password = password or ap_config.get('password', AP_PASSWORD_DEFAULT)  # Default password se non presente

        wlan_ap = network.WLAN(network.AP_IF)
        wlan_ap.active(True)

        # Configura l'AP con il SSID e la password
        if password and len(password) >= 8:
            wlan_ap.config(essid=ssid, password=password, authmode=3)  # 3 è WPA2
            auth_mode = "WPA2"
        else:
            wlan_ap.config(essid=ssid)  # AP sarà aperto se non è presente una password valida
            auth_mode = "Aperto"

        log_event(f"Access Point attivato con SSID: '{ssid}', sicurezza: {auth_mode}", "INFO")
        print(f"Access Point attivato con SSID: '{ssid}', sicurezza {'WPA2' if password and len(password) >= 8 else 'Nessuna'}")
        return True
    except Exception as e:
        log_event(f"Errore durante l'attivazione dell'Access Point: {e}", "ERROR")
        print(f"Errore durante l'attivazione dell'Access Point: {e}")
        try:
            wlan_ap.active(False)
        except:
            pass
        return False

def initialize_network():
    """
    Inizializza la rete WiFi (client o AP) in base alle impostazioni.
    
    Returns:
        boolean: True se l'inizializzazione è riuscita, False altrimenti
    """
    gc.collect()  # Effettua la garbage collection per liberare memoria
    settings = load_user_settings()
    if not isinstance(settings, dict):
        log_event("Errore: impostazioni utente non disponibili", "ERROR")
        print("Errore: impostazioni utente non disponibili.")
        return False

    client_enabled = settings.get('client_enabled', False)

    if client_enabled:
        # Modalità client attiva
        ssid = settings.get('wifi', {}).get('ssid')
        password = settings.get('wifi', {}).get('password')

        if ssid and password:
            success = connect_to_wifi(ssid, password)
            if success:
                log_event("Modalità client attivata con successo", "INFO")
                print("Modalità client attivata con successo.")
                return True
            else:
                log_event("Connessione alla rete WiFi fallita, passando alla modalità AP", "WARNING")
                print("Connessione alla rete WiFi fallita, passando alla modalità AP.")
        else:
            log_event("SSID o password non validi per il WiFi client", "WARNING")
            print("SSID o password non validi per il WiFi client.")

    # Se il client è disattivato o fallisce, avvia l'AP
    ap_ssid = settings.get('ap', {}).get('ssid', AP_SSID_DEFAULT)
    ap_password = settings.get('ap', {}).get('password', AP_PASSWORD_DEFAULT)
    success = start_access_point(ap_ssid, ap_password)
    return success

async def retry_client_connection():
    """
    Task asincrono che verifica periodicamente la connessione WiFi client e tenta di riconnettersi se necessario.
    """
    while True:
        try:
            await asyncio.sleep(WIFI_RETRY_INTERVAL)
            
            wlan_sta = network.WLAN(network.STA_IF)
            settings = load_user_settings()
            
            client_enabled = settings.get('client_enabled', False)

            if client_enabled:
                if not wlan_sta.isconnected():
                    log_event("Connessione WiFi client persa, tentativo di riconnessione...", "WARNING")
                    ssid = settings.get('wifi', {}).get('ssid')
                    password = settings.get('wifi', {}).get('password')
                    
                    if ssid and password:
                        success = connect_to_wifi(ssid, password)
                        if not success:
                            log_event(f"Impossibile riconnettersi a '{ssid}'. Attivazione della rete AP", "ERROR")
                            print(f"Impossibile riconnettersi a '{ssid}'. Attivazione della rete AP.")
                            
                            # Aggiorna le impostazioni solo dopo alcuni tentativi falliti
                            # per non disabilitare il client dopo una temporanea perdita di connessione
                            wlan_ap = network.WLAN(network.AP_IF)
                            if not wlan_ap.active():
                                start_access_point()
                    else:
                        log_event("SSID o password non validi. Impossibile riconnettersi", "ERROR")
                        print("SSID o password non validi. Impossibile riconnettersi.")
                else:
                    # Connessione attiva, verifica che l'AP sia disattivato se necessario
                    wlan_ap = network.WLAN(network.AP_IF)
                    if wlan_ap.active():
                        wlan_ap.active(False)
                        log_event("Access Point disattivato, modalità client attiva", "INFO")
            else:
                # La modalità client è disabilitata
                if wlan_sta.active():
                    log_event("Disattivazione della modalità client", "INFO")
                    print("Disattivazione della modalità client.")
                    wlan_sta.active(False)
                    
                # Assicurati che l'AP sia attivo
                wlan_ap = network.WLAN(network.AP_IF)
                if not wlan_ap.active():
                    log_event("AP non attivo, riattivazione...", "WARNING")
                    start_access_point()
        
        except Exception as e:
            log_event(f"Errore durante il retry della connessione WiFi: {e}", "ERROR")
            print(f"Errore durante il retry della connessione WiFi: {e}")
            await asyncio.sleep(5)  # Breve ritardo prima di riprovare in caso di errore