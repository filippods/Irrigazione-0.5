"""
Modulo per la gestione dello stato del programma.
Contiene variabili globali e funzioni per gestire lo stato di esecuzione dei programmi.
"""
import ujson
import uos as os
from log_manager import log_event

# Variabili globali per gestire lo stato del programma
program_running = False
current_program_id = None
PROGRAM_STATE_FILE = '/data/program_state.json'

def save_program_state():
    """
    Salva lo stato attuale del programma in esecuzione su file.
    """
    global program_running, current_program_id
    
    try:
        state_data = {
            'program_running': program_running, 
            'current_program_id': current_program_id
        }
        
        # Assicurati che la directory esista
        try:
            os.stat('/data')
        except OSError:
            os.mkdir('/data')
            
        # Usa la modalità più sicura di scrittura: scrivi in un file temporaneo e poi rinomina
        temp_file = PROGRAM_STATE_FILE + '.tmp'
        with open(temp_file, 'w') as f:
            ujson.dump(state_data, f)
            f.flush()  # Forza il flush dei dati sul disco
            
        # Rinomina il file temporaneo (operazione atomica su molti filesystem)
        os.rename(temp_file, PROGRAM_STATE_FILE)
        
        print(f"Stato del programma salvato: program_running={program_running}, current_program_id={current_program_id}")
        
        # Aggiungiamo una verifica immediata per confermare il salvataggio
        verify_save()
        
    except OSError as e:
        log_event(f"Errore durante il salvataggio dello stato del programma: {e}", "ERROR")
        print(f"Errore durante il salvataggio dello stato del programma: {e}")

def verify_save():
    """
    Verifica che lo stato del programma sia stato salvato correttamente.
    """
    global program_running, current_program_id
    
    try:
        with open(PROGRAM_STATE_FILE, 'r') as f:
            state = ujson.load(f)
            if state.get('program_running') != program_running or state.get('current_program_id') != current_program_id:
                log_event("Verifica salvataggio fallita: stato non corrispondente. Ripetizione salvataggio.", "WARNING")
                # Se lo stato letto non corrisponde a quello che avremmo dovuto salvare, risalva
                with open(PROGRAM_STATE_FILE, 'w') as f:
                    state_data = {
                        'program_running': program_running, 
                        'current_program_id': current_program_id
                    }
                    ujson.dump(state_data, f)
                    f.flush()  # Aggiungo flush per assicurare la scrittura sul disco
    except Exception as e:
        log_event(f"Errore durante la verifica del salvataggio: {e}", "WARNING")

def load_program_state():
    """
    Carica lo stato del programma dal file.
    Aggiorna le variabili globali program_running e current_program_id.
    """
    global program_running, current_program_id
    
    # Salva i valori correnti per il debug
    previous_running = program_running
    previous_id = current_program_id
    
    try:
        with open(PROGRAM_STATE_FILE, 'r') as f:
            try:
                state = ujson.load(f)
                if not isinstance(state, dict):
                    raise ValueError("Formato stato non valido")
                
                # Controllo esplicito dei tipi per evitare errori
                loaded_running = state.get('program_running')
                loaded_id = state.get('current_program_id')
                
                # Non sovrascrivere lo stato attivo con quello inattivo
                # Questa è una protezione contro la race condition osservata
                if loaded_running is not None:
                    if not loaded_running and program_running:
                        log_event("Rilevata incoerenza nello stato del programma. Mantengo stato attivo.", "WARNING")
                        # In questo caso salviamo lo stato corretto subito
                        save_program_state()
                    else:
                        program_running = bool(loaded_running)  # Conversione esplicita a boolean
                
                # Aggiorna l'ID solo se ce n'è uno nuovo e valido
                if loaded_id is not None:
                    current_program_id = loaded_id
                elif loaded_running and current_program_id is None:
                    log_event("Stato running ma ID programma mancante", "WARNING")
                
                # Log solo se lo stato è cambiato (riduce i log inutili)
                if previous_running != program_running or previous_id != current_program_id:
                    print(f"Stato del programma caricato: program_running={program_running}, current_program_id={current_program_id}")
            except ValueError as e:
                # Errore nella decodifica JSON, resettiamo lo stato solo se non è già attivo
                log_event(f"Errore nella decodifica JSON del file stato: {e}. Inizializzazione nuovo stato.", "WARNING")
                print(f"Errore nella decodifica JSON del file stato: {e}. Inizializzazione nuovo stato.")
                if not program_running:  # Solo se non c'è un programma in esecuzione
                    program_running = False
                    current_program_id = None
                save_program_state()
    except OSError as e:
        # Il file non esiste, inizializziamo lo stato solo se non è già attivo
        log_event(f"File stato non trovato: {e}. Inizializzazione nuovo stato.", "INFO")
        print(f"File stato non trovato: {e}. Inizializzazione nuovo stato.")
        if not program_running:  # Solo se non c'è un programma in esecuzione
            program_running = False
            current_program_id = None
        save_program_state()