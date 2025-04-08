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
WIFI_RETRY_INTERVAL = 600 
WIFI_RETRY_INITIAL_INTERVAL = 30
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
    Se la connessione fallisce dopo 10 secondi, attiva la modalità AP.
    
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
        # Assicurati che il client sia attivo
        wlan_sta.active(True)
        time.sleep(1)  # Breve attesa per l'attivazione
        
        # Avvia la connessione
        wlan_sta.connect(ssid, password)
        
        # Attendi fino a 10 secondi per la connessione
        connection_timeout = 10
        for i in range(connection_timeout):
            if wlan_sta.isconnected():
                ip = wlan_sta.ifconfig()[0]
                log_event(f"Connesso con successo alla rete WiFi: {ssid} con IP {ip}", "INFO")
                print(f"Connected successfully to WiFi: {ip}")
                return True
            
            print(f"Attesa connessione... {i+1}/{connection_timeout} secondi")
            time.sleep(1)
        
        # Se arriviamo qui, la connessione è fallita
        log_event(f"Connessione a '{ssid}' fallita dopo {connection_timeout} secondi", "WARNING")
        print(f"Connessione a '{ssid}' fallita dopo {connection_timeout} secondi")
        
        # Non disattiviamo il client in caso di fallimento, 
        # il task retry_client_connection gestirà i tentativi futuri
        return False
    except Exception as e:
        log_event(f"Errore durante la connessione alla rete WiFi: {e}", "ERROR")
        print(f"Errore durante la connessione alla rete WiFi: {e}")
        
        # Non disattiviamo il client in caso di errore,
        # il task retry_client_connection gestirà i tentativi futuri
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

def setup_mdns(hostname="irrigation"):
    """
    Configura mDNS per l'accesso tramite hostname.local.
    Implementazione ottimizzata per ESP32 con gestione specifica per vari moduli mDNS.
    
    Args:
        hostname: Nome host da utilizzare (default: "irrigation")
        
    Returns:
        boolean: True se l'inizializzazione è riuscita, False altrimenti
    """
    try:
        # Evita errori sul bus i2c disattivando temporaneamente i2c
        # (problema noto con alcune versioni del firmware ESP32)
        try:
            from machine import Pin, I2C
            i2c_instances = []
            for i in range(2):  # ESP32 ha 2 periferiche I2C
                try:
                    i2c = I2C(i)
                    i2c.deinit()  # Disattiva temporaneamente
                    i2c_instances.append((i, i2c))
                except:
                    pass
        except:
            i2c_instances = []
            
        # Implementazione per ESP-IDF
        try:
            import esp
            if hasattr(esp, 'mdns_init'):
                esp.mdns_init()
                esp.mdns_add_service(hostname, "_http", "_tcp", 80)
                log_event(f"mDNS avviato con hostname: {hostname}.local (ESP-IDF)", "INFO")
                print(f"mDNS avviato con hostname: {hostname}.local (ESP-IDF)")
                
                # Reinizializza i2c se necessario
                for i, i2c in i2c_instances:
                    try:
                        i2c.init()
                    except:
                        pass
                        
                return True
        except (ImportError, AttributeError, Exception) as e:
            log_event(f"Errore con mdns ESP-IDF: {e}", "WARNING")
            
        # Implementazione per moduli network con mDNS incorporato
        try:
            import network
            if hasattr(network, 'mDNS'):
                network.mDNS.init(hostname)
                log_event(f"mDNS avviato con hostname: {hostname}.local (network)", "INFO")
                print(f"mDNS avviato con hostname: {hostname}.local (network)")
                
                # Reinizializza i2c se necessario
                for i, i2c in i2c_instances:
                    try:
                        i2c.init()
                    except:
                        pass
                        
                return True
        except (ImportError, AttributeError, Exception) as e:
            log_event(f"Errore con mdns network: {e}", "WARNING")
            
        # Implementazione per modulo mdns standard
        try:
            import mdns
            mdns.start(hostname)
            log_event(f"mDNS avviato con hostname: {hostname}.local (standard)", "INFO")
            print(f"mDNS avviato con hostname: {hostname}.local (standard)")
            
            # Reinizializza i2c se necessario
            for i, i2c in i2c_instances:
                try:
                    i2c.init()
                except:
                    pass
                    
            return True
        except (ImportError, Exception) as e:
            log_event(f"Errore con mdns standard: {e}", "WARNING")
            
        # Implementazione per modulo umdns per MicroPython
        try:
            import umdns
            umdns.start(hostname)
            log_event(f"mDNS avviato con hostname: {hostname}.local (umdns)", "INFO")
            print(f"mDNS avviato con hostname: {hostname}.local (umdns)")
            
            # Reinizializza i2c se necessario
            for i, i2c in i2c_instances:
                try:
                    i2c.init()
                except:
                    pass
                    
            return True
        except (ImportError, Exception) as e:
            log_event(f"Errore con umdns: {e}", "WARNING")
        
        # Se arriviamo qui, nessuna implementazione mDNS ha funzionato
        log_event("Nessun modulo mDNS disponibile, accesso tramite IP", "WARNING")
        print("Nessun modulo mDNS disponibile. Accesso tramite IP richiesto.")
        
        # Reinizializza i2c se necessario
        for i, i2c in i2c_instances:
            try:
                i2c.init()
            except:
                pass
                
        return False
    except Exception as e:
        log_event(f"Errore durante l'inizializzazione di mDNS: {e}", "ERROR")
        print(f"Errore durante l'inizializzazione di mDNS: {e}")
        return False

def initialize_network():
    """
    Inizializza la rete WiFi (client o AP) in base alle impostazioni.
    Implementa anche il fallback da client a AP se la connessione client fallisce.
    
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
                
                # Configura mDNS per accesso facilitato - tentativi multipli
                mdns_success = False
                for attempt in range(3):
                    if setup_mdns():
                        mdns_success = True
                        break
                    time.sleep(1)
                
                if not mdns_success:
                    log_event("Non è stato possibile configurare mDNS dopo 3 tentativi", "WARNING")
                
                return True
            else:
                log_event("Connessione alla rete WiFi fallita, passando alla modalità AP come fallback", "WARNING")
                print("Connessione alla rete WiFi fallita, passando alla modalità AP come fallback.")
                # La connessione client fallita, ma lasciamo il client attivo per i tentativi futuri
                # attivando anche l'AP come fallback
        else:
            log_event("SSID o password non validi per il WiFi client", "WARNING")
            print("SSID o password non validi per il WiFi client.")

    # Se il client è disattivato o fallisce, avvia l'AP
    ap_ssid = settings.get('ap', {}).get('ssid', AP_SSID_DEFAULT)
    ap_password = settings.get('ap', {}).get('password', AP_PASSWORD_DEFAULT)
    success = start_access_point(ap_ssid, ap_password)
    
    # Configura mDNS anche in modalità AP
    mdns_success = False
    for attempt in range(3):
        if setup_mdns():
            mdns_success = True
            break
        time.sleep(1)
    
    if not mdns_success:
        log_event("Non è stato possibile configurare mDNS in modalità AP dopo 3 tentativi", "WARNING")
    
    return success

async def retry_client_connection():
    """
    Task asincrono che verifica periodicamente la connessione WiFi client e tenta di riconnettersi se necessario.
    Implementa la seguente logica:
    1. Se la modalità client è abilitata ma non è connesso:
       - Tenta di riconnettersi immediatamente
       - Se fallisce, attiva la modalità AP ma continua a tentare la connessione client ogni 10 minuti
    2. Se la connessione client si stabilisce:
       - Disattiva la modalità AP
    3. Se la modalità client è disabilitata:
       - Assicura che la modalità client sia spenta e quella AP sia attiva
    """
    last_attempt_time = 0
    reconnection_tries = 0
    ap_failover_activated = False
    mdns_configured = False

    while True:
        try:
            current_time = time.time()
            wlan_sta = network.WLAN(network.STA_IF)
            wlan_ap = network.WLAN(network.AP_IF)
            settings = load_user_settings()
            
            client_enabled = settings.get('client_enabled', False)

            if client_enabled:
                # Modalità client abilitata nelle impostazioni
                if not wlan_sta.isconnected():
                    # Client non connesso - dobbiamo riconnetterlo o attivare AP come fallback
                    
                    # Determina se è il momento di tentare una riconnessione
                    retry_interval = WIFI_RETRY_INTERVAL if ap_failover_activated else WIFI_RETRY_INITIAL_INTERVAL
                    time_since_last_attempt = current_time - last_attempt_time
                    
                    if time_since_last_attempt >= retry_interval:
                        # È ora di tentare una riconnessione
                        log_event(f"Tentativo di riconnessione WiFi client (tentativo #{reconnection_tries + 1})", "INFO")
                        print(f"Tentativo di riconnessione WiFi client (tentativo #{reconnection_tries + 1})")
                        
                        ssid = settings.get('wifi', {}).get('ssid')
                        password = settings.get('wifi', {}).get('password')
                        
                        if ssid and password:
                            last_attempt_time = current_time
                            reconnection_tries += 1
                            
                            # Assicurati che sia attivo
                            if not wlan_sta.active():
                                wlan_sta.active(True)
                                await asyncio.sleep(1)
                                
                            # Tenta la connessione
                            wlan_sta.connect(ssid, password)
                            
                            # Attendi fino a 10 secondi per la connessione
                            connected = False
                            for _ in range(10):
                                if wlan_sta.isconnected():
                                    connected = True
                                    break
                                await asyncio.sleep(1)
                                
                            if connected:
                                # Connessione riuscita!
                                log_event(f"Riconnessione alla rete WiFi '{ssid}' riuscita", "INFO")
                                print(f"Riconnessione alla rete WiFi '{ssid}' riuscita")
                                reconnection_tries = 0
                                ap_failover_activated = False
                                
                                # Disattiva l'AP se era stato attivato come fallback
                                if wlan_ap.active():
                                    wlan_ap.active(False)
                                    log_event("Access Point di fallback disattivato", "INFO")
                                    print("Access Point di fallback disattivato")
                                    
                                # Riconfigura mDNS dopo la riconnessione
                                if not mdns_configured:
                                    if setup_mdns():
                                        mdns_configured = True
                                    else:
                                        # Riprova più tardi
                                        mdns_configured = False
                            else:
                                # Connessione fallita, attiva l'AP come fallback se non è già attivo
                                if not ap_failover_activated:
                                    log_event(f"Connessione a '{ssid}' fallita, attivazione AP come fallback", "WARNING")
                                    print(f"Connessione a '{ssid}' fallita, attivazione AP come fallback")
                                    
                                    # Attiva l'AP
                                    if not wlan_ap.active():
                                        ap_ssid = settings.get('ap', {}).get('ssid', AP_SSID_DEFAULT)
                                        ap_password = settings.get('ap', {}).get('password', AP_PASSWORD_DEFAULT)
                                        start_access_point(ap_ssid, ap_password)
                                    
                                    ap_failover_activated = True
                                else:
                                    log_event(f"Tentativo di riconnessione a '{ssid}' fallito, continuerò a riprovare", "WARNING")
                                    print(f"Tentativo di riconnessione a '{ssid}' fallito, continuerò a riprovare")
                        else:
                            log_event("SSID o password non validi. Impossibile riconnettersi", "ERROR")
                            print("SSID o password non validi. Impossibile riconnettersi")
                            
                            # Attiva AP come unica opzione
                            if not wlan_ap.active():
                                ap_ssid = settings.get('ap', {}).get('ssid', AP_SSID_DEFAULT)
                                ap_password = settings.get('ap', {}).get('password', AP_PASSWORD_DEFAULT)
                                start_access_point(ap_ssid, ap_password)
                                ap_failover_activated = True
                    else:
                        # Non è ancora il momento di riprovare, aspetta
                        await asyncio.sleep(1)
                else:
                    # Client connesso, tutto OK
                    if reconnection_tries > 0:
                        log_event("Connessione WiFi client stabile", "INFO")
                        print("Connessione WiFi client stabile")
                        reconnection_tries = 0
                    
                    # Disattiva AP se attivo (quando il client funziona, l'AP non serve)
                    if wlan_ap.active() and ap_failover_activated:
                        wlan_ap.active(False)
                        log_event("Access Point di fallback disattivato", "INFO")
                        print("Access Point di fallback disattivato")
                        ap_failover_activated = False
                    
                    # Assicurati che mDNS sia configurato
                    if not mdns_configured:
                        if setup_mdns():
                            mdns_configured = True
                        else:
                            # Riprova più tardi
                            mdns_configured = False
                    
                    # Aspetta un po' prima del prossimo controllo
                    await asyncio.sleep(30)
            else:
                # La modalità client è disabilitata
                if wlan_sta.active():
                    log_event("Disattivazione della modalità client come da configurazione", "INFO")
                    print("Disattivazione della modalità client come da configurazione")
                    wlan_sta.active(False)
                    reconnection_tries = 0
                    ap_failover_activated = False
                    
                # Assicurati che l'AP sia attivo
                if not wlan_ap.active():
                    log_event("AP non attivo, riattivazione come da configurazione", "WARNING")
                    ap_ssid = settings.get('ap', {}).get('ssid', AP_SSID_DEFAULT)
                    ap_password = settings.get('ap', {}).get('password', AP_PASSWORD_DEFAULT)
                    start_access_point(ap_ssid, ap_password)
                
                # Assicurati che mDNS sia configurato
                if not mdns_configured:
                    if setup_mdns():
                        mdns_configured = True
                    else:
                        # Riprova più tardi
                        mdns_configured = False
                
                # Aspetta prima del prossimo controllo
                await asyncio.sleep(30)
        
        except Exception as e:
            log_event(f"Errore durante la gestione della connessione WiFi: {e}", "ERROR")
            print(f"Errore durante la gestione della connessione WiFi: {e}")
            await asyncio.sleep(5)  # Breve ritardo prima di riprovare in caso di errore