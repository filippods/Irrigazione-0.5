"""
Modulo di diagnostica per il sistema di irrigazione.
Monitora lo stato del sistema e dei servizi, risolvendo automaticamente i problemi rilevati.
"""
import uasyncio as asyncio
import machine
import gc
import network
import socket
import time
import urequests
from log_manager import log_event
from settings_manager import load_user_settings
from zone_manager import stop_all_zones, get_zones_status, stop_zone
from program_state import program_running, current_program_id, load_program_state
from wifi_manager import reset_wifi_module, initialize_network
from web_server import app

# Configurazione del modulo
CHECK_INTERVAL = 60  # Tempo in secondi tra i controlli
MEMORY_THRESHOLD = 20000  # Soglia di memoria libera (in bytes) prima di forzare gc
MAX_ZONE_ACTIVATION_TIME = 180  # Tempo massimo in minuti per cui una zona può rimanere attiva
WEB_SERVER_TIMEOUT = 5  # Timeout in secondi per il controllo del web server
MAX_SERVER_RESTARTS = 3  # Numero massimo di riavvii del server consecutivi
HEALTH_INDICATORS = {
    'web_server': True,
    'wifi_connection': True,
    'memory': True,
    'zones': True,
    'programs': True
}
CONSECUTIVE_FAILURES = {
    'web_server': 0,
    'wifi_connection': 0
}

# Metriche del sistema
system_metrics = {
    'uptime': 0,  # Tempo di attività in secondi
    'start_time': time.time(),
    'memory_free': 0,
    'memory_allocated': 0,
    'gc_runs': 0,
    'wifi_disconnects': 0,
    'server_restarts': 0,
    'zone_corrections': 0
}

async def check_web_server():
    """
    Verifica che il web server risponda correttamente.
    Se non risponde, tenta di riavviarlo.
    
    Returns:
        boolean: True se il server è attivo, False altrimenti
    """
    try:
        # Verifica se il server risponde a una richiesta locale
        addr_info = socket.getaddrinfo('localhost', 80)
        addr = addr_info[0][-1]
        
        s = socket.socket()
        s.settimeout(WEB_SERVER_TIMEOUT)
        
        try:
            s.connect(('127.0.0.1', 80))
            s.send(b'GET / HTTP/1.0\r\n\r\n')
            response = s.recv(100)
            s.close()
            
            if b'HTTP' in response:
                HEALTH_INDICATORS['web_server'] = True
                CONSECUTIVE_FAILURES['web_server'] = 0
                return True
        except Exception as e:
            log_event(f"Il web server non risponde: {e}", "WARNING")
            print(f"Il web server non risponde: {e}")
    except Exception as e:
        log_event(f"Errore nel controllo del web server: {e}", "ERROR")
        print(f"Errore nel controllo del web server: {e}")
    
    # Il server non risponde, incrementa il contatore di fallimenti
    CONSECUTIVE_FAILURES['web_server'] += 1
    HEALTH_INDICATORS['web_server'] = False
    
    # Tenta il riavvio del server se ci sono troppi fallimenti consecutivi
    if CONSECUTIVE_FAILURES['web_server'] >= 3:
        log_event(f"Tentativo di riavvio del web server dopo {CONSECUTIVE_FAILURES['web_server']} fallimenti", "WARNING")
        
        # Impostiamo un limite al numero di riavvii per evitare cicli infiniti
        if system_metrics['server_restarts'] < MAX_SERVER_RESTARTS:
            system_metrics['server_restarts'] += 1
            
            # Tenta di riavviare il server
            try:
                await restart_web_server()
                log_event("Web server riavviato con successo", "INFO")
                CONSECUTIVE_FAILURES['web_server'] = 0
                return True
            except Exception as e:
                log_event(f"Errore nel riavvio del web server: {e}", "ERROR")
                print(f"Errore nel riavvio del web server: {e}")
        else:
            log_event(f"Raggiunto il numero massimo di riavvii del server ({MAX_SERVER_RESTARTS})", "ERROR")
    
    return False

async def restart_web_server():
    """
    Riavvia il web server.
    """
    try:
        # Ferma il server corrente se possibile
        if hasattr(app, 'server') and app.server:
            try:
                app.server.close()
                await asyncio.sleep(1)
            except Exception as e:
                log_event(f"Errore nella chiusura del server: {e}", "WARNING")
        
        # Avvia un nuovo server
        asyncio.create_task(app.start_server(host='0.0.0.0', port=80))
        
        # Attendi un po' per permettere l'avvio del server
        await asyncio.sleep(2)
        log_event("Server web riavviato", "INFO")
    except Exception as e:
        log_event(f"Errore nel riavvio del server web: {e}", "ERROR")
        raise

async def check_wifi_connection():
    """
    Verifica lo stato della connessione WiFi e la riavvia se necessario.
    
    Returns:
        boolean: True se la connessione è OK, False altrimenti
    """
    try:
        settings = load_user_settings()
        client_enabled = settings.get('client_enabled', False)
        wlan_sta = network.WLAN(network.STA_IF)
        wlan_ap = network.WLAN(network.AP_IF)
        
        # Verifica la modalità corretta in base alle impostazioni
        if client_enabled:
            # Se il client è abilitato, dovrebbe essere connesso
            if not wlan_sta.isconnected():
                log_event("Connessione WiFi client persa, tentativo di ripristino", "WARNING")
                CONSECUTIVE_FAILURES['wifi_connection'] += 1
                HEALTH_INDICATORS['wifi_connection'] = False
                
                # Dopo 3 fallimenti, tenta un reset più drastico
                if CONSECUTIVE_FAILURES['wifi_connection'] >= 3:
                    log_event("Riavvio completo del modulo WiFi", "WARNING")
                    system_metrics['wifi_disconnects'] += 1
                    reset_wifi_module()
                    await asyncio.sleep(1)
                    initialize_network()
                    CONSECUTIVE_FAILURES['wifi_connection'] = 0
                
                return False
            else:
                HEALTH_INDICATORS['wifi_connection'] = True
                CONSECUTIVE_FAILURES['wifi_connection'] = 0
                return True
        else:
            # Se il client è disabilitato, l'AP dovrebbe essere attivo
            if not wlan_ap.active():
                log_event("Access Point non attivo, tentativo di ripristino", "WARNING")
                HEALTH_INDICATORS['wifi_connection'] = False
                
                # Riavvia l'access point
                from wifi_manager import start_access_point
                ap_ssid = settings.get('ap', {}).get('ssid', 'IrrigationSystem')
                ap_password = settings.get('ap', {}).get('password', '12345678')
                start_access_point(ap_ssid, ap_password)
                
                return False
            else:
                HEALTH_INDICATORS['wifi_connection'] = True
                return True
    
    except Exception as e:
        log_event(f"Errore nel controllo della connessione WiFi: {e}", "ERROR")
        print(f"Errore nel controllo della connessione WiFi: {e}")
        HEALTH_INDICATORS['wifi_connection'] = False
        return False

async def check_memory_usage():
    """
    Controlla l'utilizzo della memoria e forza la garbage collection se necessario.
    
    Returns:
        boolean: True se la memoria è OK, False se c'è poca memoria disponibile
    """
    try:
        # Raccogli i dati sulla memoria
        free_mem = gc.mem_free()
        allocated_mem = gc.mem_alloc()
        total_mem = free_mem + allocated_mem
        percent_free = (free_mem / total_mem) * 100
        
        # Aggiorna le metriche
        system_metrics['memory_free'] = free_mem
        system_metrics['memory_allocated'] = allocated_mem
        
        # Controlla se c'è poca memoria disponibile
        if free_mem < MEMORY_THRESHOLD or percent_free < 10:
            log_event(f"Memoria in esaurimento: {free_mem} bytes liberi ({percent_free:.1f}%), forzatura garbage collection", "WARNING")
            gc.collect()
            system_metrics['gc_runs'] += 1
            
            # Verifica di nuovo dopo la garbage collection
            new_free_mem = gc.mem_free()
            new_percent_free = (new_free_mem / total_mem) * 100
            
            log_event(f"Dopo garbage collection: {new_free_mem} bytes liberi ({new_percent_free:.1f}%)", "INFO")
            
            if new_free_mem < MEMORY_THRESHOLD:
                HEALTH_INDICATORS['memory'] = False
                return False
        
        HEALTH_INDICATORS['memory'] = True
        return True
    
    except Exception as e:
        log_event(f"Errore nel controllo della memoria: {e}", "ERROR")
        print(f"Errore nel controllo della memoria: {e}")
        HEALTH_INDICATORS['memory'] = False
        return False

async def check_zones_state():
    """
    Verifica che tutte le zone siano in uno stato coerente.
    Disattiva le zone che sono rimaste attive per troppo tempo.
    
    Returns:
        boolean: True se le zone sono OK, False altrimenti
    """
    try:
        zones_status = get_zones_status()
        current_time = time.time()
        
        # Se non ci sono zone attive, tutto è OK
        active_zones_found = False
        for zone in zones_status:
            if zone['active']:
                active_zones_found = True
                
                # Se la zona è attiva, controlla quanto tempo è rimasta attiva
                remaining_time = zone.get('remaining_time', 0)
                
                if remaining_time == 0:
                    # La zona dovrebbe già essere spenta, ma è ancora attiva
                    log_event(f"Zona {zone['id']} bloccata in stato attivo, disattivazione forzata", "WARNING")
                    stop_zone(zone['id'])
                    system_metrics['zone_corrections'] += 1
                elif remaining_time > MAX_ZONE_ACTIVATION_TIME * 60:
                    # La zona è attiva da troppo tempo
                    log_event(f"Zona {zone['id']} attiva da troppo tempo, disattivazione forzata", "WARNING")
                    stop_zone(zone['id'])
                    system_metrics['zone_corrections'] += 1
        
        # Se c'è un programma in esecuzione, verifica che le zone siano coerenti
        load_program_state()
        if program_running:
            if not active_zones_found:
                log_event("Incongruenza: programma in esecuzione ma nessuna zona attiva, ripristino", "WARNING")
                from program_manager import stop_program
                stop_program()
                system_metrics['zone_corrections'] += 1
                HEALTH_INDICATORS['zones'] = False
                return False
        
        HEALTH_INDICATORS['zones'] = True
        return True
    
    except Exception as e:
        log_event(f"Errore nel controllo dello stato delle zone: {e}", "ERROR")
        print(f"Errore nel controllo dello stato delle zone: {e}")
        HEALTH_INDICATORS['zones'] = False
        return False

async def check_programs_state():
    """
    Verifica che i programmi siano in uno stato coerente.
    
    Returns:
        boolean: True se i programmi sono OK, False altrimenti
    """
    try:
        from program_state import program_running, current_program_id
        from program_manager import load_programs
        
        # Se c'è un programma in esecuzione, verifica che esista
        if program_running and current_program_id:
            programs = load_programs()
            
            if current_program_id not in programs:
                log_event(f"Programma {current_program_id} in esecuzione non trovato, arresto forzato", "WARNING")
                from program_manager import stop_program
                stop_program()
                HEALTH_INDICATORS['programs'] = False
                return False
        
        HEALTH_INDICATORS['programs'] = True
        return True
    
    except Exception as e:
        log_event(f"Errore nel controllo dello stato dei programmi: {e}", "ERROR")
        print(f"Errore nel controllo dello stato dei programmi: {e}")
        HEALTH_INDICATORS['programs'] = False
        return False

async def check_system_health():
    """
    Controlla la salute complessiva del sistema.
    """
    try:
        # Aggiorna il tempo di attività
        system_metrics['uptime'] = time.time() - system_metrics['start_time']
        
        # Esegui tutti i controlli
        web_server_ok = await check_web_server()
        wifi_ok = await check_wifi_connection()
        memory_ok = await check_memory_usage()
        zones_ok = await check_zones_state()
        programs_ok = await check_programs_state()
        
        # Decidi se registrare un log sullo stato del sistema
        all_ok = web_server_ok and wifi_ok and memory_ok and zones_ok and programs_ok
        
        if all_ok:
            # Tutti i controlli sono OK, registra ogni 10 esecuzioni (circa ogni 10 minuti)
            if int(system_metrics['uptime']) % (CHECK_INTERVAL * 10) < CHECK_INTERVAL:
                free_mem = gc.mem_free()
                allocated_mem = gc.mem_alloc()
                total_mem = free_mem + allocated_mem
                percent_free = (free_mem / total_mem) * 100
                
                log_event(f"Sistema in salute. Uptime: {int(system_metrics['uptime']//3600)}h {int((system_metrics['uptime']%3600)//60)}m. "
                         f"Memoria: {free_mem} bytes liberi ({percent_free:.1f}%)", "INFO")
        else:
            # Qualche controllo è fallito, registra ogni esecuzione
            log_event(f"Problemi rilevati nel sistema. Stato: "
                     f"WebServer={HEALTH_INDICATORS['web_server']}, "
                     f"WiFi={HEALTH_INDICATORS['wifi_connection']}, "
                     f"Memoria={HEALTH_INDICATORS['memory']}, "
                     f"Zone={HEALTH_INDICATORS['zones']}, "
                     f"Programmi={HEALTH_INDICATORS['programs']}", "WARNING")
    
    except Exception as e:
        log_event(f"Errore nel controllo della salute del sistema: {e}", "ERROR")
        print(f"Errore nel controllo della salute del sistema: {e}")

async def diagnostic_loop():
    """
    Loop principale di diagnostica che viene eseguito periodicamente.
    """
    log_event("Sistema di diagnostica avviato", "INFO")
    print("Sistema di diagnostica avviato.")
    
    # Attendi un po' prima del primo controllo per permettere l'avvio completo del sistema
    await asyncio.sleep(30)
    
    while True:
        try:
            await check_system_health()
        except Exception as e:
            log_event(f"Errore grave nel loop di diagnostica: {e}", "ERROR")
            print(f"Errore grave nel loop di diagnostica: {e}")
        
        # Attendi fino al prossimo controllo
        await asyncio.sleep(CHECK_INTERVAL)

async def start_diagnostics():
    """
    Avvia il sistema di diagnostica.
    """
    # Crea e avvia il task di diagnostica
    diagnostic_task = asyncio.create_task(diagnostic_loop())
    log_event("Sistema di diagnostica inizializzato", "INFO")
    print("Sistema di diagnostica inizializzato.")
    return diagnostic_task