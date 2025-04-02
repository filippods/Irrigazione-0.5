"""
File principale del sistema di irrigazione.
Inizializza il sistema e avvia i servizi necessari.
"""
from wifi_manager import initialize_network, reset_wifi_module, retry_client_connection
from web_server import start_web_server
from zone_manager import initialize_pins, stop_all_zones
from program_manager import check_programs, reset_program_state
from log_manager import log_event
import uasyncio as asyncio
import gc
import machine
import time

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
            
            # Forza la garbage collection ogni ora
            gc.collect()
            
            await asyncio.sleep(3600)  # 1 ora
        except Exception as e:
            log_event(f"Errore nel watchdog: {e}", "ERROR")
            await asyncio.sleep(600)  # 10 minuti in caso di errore

async def main():
    """
    Funzione principale che inizializza il sistema e avvia i task asincroni.
    """
    try:
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

        # Mantiene il loop in esecuzione
        log_event("Sistema avviato con successo", "INFO")
        print("Sistema avviato con successo. In esecuzione...")
        
        # Loop principale
        while True:
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