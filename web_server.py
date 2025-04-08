"""
Modulo per la gestione del server web.
Fornisce le API REST e serve i file statici.
"""
from microdot import Request, Microdot, Response, send_file
import uasyncio as asyncio
from log_manager import log_event, get_logs, clear_logs

from settings_manager import (
    load_user_settings,
    save_user_settings,
    reset_user_settings,
    reset_factory_data,
    ensure_directory_exists
)
from program_manager import (
    load_programs,
    save_programs,
    stop_program,
    update_program,
    delete_program,
    execute_program,
    check_program_conflicts
)
from program_state import program_running, current_program_id, load_program_state
from wifi_manager import (
    start_access_point,
    clear_wifi_scan_file,
    save_wifi_scan_results,
    connect_to_wifi,
    reset_wifi_module
)
from zone_manager import start_zone, stop_zone, stop_all_zones, get_zones_status

import network
import ujson
import uos
import time
import gc
import machine

# Configurazione
HTML_BASE_PATH = '/web'
DATA_BASE_PATH = '/data'
WIFI_SCAN_FILE = '/data/wifi_scan.json'

app = Microdot()

# Migliore gestione delle richieste
Request.max_content_length = 32 * 1024  # 32KB per le richieste
Request.max_body_length = 16 * 1024     # 16KB per il corpo
Request.max_readline = 1024             # 1KB per riga di richiesta

def json_response(data, status_code=200):
    """
    Helper per creare risposte JSON standardizzate.
    
    Args:
        data: Dati da convertire in JSON
        status_code: Codice di stato HTTP
        
    Returns:
        Response: Oggetto risposta Microdot
    """
    return Response(
        body=ujson.dumps(data),
        status_code=status_code,
        headers={'Content-Type': 'application/json'}
    )

# Funzione per verificare se un file esiste
def file_exists(path):
    """
    Verifica se un file esiste.
    
    Args:
        path: Percorso del file
        
    Returns:
        boolean: True se il file esiste, False altrimenti
    """
    try:
        uos.stat(path)
        return True
    except OSError:
        return False

def with_gc(route_handler):
    """
    Decorator per forzare garbage collection dopo le chiamate alle API.
    
    Args:
        route_handler: Funzione da decorare
        
    Returns:
        function: Funzione decorata
    """
    async def async_wrapper(*args, **kwargs):
        try:
            result = route_handler(*args, **kwargs)
            if hasattr(result, 'send') and hasattr(result, 'throw'):
                result = await result
            gc.collect()
            return result
        except Exception as e:
            # Ottieni il nome della funzione in modo sicuro
            func_name = getattr(route_handler, '__name__', 'unknown')
            log_event(f"Errore in API '{func_name}': {e}", "ERROR")
            gc.collect()
            return json_response({'error': str(e)}, 200)  # Usa 200 per evitare errori client
    
    # Copia alcuni metadati in modo sicuro
    try:
        async_wrapper.__name__ = route_handler.__name__
    except Exception:
        pass
    
    return async_wrapper

# -------- API endpoints --------

@app.route('/data/system_log.json', methods=['GET'])
@with_gc
def get_system_logs(request):
    """API per ottenere i log di sistema."""
    try:
        logs = get_logs()
        return json_response(logs)
    except Exception as e:
        log_event(f"Errore durante la lettura dei log: {e}", "ERROR")
        return json_response({'error': str(e)}, 500)

@app.route('/clear_logs', methods=['POST'])
@with_gc
def clear_system_logs(request):
    """API per cancellare i log di sistema."""
    try:
        success = clear_logs()
        if success:
            log_event("Log di sistema cancellati", "INFO")
            return json_response({'success': True})
        else:
            return json_response({'success': False, 'error': 'Errore durante la cancellazione dei log'}, 500)
    except Exception as e:
        log_event(f"Errore durante la cancellazione dei log: {e}", "ERROR")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/data/wifi_scan.json', methods=['GET'])
@with_gc
def get_wifi_scan_results(request):
    """API per ottenere i risultati della scansione WiFi."""
    try:
        if file_exists(WIFI_SCAN_FILE):
            return send_file(WIFI_SCAN_FILE, content_type='application/json')
        else:
            return Response('File not found', status_code=404)
    except Exception as e:
        log_event(f"Errore durante la lettura del file di scansione WiFi: {e}", "ERROR")
        return Response('Internal Server Error', status_code=500)

@app.route('/scan_wifi', methods=['GET'])
@with_gc
def scan_wifi(request):
    """API per avviare una scansione WiFi."""
    try:
        log_event("Avvio della scansione Wi-Fi", "INFO")
        print("Avvio della scansione Wi-Fi")
        clear_wifi_scan_file()  # Cancella eventuali vecchi dati della scansione
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        networks = wlan.scan()
        network_list = []

        for net in networks:
            ssid = net[0].decode('utf-8')
            rssi = net[3]
            signal_quality = "Buono" if rssi > -60 else "Sufficiente" if rssi > -80 else "Scarso"
            network_list.append({"ssid": ssid, "signal": signal_quality})

        # Elimina duplicati basati su SSID
        unique_networks = []
        seen_ssids = set()
        for net in network_list:
            if net["ssid"] not in seen_ssids:
                seen_ssids.add(net["ssid"])
                unique_networks.append(net)

        # Salva i risultati nel file JSON
        save_wifi_scan_results(unique_networks)
        log_event(f"Scansione Wi-Fi completata: trovate {len(unique_networks)} reti", "INFO")

        return json_response(unique_networks)
    except Exception as e:
        log_event(f"Errore durante la scansione delle reti WiFi: {e}", "ERROR")
        print(f"Errore durante la scansione delle reti WiFi: {e}")
        return json_response({'error': 'Errore durante la scansione delle reti WiFi'}, 500)

@app.route('/clear_wifi_scan_file', methods=['POST'])
@with_gc
def clear_wifi_scan(request):
    """API per cancellare il file di scansione WiFi."""
    try:
        clear_wifi_scan_file()
        return json_response({'success': True})
    except Exception as e:
        log_event(f"Errore durante la cancellazione del file di scansione Wi-Fi: {e}", "ERROR")
        return json_response({'error': str(e)}, 500)

@app.route('/get_zones_status', methods=['GET'])
@with_gc
async def get_zones_status_endpoint(request):
    """API per ottenere lo stato delle zone."""
    try:
        # Breve pausa per prevenire polling troppo frequenti
        await asyncio.sleep(0.1)
        
        zones_status = get_zones_status()
        return json_response(zones_status)
    except Exception as e:
        log_event(f"Errore nel recupero dello stato delle zone: {e}", "ERROR")
        print(f"Errore nel recupero dello stato delle zone: {e}")
        # Restituisci una risposta fallback sicura
        return json_response([], 200)  # Restituiamo un array vuoto con status 200 invece di 500

@app.route('/get_connection_status', methods=['GET'])
@with_gc
def get_connection_status(request):
    """API per ottenere lo stato della connessione WiFi."""
    try:
        wlan_sta = network.WLAN(network.STA_IF)
        wlan_ap = network.WLAN(network.AP_IF)
        response_data = {}

        if wlan_sta.isconnected():
            ip = wlan_sta.ifconfig()[0]
            response_data['mode'] = 'client'
            response_data['ip'] = ip
            response_data['ssid'] = wlan_sta.config('essid')
        elif wlan_ap.active():
            ip = wlan_ap.ifconfig()[0]
            response_data['mode'] = 'AP'
            response_data['ip'] = ip
            response_data['ssid'] = wlan_ap.config('essid')
        else:
            response_data['mode'] = 'none'
            response_data['ip'] = 'N/A'
            response_data['ssid'] = 'N/A'

        return json_response(response_data)
    except Exception as e:
        log_event(f"Errore durante l'ottenimento dello stato della connessione: {e}", "ERROR")
        print(f"Errore durante l'ottenimento dello stato della connessione: {e}")
        return json_response({'error': str(e)}, 500)

@app.route('/activate_ap', methods=['POST'])
@with_gc
def activate_ap(request):
    """API per attivare l'access point."""
    try:
        start_access_point()  # Attiva l'AP con le impostazioni salvate
        log_event("Access Point attivato", "INFO")
        return json_response({'success': True})
    except Exception as e:
        log_event(f"Errore durante l'attivazione dell'Access Point: {e}", "ERROR")
        print(f"Error starting AP: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/data/user_settings.json', methods=['GET'])
@with_gc
def get_user_settings(request):
    """API per ottenere le impostazioni utente."""
    try:
        settings = load_user_settings()
        # Assicurati che il pin del relè di sicurezza sia sempre presente nella risposta
        if 'safety_relay' not in settings:
            settings['safety_relay'] = {'pin': 13}  # Valore di default
        elif 'pin' not in settings['safety_relay']:
            settings['safety_relay']['pin'] = 13  # Valore di default
            
        return json_response(settings)
    except Exception as e:
        log_event(f"Errore durante il caricamento di user_settings.json: {e}", "ERROR")
        print(f"Errore durante il caricamento di user_settings.json: {e}")
        return Response('Errore interno del server', status_code=500)

@app.route('/data/program.json', methods=['GET'])
@with_gc
def get_programs(request):
    """API per ottenere i programmi."""
    try:
        programs = load_programs()
        return json_response(programs)
    except Exception as e:
        log_event(f"Errore durante il caricamento di program.json: {e}", "ERROR")
        print(f"Errore durante il caricamento di program.json: {e}")
        return Response('Errore interno del server', status_code=500)

@app.route('/toggle_automatic_programs', methods=['POST'])
@with_gc
def toggle_automatic_programs(request):
    """API per abilitare/disabilitare i programmi automatici."""
    try:
        data = request.json
        if data is None:
            data = ujson.loads(request.body.decode('utf-8'))
            
        enable = data.get('enable', False)
        
        # Salva l'impostazione in un file
        settings = load_user_settings()
        settings['automatic_programs_enabled'] = enable
        save_user_settings(settings)
        
        log_event(f"Programmi automatici {'abilitati' if enable else 'disabilitati'}", "INFO")
        return json_response({'success': True})
    except Exception as e:
        log_event(f"Errore durante la modifica dell'impostazione dei programmi automatici: {e}", "ERROR")
        print(f"Errore durante la modifica dell'impostazione dei programmi automatici: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/get_zones', methods=['GET'])
@with_gc
def get_zones(request):
    """API per ottenere la lista delle zone."""
    try:
        settings = load_user_settings()
        zones = settings.get('zones', [])
        return json_response(zones)
    except Exception as e:
        log_event(f"Errore durante il caricamento delle zone: {e}", "ERROR")
        print(f"Errore durante il caricamento delle zone: {e}")
        return json_response({'error': 'Errore nel caricamento delle zone'}, 500)

@app.route('/start_zone', methods=['POST'])
@with_gc
def handle_start_zone(request):
    """API per avviare una zona."""
    try:
        data = request.json
        if data is None:
            data = ujson.loads(request.body.decode('utf-8'))

        zone_id = data.get('zone_id')
        duration = data.get('duration')

        if zone_id is None or duration is None:
            log_event("Errore: parametri mancanti per l'avvio della zona", "ERROR")
            return json_response({'error': 'Parametri mancanti', 'success': False}, 400)

        zone_id = int(zone_id)
        duration = int(duration)

        # Verifica se il valore di durata è valido
        settings = load_user_settings()
        max_duration = settings.get('max_zone_duration', 180)  # Default 3 ore
        if duration <= 0 or duration > max_duration:
            log_event(f"Errore: durata non valida per l'avvio della zona {zone_id}: {duration}", "ERROR")
            return json_response({'error': f'Durata non valida. Deve essere tra 1 e {max_duration} minuti', 'success': False}, 400)

        # Verifica se un programma è in esecuzione
        load_program_state()
        if program_running:
            log_event(f"Impossibile avviare la zona {zone_id}: un programma è già in esecuzione", "WARNING")
            return json_response({'error': 'Impossibile avviare la zona: un programma è già in esecuzione', 'success': False}, 400)

        log_event(f"Avvio della zona {zone_id} per {duration} minuti", "INFO")
        print(f"Avvio della zona {zone_id} per {duration} minuti")
        
        result = start_zone(zone_id, duration)
        if result:
            return json_response({"status": "Zona avviata", "success": True})
        else:
            return json_response({'error': "Errore durante l'avvio della zona", "success": False}, 500)
    except Exception as e:
        log_event(f"Errore durante l'avvio della zona: {e}", "ERROR")
        print(f"Errore durante l'avvio della zona: {e}")
        return json_response({'error': "Errore durante l'avvio della zona", "success": False}, 500)

@app.route('/stop_zone', methods=['POST'])
@with_gc
def handle_stop_zone(request):
    """API per fermare una zona."""
    try:
        data = request.json
        if data is None:
            data = ujson.loads(request.body.decode('utf-8'))

        zone_id = data.get('zone_id')

        if zone_id is None:
            log_event("Errore: parametro zone_id mancante", "ERROR")
            return json_response({'error': 'Parametro zone_id mancante', 'success': False}, 400)

        zone_id = int(zone_id)

        log_event(f"Arresto della zona {zone_id}", "INFO")
        print(f"Arresto della zona {zone_id}")
        
        result = stop_zone(zone_id)
        if result:
            return json_response({"status": "Zona arrestata", "success": True})
        else:
            return json_response({'error': "Errore durante l'arresto della zona", "success": False}, 500)
    except Exception as e:
        log_event(f"Errore durante l'arresto della zona: {e}", "ERROR")
        print(f"Errore durante l'arresto della zona: {e}")
        return json_response({'error': "Errore durante l'arresto della zona", "success": False}, 500)

@app.route('/stop_program', methods=['POST'])
@with_gc
def stop_program_route(request):
    """API per fermare il programma corrente."""
    try:
        log_event("Richiesta di interruzione del programma ricevuta", "INFO")
        print("Richiesta di interruzione ricevuta.")
        success = stop_program()
        return json_response({'success': success, 'message': 'Programma interrotto'})
    except Exception as e:
        log_event(f"Errore nell'arresto del programma: {e}", "ERROR")
        print(f"Errore nell'arresto del programma: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/save_program', methods=['POST'])
@with_gc
def save_program_route(request):
    """API per salvare un nuovo programma."""
    try:
        program_data = request.json
        if program_data is None:
            program_data = ujson.loads(request.body.decode('utf-8'))

        # Validazione della lunghezza del nome del programma
        if len(program_data.get('name', '')) > 16:
            log_event("Errore: nome programma troppo lungo", "ERROR")
            return json_response({'success': False, 'error': 'Il nome del programma non può superare 16 caratteri'}, 400)

        # Validazione mesi e zone
        if not program_data.get('months'):
            log_event("Errore: nessun mese selezionato", "ERROR")
            return json_response({'success': False, 'error': 'Seleziona almeno un mese per il programma'}, 400)
            
        if not program_data.get('steps'):
            log_event("Errore: nessuna zona selezionata", "ERROR")
            return json_response({'success': False, 'error': 'Seleziona almeno una zona per il programma'}, 400)

        # Carica i programmi esistenti
        programs = load_programs()

        # Verifica se esiste un programma con lo stesso nome
        for existing_program in programs.values():
            if existing_program['name'] == program_data['name']:
                log_event(f"Errore: programma con nome '{program_data['name']}' già esistente", "ERROR")
                return json_response({'success': False, 'error': 'Esiste già un programma con questo nome'}, 400)

        # Verifica conflitti con altri programmi
        has_conflict, conflict_message = check_program_conflicts(program_data, programs)
        if has_conflict:
            log_event(f"Conflitto programma: {conflict_message}", "WARNING")
            return json_response({'success': False, 'error': conflict_message}, 400)

        # Genera un nuovo ID per il programma
        new_id = '1'
        if programs:
            new_id = str(max([int(pid) for pid in programs.keys()]) + 1)
        program_data['id'] = new_id  # Assicurati che l'ID sia una stringa

        # Aggiungi il nuovo programma al dizionario
        programs[new_id] = program_data

        # Salva i programmi aggiornati
        if save_programs(programs):
            log_event(f"Nuovo programma '{program_data['name']}' creato con ID {new_id}", "INFO")
            return json_response({'success': True, 'message': 'Programma salvato con successo', 'program_id': new_id})
        else:
            log_event(f"Errore durante il salvataggio del programma '{program_data['name']}'", "ERROR")
            return json_response({'success': False, 'error': 'Errore durante il salvataggio del programma'}, 500)
    except Exception as e:
        log_event(f"Errore durante il salvataggio del programma: {e}", "ERROR")
        print(f"Errore durante il salvataggio del programma: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/update_program', methods=['PUT'])
@with_gc
def update_program_route(request):
    """API per aggiornare un programma esistente."""
    try:
        updated_program_data = request.json
        if updated_program_data is None:
            updated_program_data = ujson.loads(request.body.decode('utf-8'))
            
        program_id = updated_program_data.get('id')

        if program_id is None:
            log_event("Errore: ID del programma mancante", "ERROR")
            return json_response({'success': False, 'error': 'ID del programma mancante'}, 400)

        # Validazione della lunghezza del nome del programma
        if len(updated_program_data.get('name', '')) > 16:
            log_event("Errore: nome programma troppo lungo", "ERROR")
            return json_response({'success': False, 'error': 'Il nome del programma non può superare 16 caratteri'}, 400)

        # Aggiorna il programma esistente
        success, error_msg = update_program(program_id, updated_program_data)

        if success:
            log_event(f"Programma {program_id} aggiornato con successo", "INFO")
            return json_response({'success': True, 'message': 'Programma aggiornato con successo'})
        else:
            log_event(f"Errore nell'aggiornamento del programma {program_id}: {error_msg}", "ERROR")
            return json_response({'success': False, 'error': error_msg}, 400)
    except Exception as e:
        log_event(f"Errore durante l'aggiornamento del programma: {e}", "ERROR")
        print(f"Errore durante l'aggiornamento del programma: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/toggle_program_automatic', methods=['POST'])
@with_gc
def toggle_program_automatic(request):
    """API per abilitare/disabilitare l'automazione di un singolo programma."""
    try:
        data = request.json
        if data is None:
            data = ujson.loads(request.body.decode('utf-8'))
            
        program_id = data.get('program_id')
        enable = data.get('enable', True)
        
        if not program_id:
            return json_response({'success': False, 'error': 'ID programma mancante'}, 400)
            
        # Carica i programmi
        programs = load_programs()
        
        if program_id not in programs:
            return json_response({'success': False, 'error': 'Programma non trovato'}, 404)
            
        # Aggiorna lo stato automatico del programma
        programs[program_id]['automatic_enabled'] = enable
        
        # Salva i programmi aggiornati
        if save_programs(programs):
            log_event(f"Automazione del programma {program_id} {'abilitata' if enable else 'disabilitata'}", "INFO")
            return json_response({'success': True})
        else:
            return json_response({'success': False, 'error': 'Errore durante il salvataggio'}, 500)
    except Exception as e:
        log_event(f"Errore durante la modifica dello stato automatico del programma: {e}", "ERROR")
        print(f"Errore durante la modifica dello stato automatico del programma: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)
        
@app.route('/delete_program', methods=['POST'])
@with_gc
def delete_program_route(request):
    """API per eliminare un programma."""
    try:
        program_data = request.json
        if program_data is None:
            program_data = ujson.loads(request.body.decode('utf-8'))
            
        program_id = program_data.get('id')

        if program_id is None:
            log_event("Errore: ID del programma mancante", "ERROR")
            return json_response({'success': False, 'error': 'ID del programma mancante'}, 400)

        # Elimina il programma
        success = delete_program(program_id)

        if success:
            log_event(f"Programma {program_id} eliminato con successo", "INFO")
            return json_response({'success': True, 'message': f'Programma {program_id} eliminato'})
        else:
            log_event(f"Errore: programma con ID {program_id} non trovato", "ERROR")
            return json_response({'success': False, 'error': 'Programma non trovato'}, 404)
    except Exception as e:
        log_event(f"Errore nell'eliminazione del programma: {e}", "ERROR")
        print(f"Errore nell'eliminazione del programma: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/restart_system', methods=['POST'])
@with_gc
def restart_system_route(request):
    """API per riavviare il sistema."""
    try:
        log_event("Riavvio del sistema richiesto", "INFO")
        
        # Disattiva tutte le zone prima del riavvio
        stop_all_zones()
        
        # Ritardo per consentire l'invio della risposta
        asyncio.create_task(_delayed_reset(2))
        return json_response({'success': True, 'message': 'Sistema in riavvio'})
    except Exception as e:
        log_event(f"Errore durante il riavvio del sistema: {e}", "ERROR")
        print(f"Errore durante il riavvio del sistema: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

async def _delayed_reset(delay_seconds):
    """Esegue un reset del sistema dopo un ritardo specificato."""
    await asyncio.sleep(delay_seconds)
    machine.reset()

@app.route('/reset_settings', methods=['POST'])
@with_gc
def reset_settings_route(request):
    """API per ripristinare le impostazioni predefinite."""
    try:
        success = reset_user_settings()
        if success:
            log_event("Impostazioni resettate con successo", "INFO")
            return json_response({'success': True, 'message': 'Impostazioni resettate con successo'})
        else:
            log_event("Errore durante il reset delle impostazioni", "ERROR")
            return json_response({'success': False, 'error': 'Errore durante il reset delle impostazioni'}, 500)
    except Exception as e:
        log_event(f"Errore durante il reset delle impostazioni: {e}", "ERROR")
        print(f"Errore durante il reset delle impostazioni: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/reset_factory_data', methods=['POST'])
@with_gc
def reset_factory_data_route(request):
    """API per ripristinare le impostazioni e i dati di fabbrica."""
    try:
        success = reset_factory_data()
        if success:
            log_event("Dati di fabbrica resettati con successo", "INFO")
            return json_response({'success': True, 'message': 'Dati di fabbrica resettati con successo'})
        else:
            log_event("Errore durante il reset dei dati di fabbrica", "ERROR")
            return json_response({'success': False, 'error': 'Errore durante il reset dei dati di fabbrica'}, 500)
    except Exception as e:
        log_event(f"Errore durante il reset dei dati di fabbrica: {e}", "ERROR")
        print(f"Errore durante il reset dei dati di fabbrica: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/get_program_state', methods=['GET'])
@with_gc
async def get_program_state(request):
    """API per ottenere lo stato del programma corrente."""
    try:
        # Breve pausa per prevenire polling troppo frequenti
        await asyncio.sleep(0.1)
        
        # Ricarichiamo lo stato per essere sicuri di avere dati aggiornati
        try:
            load_program_state()
        except Exception as e:
            log_event(f"Errore durante il caricamento dello stato del programma: {e}", "ERROR")
            return json_response({'program_running': False, 'current_program_id': None})
            
        state = {
            'program_running': program_running,
            'current_program_id': current_program_id
        }
        return json_response(state)
    except Exception as e:
        log_event(f"Errore durante la risposta dello stato del programma: {e}", "ERROR")
        print(f"Errore durante la risposta dello stato del programma: {e}")
        return json_response({'program_running': False, 'current_program_id': None})

@app.route('/start_program', methods=['POST'])
@with_gc
async def start_program_route(request):
    """API per avviare manualmente un programma."""
    try:
        data = request.json
        if data is None:
            data = ujson.loads(request.body.decode('utf-8'))
            
        program_id = str(data.get('program_id', ''))

        if not program_id:
            log_event("Errore: ID del programma mancante", "ERROR")
            return json_response({'success': False, 'error': 'ID del programma mancante'}, 400)

        programs = load_programs()
        program = programs.get(program_id)

        if program is None:
            log_event(f"Errore: programma con ID {program_id} non trovato", "ERROR")
            return json_response({'success': False, 'error': 'Programma non trovato'}, 404)

        # Controlla se un altro programma è già in esecuzione
        load_program_state()
        if program_running:
            log_event("Impossibile avviare il programma: un altro programma è già in esecuzione", "WARNING")
            return json_response({'success': False, 'error': 'Un altro programma è già in esecuzione'}, 400)

        # Avvia il programma manualmente
        success = await execute_program(program, manual=True)
        
        if success:
            log_event(f"Programma {program.get('name', '')} avviato manualmente", "INFO")
            return json_response({'success': True, 'message': 'Programma avviato manualmente'})
        else:
            return json_response({'success': False, 'error': 'Errore nell\'avvio del programma'}, 500)
    except Exception as e:
        log_event(f"Errore nell'avvio del programma: {e}", "ERROR")
        print(f"Errore nell'avvio del programma: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/connect_wifi', methods=['POST'])
@with_gc
def connect_wifi_route(request):
    """API per connettersi a una rete WiFi."""
    try:
        # Ottieni i dati della richiesta
        data = request.json
        if data is None:
            data = ujson.loads(request.body.decode('utf-8'))

        # Estrai SSID e password
        ssid = data.get('ssid')
        password = data.get('password')

        if not ssid or not password:
            log_event("Errore: SSID o password mancanti", "ERROR")
            return json_response({'success': False, 'error': 'SSID o password mancanti'}, 400)

        log_event(f"Tentativo di connessione alla rete WiFi: {ssid}", "INFO")
        
        # Attiva il WiFi in modalità client e connessione alla rete
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(ssid, password)

        # Attendere la connessione (timeout 15 secondi)
        timeout = 15
        for _ in range(timeout):
            if wlan.isconnected():
                break
            print("Tentativo di connessione...")
            time.sleep(1)

        # Se la connessione è riuscita, salvare le nuove impostazioni WiFi
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            log_event(f"Connesso alla rete WiFi con IP: {ip}", "INFO")
            print(f"Connesso alla rete WiFi con IP: {ip}")

            # Carica le impostazioni esistenti
            existing_settings = load_user_settings()
            if not isinstance(existing_settings, dict):
                existing_settings = {}

            # Aggiorna solo le impostazioni WiFi e salva il file
            existing_settings['wifi'] = {'ssid': ssid, 'password': password}
            existing_settings['client_enabled'] = True

            # Salva le impostazioni aggiornate
            save_user_settings(existing_settings)

            # Restituisci una risposta di successo
            return json_response({'success': True, 'ip': ip, 'mode': 'client'})
        else:
            # Connessione fallita
            log_event("Connessione WiFi fallita", "ERROR")
            print("Connessione WiFi fallita")
            return json_response({'success': False, 'error': 'Connessione WiFi fallita'}, 500)

    except Exception as e:
        log_event(f"Errore durante la connessione alla rete WiFi: {e}", "ERROR")
        print(f"Errore durante la connessione alla rete WiFi: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/save_user_settings', methods=['POST'])
@with_gc
def save_user_settings_route(request):
    """API per salvare le impostazioni utente."""
    try:
        # Ricevi i dati delle impostazioni dal client e assicurati che siano validi
        settings_data = request.json
        if settings_data is None:
            settings_data = ujson.loads(request.body.decode('utf-8'))

        # Controlla che 'settings_data' sia un dizionario
        if not isinstance(settings_data, dict):
            log_event("Errore: dati impostazioni non validi", "ERROR")
            return json_response({'success': False, 'error': 'I dati delle impostazioni devono essere un oggetto JSON valido'}, 400)

        # Stampa di debug delle impostazioni ricevute
        print("Dati ricevuti per le impostazioni:", ujson.dumps(settings_data))

        # Carica le impostazioni esistenti dal file
        existing_settings = load_user_settings()
        if not isinstance(existing_settings, dict):
            existing_settings = {}

        # Aggiorna le impostazioni esistenti con le nuove impostazioni ricevute
        for key, value in settings_data.items():
            if isinstance(value, dict) and key in existing_settings and isinstance(existing_settings[key], dict):
                # Se il valore è un dizionario, aggiorna in modo ricorsivo
                existing_settings[key].update(value)
            else:
                # Se il valore non è un dizionario, sovrascrivi direttamente
                existing_settings[key] = value

        # Salva le impostazioni aggiornate
        success = save_user_settings(existing_settings)
        if not success:
            return json_response({'success': False, 'error': 'Errore nella scrittura del file'}, 500)

        # Verifica se client_enabled è stato impostato su False
        client_enabled = existing_settings.get('client_enabled', True)
        wlan_sta = network.WLAN(network.STA_IF)

        if not client_enabled:
            # Se il client Wi-Fi è attivo, disattivalo
            if wlan_sta.active() or wlan_sta.isconnected():
                wlan_sta.active(False)
                log_event("Modalità client disattivata poiché 'client_enabled' è False", "INFO")
                print("Modalità client disattivata poiché 'client_enabled' è False.")
        else:
            log_event("Modalità client attivata o già attiva", "INFO")
            print("Modalità client attivata o già attiva.")

        # Forza la garbage collection
        gc.collect()
        
        # Restituisce una risposta di successo
        return json_response({'success': True})

    except ValueError as e:
        log_event(f"Errore nella decodifica del JSON: {e}", "ERROR")
        print(f"Errore nella decodifica del JSON: {e}")
        return json_response({'success': False, 'error': 'JSON syntax error'})
    except Exception as e:
        log_event(f"Errore durante il salvataggio delle impostazioni: {e}", "ERROR")
        print(f"Errore durante il salvataggio delle impostazioni: {e}")
        return json_response({'success': False, 'error': str(e)})

@app.route('/disconnect_wifi', methods=['POST'])
@with_gc
def disconnect_wifi(request):
    """API per disconnettere il client WiFi."""
    try:
        wlan_sta = network.WLAN(network.STA_IF)
        if wlan_sta.isconnected():
            wlan_sta.disconnect()
            wlan_sta.active(False)
            log_event("WiFi client disconnesso", "INFO")
            print("WiFi client disconnesso.")
        return json_response({'success': True})
    except Exception as e:
        log_event(f"Errore durante la disconnessione del WiFi client: {e}", "ERROR")
        print(f"Errore durante la disconnessione del WiFi client: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route('/', methods=['GET'])
@with_gc
def index(request):
    """Route per servire la pagina principale."""
    try:
        return send_file('/web/main.html')
    except Exception as e:
        log_event(f"Errore durante il caricamento di main.html: {e}", "ERROR")
        print(f"Errore durante il caricamento di main.html: {e}")
        return Response('Errore interno del server', status_code=500)

@app.route('/<path:path>', methods=['GET'])
@with_gc
def static_files(request, path):
    """Route per servire i file statici."""
    try:
        # Evita di intercettare percorsi che iniziano con 'data/'
        if path.startswith('data/'):
            return Response('Not Found', status_code=404)

        file_path = f'/web/{path}'
        if file_exists(file_path):
            # Determina il tipo di contenuto in base all'estensione del file
            if file_path.endswith('.html'):
                content_type = 'text/html'
            elif file_path.endswith('.css'):
                content_type = 'text/css'
            elif file_path.endswith('.js'):
                content_type = 'application/javascript'
            elif file_path.endswith('.json'):
                content_type = 'application/json'
            elif file_path.endswith('.png'):
                content_type = 'image/png'
            elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif file_path.endswith('.ico'):
                content_type = 'image/x-icon'
            elif file_path.endswith('.webp'):
                content_type = 'image/webp'
            else:
                content_type = 'text/plain'
            return send_file(file_path, content_type=content_type)
        else:
            log_event(f"File non trovato: {path}", "WARNING")
            return Response('File non trovato', status_code=404)
    except Exception as e:
        log_event(f"Errore durante il caricamento del file {path}: {e}", "ERROR")
        print(f"Errore durante il caricamento del file {path}: {e}")
        return Response('Errore interno del server', status_code=500)

async def start_web_server():
    """
    Avvia il server web.
    """
    try:
        print("Avvio del server web.")
        log_event("Avvio del server web", "INFO")
        
        # Crea la directory data se non esiste
        ensure_directory_exists('/data')
        
        # Libera memoria prima di avviare il server
        gc.collect()
        
        # Configurazioni per migliorare la stabilità
        Request.max_content_length = 32 * 1024  # Limitare la dimensione massima della richiesta
        Request.max_readline = 1024  # Ridurre la dimensione massima delle righe di richiesta
        
        # Avvia il server sulla porta 80
        await app.start_server(host='0.0.0.0', port=80)
    except Exception as e:
        log_event(f"Errore durante l'avvio del server web: {e}", "ERROR")
        print(f"Errore durante l'avvio del server web: {e}")