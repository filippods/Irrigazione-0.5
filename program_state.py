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
        state_data = {
            'program_running': program_running, 
            'current_program_id': current_program_id
        }
        with open(PROGRAM_STATE_FILE, 'w') as f:
            ujson.dump(state_data, f)
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
            try:
                state = ujson.load(f)
                if not isinstance(state, dict):
                    raise ValueError("Formato stato non valido")
                    
                program_running = state.get('program_running', False)
                current_program_id = state.get('current_program_id', None)
                print(f"Stato del programma caricato: program_running={program_running}, current_program_id={current_program_id}")
            except ValueError as e:
                # Errore nella decodifica JSON, resettiamo lo stato
                log_event(f"Errore nella decodifica JSON del file stato: {e}. Inizializzazione nuovo stato.", "WARNING")
                print(f"Errore nella decodifica JSON del file stato: {e}. Inizializzazione nuovo stato.")
                program_running = False
                current_program_id = None
                save_program_state()
    except OSError as e:
        # Il file non esiste, inizializziamo lo stato
        log_event(f"File stato non trovato: {e}. Inizializzazione nuovo stato.", "INFO")
        print(f"File stato non trovato: {e}. Inizializzazione nuovo stato.")
        program_running = False
        current_program_id = None
        save_program_state()