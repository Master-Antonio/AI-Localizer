# 🎮 AI Game Localizer Prototype

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![AI](https://img.shields.io/badge/AI-Offline%20%26%20Secure-orange) ![GPU](https://img.shields.io/badge/Hardware-CUDA%20Accelerated-76b900)

**AI Game Localizer** è una suite open-source per la traduzione automatica di file di localizzazione videogiochi (CSV, Excel).
Lavora **completamente offline** (senza API costose) e garantisce l'integrità del codice di gioco tramite la gestione delle variabili in stringa.

Il progetto è attualmente in sviluppo ed è solo un prototipo, quindi aspettatevi bugs e problemi.
---

## ✨ Funzionalità Principali

### 🚀 Core & Performance
* **Traduzione AI Offline:** Utilizza modelli neurali `Helsinki-NLP` (MarianMT) in locale.
* **Accelerazione GPU (CUDA):** Supporto nativo per schede NVIDIA con modalità **FP16 (Turbo)** per traduzioni veloci.
* **Monitor Hardware:** Badge visivo in tempo reale che indica se stai usando CPU (Arancione) o GPU (Verde).
* **Batch Processing:** Carica intere cartelle o liste di file e traducili in sequenza automaticamente.

### 🛡️ Sicurezza & QA (Quality Assurance)
* **Smart Masking:** Protegge automaticamente codici (`#G...#`), tag HTML/XML, e variabili (`{0}`, `%s`, `$VAR`).
* **Variable Manager:** Interfaccia dedicata per **aggiungere/rimuovere le tue regole Regex** personalizzate per proteggere formati di variabili specifici del tuo gioco.
* **Safety Check:** Blocca la traduzione se l'IA corrompe o perde una variabile.
* **Fail Fixer:** Finestra di dialogo per correggere manualmente gli errori critici prima del salvataggio.
* **Online Fallback:** (Opzionale) Usa Google Translate per riparare automaticamente le frasi dove l'IA locale fallisce il Safety Check.

### 🎛️ Gestione Studio
* **Project Profiles:** Salva configurazioni diverse (Glossari, Regex, Lingue) per progetti diversi (es. *Skyrim* vs *Cyberpunk*).
* **Model Manager:** Scansiona la cache di HuggingFace e permette di eliminare i modelli scaricati per liberare spazio su disco.
* **Glossario:** Supporto per dizionari personalizzati (`.csv`/`.txt`) per mantenere la coerenza della Lore.
* **Anteprima Live:** Estrae 3 righe casuali dal file per testare la qualità e le regex prima di lanciare il batch.

---

## 🛠️ Installazione

### 1. Requisiti
* **Python 3.10** o superiore.
* (Consigliato) Scheda Video NVIDIA aggiornata.

### 2. Installazione Dipendenze
Esegui questo comando nel terminale per installare tutte le librerie necessarie:

```bash
pip install customtkinter pandas torch transformers sentencepiece tqdm deep-translator huggingface_hub packaging openpyxl
```
(Nota: Se hai una GPU AMD, installa la versione ROCm di PyTorch separatamente).

## 🚀 Guida all'Uso

Avvia il programma:
```bash
python AI_Localizer_V1_Complete.py
```

1. Scheda "Esecuzione"

    Seleziona File: Carica i tuoi file .csv o .xlsx.

    Configura: Scegli la colonna del testo e le lingue.

    Safety Check: Tienilo attivo per evitare crash del gioco.

    Avvia: Lancia il processo.

2. Scheda "Gestione Variabili"

    Qui puoi vedere le regole Regex attive che proteggono il codice.

    Aggiungi: Inserisci un nome e un pattern regex (es. \[.*?\]) per proteggere nuovi tipi di tag.

    Reset: Ripristina le regole di default.

3. Scheda "Gestione Modelli"

    Clicca Scansiona Disco per vedere i modelli AI scaricati.

    Seleziona quelli vecchi e clicca Elimina per liberare GB di spazio.

4. Scheda "Configurazione"

    Glossario: Carica file .txt (formato: Originale;Tradotto) per forzare termini specifici.

    FP16: Attivalo se hai una GPU NVIDIA (velocizza del 40%).

    Regex Pulizia: Regole applicate dopo la traduzione (es. per rimuovere spazi doppi).

## 📂 Struttura Output

Il programma crea nella cartella dello script:

    profiles.json: Il database dei tuoi profili progetto.

    session_log.txt: Log degli errori e delle operazioni.

    *_FINAL.csv: Il file tradotto pronto per il gioco.

## 🤝 Contribuire
Se vuoi supportarmi: https://paypal.me/MasterAntonio

Progetto Open Source. Sentiti libero di aprire Issue o Pull Request per migliorare il supporto a nuovi formati o aggiungere lingue.

## 📄 Licenza

Distribuito sotto licenza GNU GPL V3.0.

