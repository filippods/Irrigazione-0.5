"""
Modulo per la gestione dello stato del programma.
Contiene variabili globali e funzioni per gestire lo stato di esecuzione dei programmi.
"""
import ujson
from log_manager import log_event

# Variabili globali per gestire lo stato del programma
program_running = False
current_program_id = None
PROGRAM_STATE_FILE = '/data/program_state.json'

def save_program_state():
    """
    Salva lo stato attuale del programma in esecuzione su file.
    """
    try:
        with open(PROGRAM_STATE_FILE, 'w') as f:
            ujson.dump({
                'program_running': program_running, 
                'current_program_id': current_program_id
            }, f)
        print(f"Stato del programma salvato: program_running={program_running}, current_program_id={current_program_id}")
    except OSError as e:
        log_event(f"Errore durante il salvataggio dello stato del programma: {e}", "ERROR")
        print(f"Errore durante il salvataggio dello stato del programma: {e}")

def load_program_state():
    """
    Carica lo stato del programma dal file.
    Aggiorna le variabili globali program_running e current_program_id.
    """
    global program_running, current_program_id
    try:
        with open(PROGRAM_STATE_FILE, 'r') as f:
            state = ujson.load(f)
            program_running = state.get('program_running', False)
            current_program_id = state.get('current_program_id', None)
            print(f"Stato del programma caricato: program_running={program_running}, current_program_id={current_program_id}")
    except (OSError, ValueError):
        # Resetta lo stato se il file non esiste, è vuoto o c'è un errore
        log_event("Nessuno stato salvato trovato o stato non valido, avvio da zero", "INFO")
        print("Nessuno stato salvato trovato o stato non valido, avvio da zero.")
        program_running = False
        current_program_id = None
        save_program_state()  # Salva il nuovo stato inizializzato