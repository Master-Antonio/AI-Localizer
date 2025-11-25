"""
---------------------------------------------------------------------------
AI CSV LOCALIZER 
---------------------------------------------------------------------------
Author:      https://github.com/Master-Antonio
Copyright:   (c) 2024-2025 All Rights Reserved
License:     GNU GPL V3.0
Description: Tool di traduzione offline per file csv tramite
             supporto AI (Neural Networks) con diverse funzionalità aggiuntive
---------------------------------------------------------------------------
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import pandas as pd
from transformers import MarianMTModel, MarianTokenizer
import torch
import math
import re
import threading
import time
import os
import json
import random
import datetime
import csv

# --- IMPORT OPZIONALI ---
try:
    from huggingface_hub import scan_cache_dir
    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    ONLINE_AVAILABLE = True
except ImportError:
    ONLINE_AVAILABLE = False

try:
    from rapidfuzz import process, fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

# --- CONFIGURAZIONE ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_FILE = os.path.join(SCRIPT_DIR, "profiles.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "session_log.txt")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

DEFAULT_PATTERNS = [
    {"name": "Hash Codes", "pattern": r'(\#[A-Z][^\s#]*?(?:\#E|\Z))', "active": True},
    {"name": "Complex Tags", "pattern": r'(\<[^\>]*?\|[^\>]*?\>)', "active": True},
    {"name": "Variables $", "pattern": r'(\$[^\s$]*?\.\d+f\$|\$[^\s$]*\$)', "active": True},
    {"name": "Brackets []", "pattern": r'(\[.*?\])', "active": True},
    {"name": "Braces {}", "pattern": r'(\{[^\s\{\}]*?\})', "active": True},
    {"name": "C-Style %", "pattern": r'(%[sdfo0-9\.]*[sdf])', "active": True},
    {"name": "New Line", "pattern": r'(\\n)', "active": True}
]

class TextProcessor:
    def __init__(self):
        self.placeholder_map = {}
        self.placeholder_counter = 0
        self.regex_rules = []
        self.protection_patterns = []

    def update_patterns(self, pattern_list):
        self.protection_patterns = [p["pattern"] for p in pattern_list if p["active"]]

    def fix_mojibake(self, text):
        text = str(text)
        if not text.strip(): return text
        replacements = {
            'â€”': '—', 'â€¦': '...', 'â€™': '’', 'â€œ': '“',
            'â€': '”', 'â€ś': '”', 'â€ť': '”'
        }
        for old, new in replacements.items(): text = text.replace(old, new)
        return text

    def fix_punctuation(self, text):
        text = re.sub(r'\s+([.,:;!?])', r'\1', text)
        return text

    def mask_text(self, text):
        self.placeholder_map = {}
        self.placeholder_counter = 0
        if not self.protection_patterns: return text
        
        full_pattern = '|'.join(self.protection_patterns)
        text = str(text)
        if not text.strip(): return text

        def replacer(match):
            code = match.group(0)
            # Deduplicazione
            for k, v in self.placeholder_map.items():
                if v == code: return k
            
            # Usiamo __X_0_X__ come maschera per le variabili in stringa
            key = f"__X_{self.placeholder_counter}_X__"
            self.placeholder_map[key] = code
            self.placeholder_counter += 1
            return key

        try:
            return re.sub(full_pattern, replacer, text, flags=re.DOTALL)
        except:
            return text

    def unmask_text(self, text):
        text = str(text)
        # Ordiniamo per lunghezza inversa (es. 10 prima di 1)
        sorted_map = sorted(self.placeholder_map.items(), key=lambda x: len(x[0]), reverse=True)
        
        for ph, orig in sorted_map:
            if ph in text:
                text = text.replace(ph, orig)
            else:
                # Se l'IA ha scritto {0} invece di __X_0_X__, proviamo a recuperarlo
                try:
                    # Estrai ID numerico da __X_0_X__
                    ph_id = ph.split('_')[2] 
                    
                    # Lista di possibili allucinazioni dell'IA
                    possible_errors = [
                        f"{{{ph_id}}}",   # {0}
                        f"({ph_id})",     # (0)
                        f"[{ph_id}]",     # [0]
                        f"X_{ph_id}_X",   # X_0_X (persi gli underscore)
                        f"__X {ph_id} X__" # Spazi aggiunti
                    ]
                    
                    for err in possible_errors:
                        if err in text:
                            text = text.replace(err, orig)
                            break # Trovato e corretto
                except:
                    pass 

        return text

    def apply_regex_rules(self, text):
        for pattern, replacement in self.regex_rules:
            try:
                text = re.sub(pattern, replacement, text)
            except:
                pass
        return text
    
    def get_variables(self, text):
        found = []
        for p in self.protection_patterns:
            try:
                found.extend(re.findall(p, text))
            except:
                pass
        return found

class FailFixerDialog(ctk.CTkToplevel):
    def __init__(self, parent, failed_rows, callback_save):
        super().__init__(parent)
        self.title("Fail Fixer")
        self.geometry("900x600")
        self.failed_rows = failed_rows 
        self.callback_save = callback_save
        self.fixed_data = {} 
        
        ctk.CTkLabel(self, text=f"Trovati {len(failed_rows)} errori critici.", font=("Arial", 14, "bold"), text_color="#FF5555").pack(pady=10)
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=5)
        self.entries = {}
        
        for item in failed_rows:
            f = ctk.CTkFrame(self.scroll)
            f.pack(fill="x", pady=5)
            ctk.CTkLabel(f, text="ORIG:", font=("Consolas", 10, "bold")).pack(anchor="w", padx=5)
            ctk.CTkTextbox(f, height=50, font=("Consolas", 11)).pack(fill="x", padx=5)
            f.winfo_children()[-1].insert("0.0", item['orig'])
            f.winfo_children()[-1].configure(state="disabled")
            ctk.CTkLabel(f, text="EDIT:", font=("Consolas", 10, "bold"), text_color="orange").pack(anchor="w", padx=5)
            ent = ctk.CTkTextbox(f, height=50, font=("Consolas", 11))
            ent.insert("0.0", item['trans']) 
            ent.pack(fill="x", padx=5)
            self.entries[item['idx']] = ent
            
        ctk.CTkButton(self, text="Salva e Chiudi", command=self.save_and_close, fg_color="green").pack(pady=10)

    def save_and_close(self):
        for idx, ent in self.entries.items():
            self.fixed_data[idx] = ent.get("0.0", "end").strip()
        self.callback_save(self.fixed_data)
        self.destroy()

class TranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.app_name = "AI Localizer"
        self.version = "V1 Prototype"
        self.author = "Toriga"

        self.title(f"{self.app_name} {self.version}")
        self.geometry("1280x950")
        
        self.files_queue = []
        self.glossary_dict = {}
        self.protection_config = [d.copy() for d in DEFAULT_PATTERNS]
        self.model_checkboxes = []
        
        self.is_running = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_event = threading.Event()
        self.processor = TextProcessor()
        
        self.profiles = {}
        self.current_profile = "Default"

        self.device_name = "CPU"
        self.device_color = "#FFA500" 
        if torch.cuda.is_available():
            self.device_name = f"CUDA ({torch.cuda.get_device_name(0)})"
            self.device_color = "#2CC985"

        self.languages = {
            "Inglese": "en", "Italiano": "it", "Francese": "fr", "Spagnolo": "es",
            "Tedesco": "de", "Cinese": "zh", "Russo": "ru", "Giapponese": "ja"
        }

        # Inizializza log
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"--- Session V19 Start: {datetime.datetime.now()} ---\n")
        except: pass

        self.create_ui()
        self.after(500, self.load_profiles)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # SIDEBAR
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(self.sidebar, text=f"{self.app_name}", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(30, 5))
        ctk.CTkLabel(self.sidebar, text=f"{self.version}", font=ctk.CTkFont(size=12)).pack(pady=(0, 20))
        
        hw_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", border_width=1, border_color="gray")
        hw_frame.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(hw_frame, text="HARDWARE:", font=("Arial", 10, "bold")).pack(pady=(5,0))
        self.lbl_hw = ctk.CTkLabel(hw_frame, text=f"⚡ {self.device_name}", font=("Arial", 11, "bold"), text_color=self.device_color)
        self.lbl_hw.pack(pady=(0,5))

        ctk.CTkLabel(self.sidebar, text="PROGETTO:", font=("Arial", 11, "bold")).pack(pady=(20,5), anchor="w", padx=20)
        self.combo_profiles = ctk.CTkComboBox(self.sidebar, values=["Default"], command=self.change_profile)
        self.combo_profiles.pack(fill="x", padx=20, pady=5)
        
        frm_prof_btn = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        frm_prof_btn.pack(pady=5)
        ctk.CTkButton(frm_prof_btn, text="+", width=40, command=self.add_profile).pack(side="left", padx=2)
        ctk.CTkButton(frm_prof_btn, text="-", width=40, fg_color="#C0392B", command=self.delete_profile).pack(side="left", padx=2)
        ctk.CTkButton(frm_prof_btn, text="💾", width=40, fg_color="#2980B9", command=self.save_current_profile).pack(side="left", padx=2)

        # TABS
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=1, padx=20, pady=10, sticky="nsew")
        
        self.tab_run = self.tabview.add("Esecuzione")
        self.tab_models = self.tabview.add("Gestione Modelli")
        self.tab_preview = self.tabview.add("Anteprima")
        self.tab_qa = self.tabview.add("QA & Sicurezza")
        self.tab_vars = self.tabview.add("Variabili")
        self.tab_settings = self.tabview.add("Configurazione")
        
        self.setup_tab_run()
        self.setup_tab_models()
        self.setup_tab_preview()
        self.setup_tab_qa()
        self.setup_tab_vars()
        self.setup_tab_settings()

        # CONSOLE
        self.console_frame = ctk.CTkFrame(self, height=140, fg_color="transparent")
        self.console_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.txt_log = ctk.CTkTextbox(self.console_frame, height=120, font=("Consolas", 11), fg_color="#1E1E1E", text_color="#DCDCDC")
        self.txt_log.pack(fill="both", padx=10, pady=5)
        self.txt_log.configure(state="disabled")

    def setup_tab_run(self):
        card_file = ctk.CTkFrame(self.tab_run, fg_color=("#333333", "#2B2B2B"))
        card_file.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(card_file, text="1. FILE TARGET", font=("Arial", 12, "bold"), text_color="gray").pack(anchor="w", padx=15, pady=(10,0))
        row_f = ctk.CTkFrame(card_file, fg_color="transparent")
        row_f.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(row_f, text="📂 Seleziona File", command=self.load_files, height=35).pack(side="left", padx=5)
        self.lbl_file_count = ctk.CTkLabel(row_f, text="Nessun file", text_color="#FF5555", font=("Arial", 12, "bold"))
        self.lbl_file_count.pack(side="left", padx=15)

        card_merge = ctk.CTkFrame(self.tab_run, fg_color=("#252525", "#1F1F1F"), border_color="gray", border_width=1)
        card_merge.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(card_merge, text="2. IMPORTA VECCHIE TRADUZIONI (Opzionale)", font=("Arial", 12, "bold"), text_color="#3498DB").pack(anchor="w", padx=15, pady=(5,0))
        row_m = ctk.CTkFrame(card_merge, fg_color="transparent")
        row_m.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(row_m, text="📥 Importa da CSV", command=self.import_reference_csv, fg_color="#3498DB").pack(side="left", padx=5)
        self.chk_fuzzy = ctk.CTkCheckBox(row_m, text="Fuzzy Match", text_color="#3498DB") 
        if FUZZY_AVAILABLE:
            self.chk_fuzzy.pack(side="left", padx=15)
        self.lbl_merge_status = ctk.CTkLabel(row_m, text="", text_color="orange")
        self.lbl_merge_status.pack(side="left", padx=10)

        card_conf = ctk.CTkFrame(self.tab_run, fg_color=("#333333", "#2B2B2B"))
        card_conf.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(card_conf, text="3. PARAMETRI", font=("Arial", 12, "bold"), text_color="gray").pack(anchor="w", padx=15, pady=(10,0))
        grid = ctk.CTkFrame(card_conf, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=10)
        
        self.combo_col = ctk.CTkComboBox(grid, values=["Carica file..."], width=200)
        self.combo_col.grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkLabel(grid, text="Colonna").grid(row=1, column=0)
        
        self.combo_src = ctk.CTkComboBox(grid, values=list(self.languages.keys()))
        self.combo_src.grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(grid, text="Da Lingua").grid(row=1, column=1)
        
        self.combo_tgt = ctk.CTkComboBox(grid, values=list(self.languages.keys()))
        self.combo_tgt.grid(row=0, column=2, padx=5, pady=5)
        ctk.CTkLabel(grid, text="A Lingua").grid(row=1, column=2)

        self.chk_skip_existing = ctk.CTkCheckBox(card_conf, text="Smart Skip: Non toccare celle già piene", text_color="#55FF55")
        self.chk_skip_existing.select()
        self.chk_skip_existing.pack(anchor="w", padx=20, pady=5)

        card_act = ctk.CTkFrame(self.tab_run, fg_color="transparent")
        card_act.pack(fill="x", padx=10, pady=10)
        self.btn_start = ctk.CTkButton(card_act, text="🚀 AVVIA / RIPRENDI", command=self.start_thread, fg_color="#27AE60", height=45, font=("Arial", 14, "bold"))
        self.btn_start.pack(side="left", padx=5, fill="x", expand=True)
        self.btn_stop = ctk.CTkButton(card_act, text="🛑 SALVA E STOP", command=self.stop_process, state="disabled", fg_color="#C0392B", height=45)
        self.btn_stop.pack(side="left", padx=5, fill="x", expand=True)

        self.lbl_eta = ctk.CTkLabel(self.tab_run, text="Pronto.", font=("Consolas", 12))
        self.lbl_eta.pack(pady=5)
        self.progress = ctk.CTkProgressBar(self.tab_run)
        self.progress.pack(fill="x", padx=10, pady=5)
        self.progress.set(0)

    def setup_tab_models(self):
        ctk.CTkLabel(self.tab_models, text="Gestione Cache HuggingFace", font=("Arial", 14, "bold")).pack(pady=10)
        self.scroll_models = ctk.CTkScrollableFrame(self.tab_models, height=350)
        self.scroll_models.pack(fill="both", expand=True, padx=20, pady=10)
        frame_actions = ctk.CTkFrame(self.tab_models, fg_color="transparent")
        frame_actions.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(frame_actions, text="🔄 Scansiona", command=self.scan_models, fg_color="#3498DB").pack(side="left", padx=5, expand=True)
        ctk.CTkButton(frame_actions, text="🗑️ Elimina Selezionati", command=self.delete_selected_models, fg_color="#C0392B").pack(side="left", padx=5, expand=True)
        if not HF_HUB_AVAILABLE:
            ctk.CTkLabel(self.tab_models, text="Libreria mancante.", text_color="red").pack()

    def setup_tab_preview(self):
        top = ctk.CTkFrame(self.tab_preview)
        top.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(top, text="🎲 Estrai 3 Righe Random", command=self.generate_preview, fg_color="#8E44AD").pack(side="right", padx=10, pady=10)
        self.txt_preview = ctk.CTkTextbox(self.tab_preview, font=("Consolas", 12), wrap="word")
        self.txt_preview.pack(fill="both", expand=True, padx=10, pady=10)

    def setup_tab_qa(self):
        ctk.CTkLabel(self.tab_qa, text="Impostazioni QA", font=("Arial", 14, "bold")).pack(pady=10)
        card = ctk.CTkFrame(self.tab_qa)
        card.pack(fill="x", padx=20, pady=10)
        self.chk_safety = ctk.CTkCheckBox(card, text="Safety Check (Blocca se variabili perse)", text_color="#FF5555")
        self.chk_safety.select()
        self.chk_safety.pack(anchor="w", padx=20, pady=10)
        self.chk_punct = ctk.CTkCheckBox(card, text="Auto-Correzione Punteggiatura", text_color="#55FF55")
        self.chk_punct.select()
        self.chk_punct.pack(anchor="w", padx=20, pady=10)
        self.chk_len_check = ctk.CTkCheckBox(card, text="Avviso Lunghezza (>30%)")
        self.chk_len_check.select()
        self.chk_len_check.pack(anchor="w", padx=20, pady=10)
        self.chk_debug_col = ctk.CTkCheckBox(card, text="Colonna 'Status' nel CSV")
        self.chk_debug_col.select()
        self.chk_debug_col.pack(anchor="w", padx=20, pady=10)
        if ONLINE_AVAILABLE:
            self.chk_online = ctk.CTkCheckBox(card, text="Google Translate Fallback")
            self.chk_online.pack(anchor="w", padx=20, pady=10)
        else:
            self.chk_online = None

    def setup_tab_vars(self):
        ctk.CTkLabel(self.tab_vars, text="Regex Variabili", font=("Arial", 14, "bold")).pack(pady=10)
        self.scroll_vars = ctk.CTkScrollableFrame(self.tab_vars, height=300)
        self.scroll_vars.pack(fill="both", expand=True, padx=10)
        
        frame_add = ctk.CTkFrame(self.tab_vars)
        frame_add.pack(fill="x", padx=10, pady=10)
        self.entry_var_name = ctk.CTkEntry(frame_add, placeholder_text="Nome")
        self.entry_var_name.pack(side="left", padx=5, fill="x", expand=True)
        self.entry_var_regex = ctk.CTkEntry(frame_add, placeholder_text="Regex")
        self.entry_var_regex.pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(frame_add, text="Aggiungi", command=self.add_custom_pattern, width=80, fg_color="green").pack(side="left", padx=5)
        
        ctk.CTkButton(self.tab_vars, text="Reset Default", command=self.reset_patterns, fg_color="gray").pack(pady=10)

    def setup_tab_settings(self):
        card_g = ctk.CTkFrame(self.tab_settings)
        card_g.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(card_g, text="Carica Glossario", command=self.load_glossary).pack(side="left", padx=10, pady=10)
        self.lbl_gloss_status = ctk.CTkLabel(card_g, text="0 termini", text_color="orange")
        self.lbl_gloss_status.pack(side="left", padx=10)
        
        card_p = ctk.CTkFrame(self.tab_settings)
        card_p.pack(fill="x", padx=20, pady=10)
        self.chk_fp16 = ctk.CTkCheckBox(card_p, text="Usa FP16 (Turbo Mode)")
        self.chk_fp16.pack(anchor="w", padx=10, pady=10)
        
        card_r = ctk.CTkFrame(self.tab_settings)
        card_r.pack(fill="x", padx=20, pady=10)
        self.txt_regex = ctk.CTkTextbox(card_r, height=80)
        self.txt_regex.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(card_r, text="Applica Pulizia Regex", command=self.save_regex_from_ui).pack(anchor="e", padx=10, pady=5)

    # --- LOGICA: MERGE ---
    def import_reference_csv(self):
        if not self.files_queue:
            messagebox.showwarning("!", "Carica prima il file Target!")
            return
        
        ref_path = filedialog.askopenfilename(filetypes=[("Ref", "*.csv")])
        if not ref_path: return

        col_src = simpledialog.askstring("Input", "Nome colonna INGLESE nel file vecchio:")
        col_tgt = simpledialog.askstring("Input", "Nome colonna ITALIANA nel file vecchio:")
        
        if not col_src or not col_tgt: return

        target_col_main = self.combo_col.get()
        self.log("Avvio importazione Reference...")
        
        threading.Thread(target=self._process_merge, args=(ref_path, col_src, col_tgt, target_col_main)).start()

    def _process_merge(self, ref_path, col_src, col_tgt, col_main):
        try:
            # Force string type on reference
            try:
                df_ref = pd.read_csv(ref_path, sep=';', on_bad_lines='skip', dtype=str, keep_default_na=False)
            except:
                df_ref = pd.read_csv(ref_path, sep=None, engine='python', dtype=str, keep_default_na=False)
            
            df_ref.columns = df_ref.columns.str.strip()
            if col_src not in df_ref.columns or col_tgt not in df_ref.columns:
                self.log("Errore: Colonne non trovate nel file di riferimento.")
                return

            df_ref = df_ref.dropna(subset=[col_src, col_tgt])
            ref_dict = dict(zip(df_ref[col_src].astype(str), df_ref[col_tgt].astype(str)))
            self.log(f"Caricate {len(ref_dict)} traduzioni dal vecchio file.")

            main_path = self.files_queue[0]
            if main_path.endswith('.csv'):
                try:
                    df_main = pd.read_csv(main_path, sep=';', on_bad_lines='skip', dtype=str, keep_default_na=False)
                except:
                    df_main = pd.read_csv(main_path, sep=None, engine='python', dtype=str, keep_default_na=False)
            else:
                df_main = pd.read_excel(main_path, dtype=str)
            
            df_main.columns = df_main.columns.str.strip()
            
            matches = 0
            fuzzy_matches = 0
            use_fuzzy = self.chk_fuzzy.get() and FUZZY_AVAILABLE
            new_col_data = []
            
            for txt in df_main[col_main].astype(str):
                txt_clean = str(txt).strip()
                if txt_clean in ref_dict:
                    new_col_data.append(ref_dict[txt_clean])
                    matches += 1
                elif use_fuzzy and txt_clean:
                    best_match = process.extractOne(txt_clean, ref_dict.keys(), scorer=fuzz.ratio)
                    if best_match and best_match[1] > 90:
                        new_col_data.append(ref_dict[best_match[0]])
                        fuzzy_matches += 1
                    else:
                        new_col_data.append(txt)
                else:
                    new_col_data.append(txt)

            df_main[col_main] = new_col_data
            out_path = main_path.replace(".csv", "_MERGED.csv").replace(".xlsx", "_MERGED.csv")
            df_main.to_csv(out_path, sep=';', index=False, encoding='utf-8-sig', quoting=csv.QUOTE_MINIMAL)
            
            self.files_queue[0] = out_path
            self.lbl_merge_status.configure(text=f"Merge: {matches} esatti, {fuzzy_matches} fuzzy")
            self.log(f"Merge completato. Salvato: {os.path.basename(out_path)}")
            messagebox.showinfo("Merge Finito", f"Recuperate {matches} traduzioni.")

        except Exception as e:
            self.log(f"Errore Merge: {e}")

    # --- LOGICA VARS ---
    def refresh_vars_list(self):
        for w in self.scroll_vars.winfo_children(): w.destroy()
        for idx, item in enumerate(self.protection_config):
            r = ctk.CTkFrame(self.scroll_vars)
            r.pack(fill="x", pady=2)
            v = ctk.BooleanVar(value=item["active"])
            ctk.CTkCheckBox(r, text=item["name"], variable=v, command=lambda i=idx, x=v: self.toggle_pattern(i,x)).pack(side="left", padx=5)
            e = ctk.CTkEntry(r)
            e.insert(0, item["pattern"])
            e.configure(state="readonly")
            e.pack(side="left", fill="x", expand=True, padx=5)
            ctk.CTkButton(r, text="X", width=30, fg_color="#C0392B", command=lambda i=idx: self.delete_pattern(i)).pack(side="right", padx=5)
        self.processor.update_patterns(self.protection_config)

    def add_custom_pattern(self):
        name = self.entry_var_name.get()
        pat = self.entry_var_regex.get()
        if not name or not pat:
            messagebox.showwarning("Err", "Dati mancanti")
            return
        try:
            re.compile(pat)
        except: 
            messagebox.showerror("Err", "Regex non valida")
            return
        self.protection_config.append({"name": name, "pattern": pat, "active": True})
        self.refresh_vars_list()
        self.entry_var_name.delete(0, 'end')
        self.entry_var_regex.delete(0, 'end')

    def delete_pattern(self, idx):
        if idx < len(self.protection_config):
            del self.protection_config[idx]
            self.refresh_vars_list()

    def toggle_pattern(self, i, v):
        self.protection_config[i]["active"] = v.get()
        self.processor.update_patterns(self.protection_config)
    
    def reset_patterns(self):
        self.protection_config = [d.copy() for d in DEFAULT_PATTERNS]
        self.refresh_vars_list()

    # --- LOGICA MODELS ---
    def scan_models(self):
        if not HF_HUB_AVAILABLE: return
        for w in self.scroll_models.winfo_children(): w.destroy()
        self.model_checkboxes = []
        try:
            info = scan_cache_dir()
            repos = [r for r in info.repos if r.repo_type == 'model']
            if not repos:
                ctk.CTkLabel(self.scroll_models, text="Nessun modello.").pack()
                return
            
            for r in repos:
                size = r.size_on_disk / (1024*1024)
                row = ctk.CTkFrame(self.scroll_models)
                row.pack(fill="x", pady=2)
                v = ctk.BooleanVar()
                ctk.CTkCheckBox(row, text=f"{r.repo_id} ({size:.1f} MB)", variable=v).pack(side="left", padx=10)
                self.model_checkboxes.append((v, r))
        except:
            pass

    def delete_selected_models(self):
        to_del = [r for v,r in self.model_checkboxes if v.get()]
        if not to_del: return
        if messagebox.askyesno("Conferma", f"Eliminare {len(to_del)} modelli?"):
            c = 0
            for r in to_del: 
                try:
                    scan_cache_dir().delete_revisions(*[x.commit_hash for x in r.revisions]).execute()
                    c+=1
                except:
                    pass
            messagebox.showinfo("Info", f"Eliminati {c} modelli.")
            self.scan_models()

    # --- LOGIC: PREVIEW ---
    def generate_preview(self):
        if not self.files_queue:
            messagebox.showwarning("!", "Carica file!")
            return
        self.txt_preview.delete("0.0", "end")
        self.txt_preview.insert("0.0", "Elaborazione...\n")
        threading.Thread(target=self._run_prev, daemon=True).start()

    def _run_prev(self):
        try:
            f = self.files_queue[0]
            col = self.combo_col.get()
            src = self.languages[self.combo_src.get()]
            tgt = self.languages[self.combo_tgt.get()]
            try:
                df = pd.read_csv(f, sep=';', engine='python', nrows=50, dtype=str, keep_default_na=False)
                df.columns = df.columns.str.strip()
            except:
                df = pd.read_csv(f, sep=None, engine='python', nrows=50, dtype=str, keep_default_na=False)
            
            if col not in df.columns: return
            cands = df[col].astype(str).tolist()
            # Filter empty
            cands = [x for x in cands if x.strip()]
            
            if not cands: return
            samps = random.sample(cands, min(3, len(cands)))
            
            mod = f"Helsinki-NLP/opus-mt-{src}-{tgt}"
            tk_prev = MarianTokenizer.from_pretrained(mod)
            md_prev = MarianMTModel.from_pretrained(mod)
            
            self.processor.update_patterns(self.protection_config)
            out_txt = ""
            for s in samps:
                m = self.processor.mask_text(self.processor.fix_mojibake(s))
                inp = tk_prev([m], return_tensors="pt")
                out = md_prev.generate(**inp)
                dec = tk_prev.batch_decode(out, skip_special_tokens=True)[0]
                fin = self.processor.unmask_text(dec)
                if self.chk_punct.get():
                    fin = self.processor.fix_punctuation(fin)
                
                warn = ""
                if self.chk_safety.get():
                    ok, _ = self.safety_check(s, fin)
                    if not ok: warn = " [⚠️ SAFETY FAIL]"
                out_txt += f"ORG: {s}\nTRD: {fin}{warn}\n---\n"
            
            self.txt_preview.delete("0.0", "end")
            self.txt_preview.insert("0.0", out_txt)
        except Exception as e:
            self.log(f"Err Prev: {e}")

    # --- CORE RUN ---
    def start_thread(self):
        if not self.files_queue:
            messagebox.showwarning("!", "Seleziona file!")
            return
        self.is_running = True
        self.stop_event.clear()
        self.pause_event.set()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        threading.Thread(target=self.run_batch, daemon=True).start()

    def run_batch(self):
        col = self.combo_col.get()
        src = self.languages[self.combo_src.get()]
        tgt = self.languages[self.combo_tgt.get()]
        fp16 = self.chk_fp16.get() and torch.cuda.is_available()
        safety = bool(self.chk_safety.get())
        debug_col = bool(self.chk_debug_col.get())
        use_online = self.chk_online.get() if self.chk_online else False
        len_check = bool(self.chk_len_check.get())
        skip_existing = bool(self.chk_skip_existing.get())
        auto_punct = bool(self.chk_punct.get())

        model_name = f"Helsinki-NLP/opus-mt-{src}-{tgt}"
        device = "cuda" if torch.cuda.is_available() else "cpu"

        total_trans = 0
        total_skip = 0

        try:
            self.log(f"Caricamento {model_name}...")
            tokenizer = MarianTokenizer.from_pretrained(model_name)
            model = MarianMTModel.from_pretrained(model_name).to(device)
            if fp16: model = model.half()
            self.processor.update_patterns(self.protection_config)

            for fpath in self.files_queue:
                if self.stop_event.is_set(): break
                self.log(f"File: {os.path.basename(fpath)}")
                
                if fpath.endswith('.csv'):
                    try:
                        df = pd.read_csv(fpath, sep=';', on_bad_lines='skip', dtype=str, keep_default_na=False)
                    except:
                        df = pd.read_csv(fpath, sep=None, engine='python', dtype=str, keep_default_na=False)
                else:
                    df = pd.read_excel(fpath, dtype=str)
                
                df.columns = df.columns.str.strip()
                if col not in df.columns: continue

                rows_to_do = []
                if skip_existing:
                    rows_to_do = (df[col] == "") | (df[col].isna())
                    total_skip += len(df) - rows_to_do.sum()
                else:
                    rows_to_do = [True] * len(df)

                df.loc[rows_to_do, col] = df.loc[rows_to_do, col].apply(self.processor.fix_mojibake)
                df['Masked'] = df[col].apply(self.processor.mask_text)

                unique = [t for t in list(df.loc[rows_to_do, 'Masked'].unique()) if str(t).strip()]
                cache_file = f"{fpath}.cache.json"
                cache = {}
                if os.path.exists(cache_file):
                    with open(cache_file, 'r', encoding='utf-8') as f: cache = json.load(f)
                
                todo = [t for t in unique if t not in cache]
                bs = 64 if fp16 else 32
                if device == "cpu": bs = 16
                
                start_t = time.time()
                proc = 0
                
                for i in range(0, len(todo), bs):
                    if self.stop_event.is_set(): break
                    self.pause_event.wait()
                    batch = todo[i:i+bs]
                    try:
                        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
                        with torch.no_grad(): trans = model.generate(**inputs)
                        res = tokenizer.batch_decode(trans, skip_special_tokens=True)
                        for s, r in zip(batch, res): cache[s] = r
                    except: 
                        for s in batch: cache[s] = s

                    proc += len(batch)
                    elapsed = time.time() - start_t
                    if elapsed > 0:
                        spd = proc/elapsed
                        self.lbl_eta.configure(text=f"Speed: {spd:.1f}/s")
                    
                    self.progress.set((i/len(todo)) if len(todo)>0 else 1)
                    if i>0 and (i//bs)%10==0:
                        with open(cache_file, 'w', encoding='utf-8') as f: json.dump(cache, f)

                with open(cache_file, 'w', encoding='utf-8') as f: json.dump(cache, f)

                final_texts = []
                statuses = []
                failed_indices = []
                
                for idx, row in df.iterrows():
                    if skip_existing and row[col] != "":
                        final_texts.append(row[col])
                        statuses.append("SKIPPED")
                        continue

                    masked = row['Masked']
                    orig_full = self.processor.unmask_text(masked)
                    trans_masked = cache.get(masked, masked)
                    final = self.processor.unmask_text(trans_masked)
                    if auto_punct:
                        final = self.processor.fix_punctuation(final)

                    status = "OK"
                    if safety:
                        ok, _ = self.safety_check(orig_full, final)
                        if not ok:
                            if use_online:
                                try:
                                    fb = GoogleTranslator(source=src, target=tgt).translate(orig_full)
                                    if self.safety_check(orig_full, fb)[0]: final = fb; status = "ONLINE"
                                    else: status = "FAIL"
                                except: status = "FAIL"
                            else: status = "FAIL"
                            if status == "FAIL": 
                                final = orig_full
                                status = "SAFETY_FAIL"
                                failed_indices.append({'idx': idx, 'orig': orig_full, 'trans': final})

                    if len_check and status in ["OK", "ONLINE"]:
                        if len(final) > len(orig_full) * 1.3: status += "_LEN"

                    final_texts.append(final)
                    statuses.append(status)
                    total_trans += 1

                df[col] = final_texts
                if debug_col: df['QA_Status'] = statuses

                if self.glossary_dict:
                    gs = dict(sorted(self.glossary_dict.items(), key=lambda x: len(str(x[0])), reverse=True))
                    df[col] = df[col].replace(gs, regex=True)

                if self.processor.regex_rules:
                    df[col] = df[col].apply(self.processor.apply_regex_rules)

                df.drop(columns=['Masked'], inplace=True, errors='ignore')
                out = fpath.rsplit('.', 1)[0] + f"_{tgt}_FINAL.csv"
                # FIXED SAVING
                df.to_csv(out, sep=';', index=False, encoding='utf-8-sig', quoting=csv.QUOTE_MINIMAL)
                self.log(f"Salvato: {os.path.basename(out)}")
                if os.path.exists(cache_file): os.remove(cache_file)

            if not self.stop_event.is_set():
                msg = f"Finito.\nTradotte: {total_trans}\nSaltate: {total_skip}"
                self.log(msg)
                messagebox.showinfo("Report", msg)

        except Exception as e:
            self.log(f"Err: {e}")
        finally:
            self.is_running = False
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")

    # --- UTILS ---
    def log(self, msg):
        self.txt_log.configure(state="normal")
        self.txt_log.insert(tk.END, f"> {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state="disabled")
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now()}] {msg}\n")
        except:
            pass

    def safety_check(self, o, t):
        v1 = self.processor.get_variables(o)
        v2 = self.processor.get_variables(t)
        return set(v1)==set(v2), t

    def load_files(self):
        p = filedialog.askopenfilenames(filetypes=[("Data", "*.csv *.xlsx")])
        if p: 
            self.files_queue = list(p)
            self.lbl_file_count.configure(text=f"{len(p)} file", text_color="#2CC985")
            try:
                df = pd.read_csv(p[0], sep=None, engine='python', nrows=2, dtype=str, keep_default_na=False)
                df.columns=df.columns.str.strip()
                self.combo_col.configure(values=list(df.columns))
                self.combo_col.set(next((c for c in df.columns if "Text" in c or "English" in c), df.columns[0]))
            except: pass

    def load_glossary(self, path=None):
        if not path: path = filedialog.askopenfilename()
        if path: 
            try:
                df = pd.read_csv(path, sep=None, engine='python', header=None)
                self.glossary_dict = dict(zip(df[0].astype(str), df[1].astype(str)))
                self.lbl_gloss_status.configure(text=f"{len(self.glossary_dict)} termini", text_color="#2CC985")
            except: pass

    def save_regex_from_ui(self):
        raw = self.txt_regex.get("0.0", "end").strip().split('\n')
        self.processor.regex_rules = []
        for l in raw: 
            if "->" in l and not l.startswith("#"):
                p = l.split("->")
                self.processor.regex_rules.append((p[0].strip(), p[1].strip()))
        self.log("Regex aggiornate.")

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.configure(text="RIPRENDI")
        else:
            self.pause_event.set()
            self.btn_pause.configure(text="PAUSA")

    def stop_process(self):
        if messagebox.askyesno("Stop", "?"):
            self.stop_event.set()
            self.pause_event.set()
    
    def load_profiles(self):
        d_def = {"Default": {"src": "Inglese", "tgt": "Italiano", "fp16": True, "patterns": [d.copy() for d in DEFAULT_PATTERNS], "regex": []}}
        if os.path.exists(PROFILES_FILE):
            try:
                with open(PROFILES_FILE, 'r') as f: self.profiles = json.load(f)
            except: self.profiles = d_def
        else: self.profiles = d_def
        self.combo_profiles.configure(values=list(self.profiles.keys()))
        self.combo_profiles.set("Default")
        self.apply_profile("Default")

    def change_profile(self, c):
        self.save_current_profile()
        self.current_profile = c
        self.apply_profile(c)
    
    def apply_profile(self, n):
        d = self.profiles.get(n, {})
        if "src" in d: self.combo_src.set(d["src"])
        if "tgt" in d: self.combo_tgt.set(d["tgt"])
        if "fp16" in d and torch.cuda.is_available():
            self.chk_fp16.select() if d["fp16"] else self.chk_fp16.deselect()
        self.protection_config = d.get("patterns", [x.copy() for x in DEFAULT_PATTERNS])
        self.refresh_vars_list()
        self.txt_regex.delete("0.0", "end")
        for r in d.get("regex", []): self.txt_regex.insert("end", f"{r[0]} -> {r[1]}\n")
        self.save_regex_from_ui()

    def save_current_profile(self):
        self.save_regex_from_ui()
        self.profiles[self.current_profile] = {
            "src": self.combo_src.get(),
            "tgt": self.combo_tgt.get(),
            "fp16": bool(self.chk_fp16.get()),
            "patterns": self.protection_config,
            "regex": self.processor.regex_rules
        }
        with open(PROFILES_FILE, 'w') as f: json.dump(self.profiles, f, indent=4)

    def add_profile(self):
        d = ctk.CTkInputDialog(text="Nome:", title="Nuovo")
        n = d.get_input()
        if n and n not in self.profiles:
            self.profiles[n] = self.profiles["Default"].copy()
            self.combo_profiles.configure(values=list(self.profiles.keys()))
            self.combo_profiles.set(n)
            self.change_profile(n)

    def delete_profile(self):
        n = self.combo_profiles.get()
        if n != "Default" and messagebox.askyesno("Del", "?"):
            del self.profiles[n]
            self.combo_profiles.configure(values=list(self.profiles.keys()))
            self.combo_profiles.set("Default")
            self.change_profile("Default")

    def on_closing(self):
        self.save_current_profile()
        self.destroy()

    def reset_settings(self): 
        if os.path.exists(PROFILES_FILE): os.remove(PROFILES_FILE)
        self.log("Reset done.")

if __name__ == "__main__":
    try:
        app = TranslatorApp()
        app.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("Error. Enter...")