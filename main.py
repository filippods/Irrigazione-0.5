"""
File principale del sistema di irrigazione.
Inizializza il sistema e avvia i servizi necessari.
"""
from wifi_manager import initialize_network, reset_wifi_module, retry_client_connection
from web_server import start_web_server
from zone_manager import initialize_pins, stop_all_zones
from program_manager import check_programs, reset_program_state
from log_manager import log_event
from system_monitor import start_diagnostics  # Importa il nuovo modulo di diagnostica
import uasyncio as asyncio
import gc
import machine
import time

# Tentativo di importare il watchdog hardware
try:
    from machine import WDT
    HAS_WATCHDOG = True
except (ImportError, AttributeError):
    HAS_WATCHDOG = False

# Intervallo di controllo dei programmi in secondi
PROGRAM_CHECK_INTERVAL = 30

async def program_check_loop():
    """
    Task asincrono che controlla periodicamente i programmi di irrigazione.
    """
    while True:
        try:
            # Controlla se ci sono programmi da avviare
            await check_programs()
            await asyncio.sleep(PROGRAM_CHECK_INTERVAL)
        except Exception as e:
            log_event(f"Errore durante il controllo dei programmi: {e}", "ERROR")
            await asyncio.sleep(PROGRAM_CHECK_INTERVAL)  # Continua comunque

async def watchdog_loop():
    """
    Task asincrono che monitora lo stato del sistema e registra
    periodicamente le informazioni di memoria disponibile.
    """
    while True:
        try:
            free_mem = gc.mem_free()
            allocated_mem = gc.mem_alloc()
            total_mem = free_mem + allocated_mem
            percent_free = (free_mem / total_mem) * 100
            
            log_event(f"Memoria: {free_mem} bytes liberi ({percent_free:.1f}%)", "INFO")
            
            # Forza la garbage collection
            gc.collect()
            
            # Se memoria bassa, forza una garbage collection aggressiva
            if percent_free < 20:
                log_event("Memoria bassa rilevata, esecuzione pulizia aggressiva", "WARNING")
                # Esegui più volte la garbage collection
                for _ in range(3):
                    gc.collect()
                # Riavvia il server web se la memoria è estremamente bassa
                if percent_free < 10:
                    log_event("Memoria critica, riavvio del server web", "WARNING")
                    try:
                        from web_server import app
                        if hasattr(app, 'server') and app.server:
                            app.server.close()
                            await asyncio.sleep(1)
                            asyncio.create_task(app.start_server(host='0.0.0.0', port=80))
                    except Exception as e:
                        log_event(f"Errore nel riavvio del server web: {e}", "ERROR")
            
            # Controllo ogni 10 minuti invece di ogni ora
            await asyncio.sleep(600)
        except Exception as e:
            log_event(f"Errore nel watchdog: {e}", "ERROR")
            await asyncio.sleep(60)  # Ridotto a 1 minuto in caso di errore

async def main():
    """
    Funzione principale che inizializza il sistema e avvia i task asincroni.
    """
    try:
        # Inizializza il watchdog hardware se disponibile
        wdt = None
        if HAS_WATCHDOG:
            try:
                wdt = WDT(timeout=60000)  # timeout di 60 secondi
                log_event("Watchdog hardware inizializzato", "INFO")
            except Exception as e:
                log_event(f"Hardware watchdog non inizializzato: {e}", "WARNING")
                print(f"Hardware watchdog non inizializzato: {e}")
        
        log_event("Avvio del sistema di irrigazione", "INFO")
        
        # Disattiva Bluetooth se disponibile per risparmiare memoria
        try:
            import bluetooth
            bt = bluetooth.BLE()
            bt.active(False)
            log_event("Bluetooth disattivato", "INFO")
        except ImportError:
            print("Modulo Bluetooth non presente.")
        
        # Pulizia iniziale della memoria
        gc.collect()
        
        # Resetta lo stato di tutte le zone per sicurezza
        log_event("Arresto di tutte le zone attive", "INFO")
        stop_all_zones()
        
        # Inizializza la rete WiFi
        try:
            print("Inizializzazione della rete WiFi...")
            initialize_network()
            log_event("Rete WiFi inizializzata", "INFO")
        except Exception as e:
            log_event(f"Errore durante l'inizializzazione della rete WiFi: {e}", "ERROR")
            # Riprova con reset
            try:
                reset_wifi_module()
                initialize_network()
                log_event("Rete WiFi inizializzata dopo reset", "INFO")
            except Exception as e:
                log_event(f"Impossibile inizializzare la rete WiFi: {e}", "ERROR")
                print("Continuazione con funzionalità limitate...")

        # Resetta lo stato del programma all'avvio
        reset_program_state()
        log_event("Stato del programma resettato", "INFO")
        
        # Inizializza le zone
        if not initialize_pins():
            log_event("Errore: Nessuna zona inizializzata correttamente.", "ERROR")
            print("Errore: Nessuna zona inizializzata correttamente.")
        else:
            log_event("Zone inizializzate correttamente.", "INFO")
            print("Zone inizializzate correttamente.")
        
        # Avvia i task asincroni
        print("Avvio del web server...")
        web_server_task = asyncio.create_task(start_web_server())
        log_event("Web server avviato", "INFO")
        
        print("Avvio del controllo dei programmi...")
        program_check_task = asyncio.create_task(program_check_loop())
        log_event("Loop di controllo programmi avviato", "INFO")
        
        # Avvia il task per il retry della connessione WiFi
        retry_wifi_task = asyncio.create_task(retry_client_connection())
        log_event("Task di retry connessione WiFi avviato", "INFO")
        
        # Avvia il watchdog
        watchdog_task = asyncio.create_task(watchdog_loop())
        log_event("Watchdog avviato", "INFO")

        # Avvia il sistema di diagnostica
        diagnostics_task = asyncio.create_task(start_diagnostics())
        log_event("Sistema di diagnostica avviato", "INFO")

        # Mantiene il loop in esecuzione
        log_event("Sistema avviato con successo", "INFO")
        print("Sistema avviato con successo. In esecuzione...")
        
        # Loop principale - resetta il watchdog hardware
        while True:
            if wdt:
                wdt.feed()  # Reimposta il watchdog hardware
            await asyncio.sleep(1)

    except Exception as e:
        log_event(f"Errore critico nel main: {e}", "ERROR")
        print(f"Errore critico: {e}")
        # In caso di errore grave, attendere 10 secondi e riavviare il sistema
        time.sleep(10)
        machine.reset()

def start():
    """
    Funzione di avvio chiamata quando il sistema si accende.
    Gestisce eventuali eccezioni generali.
    """
    try:
        # Imposta una frequenza di clock più alta per prestazioni migliori
        try:
            import machine
            # Imposta frequenza CPU a 240MHz
            machine.freq(240000000)
        except:
            pass
        
        # Avvia il loop principale
        asyncio.run(main())
    except Exception as e:
        print(f"Errore nell'avvio del main: {e}")
        # Attendi 10 secondi e riavvia
        time.sleep(10)
        import machine
        machine.reset()

# Punto di ingresso principale
if __name__ == '__main__':
    start()