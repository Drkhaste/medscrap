import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import csv
import threading
import asyncio
import os
from pathlib import Path
from scraper import MedofastScraper

SETTINGS_FILE = "settings.json"

class MedofastGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Medofast Scraper Pro")
        self.root.geometry("900x800")
        self.scraper = None
        self.loop = None
        self.scraper_thread = None
        self.login_confirmed_event = None
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.scraper_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.scraper_tab, text="Scraper")
        self.setup_scraper_tab()
        self.exporter_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.exporter_tab, text="Export JSON to CSV")
        self.setup_exporter_tab()

    def setup_scraper_tab(self):
        main = ttk.Frame(self.scraper_tab, padding="10")
        main.pack(fill=tk.BOTH, expand=True)
        manage = ttk.LabelFrame(main, text="Scrape Management", padding="10")
        manage.grid(row=0, column=0, columnspan=3, sticky=tk.EW, pady=5)
        self.is_new_scrape_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(manage, text="New Scrape", variable=self.is_new_scrape_var, command=self.toggle_scrape_mode).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(manage, text="Project Name:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.project_name_var = tk.StringVar(value="my_scrape")
        self.project_entry = ttk.Entry(manage, textvariable=self.project_name_var, width=40)
        self.project_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.browse_proj_btn = ttk.Button(manage, text="Browse Existing", command=self.browse_existing_project, state=tk.DISABLED)
        self.browse_proj_btn.grid(row=1, column=2, padx=5)

        ttk.Label(main, text="Start URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.url_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.url_var, width=60).grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=5)

        delay = ttk.LabelFrame(main, text="Delays (seconds)", padding="10")
        delay.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=10)
        self.click_delay_var = tk.DoubleVar(value=2.0)
        ttk.Scale(delay, from_=0.1, to=10.0, variable=self.click_delay_var, orient=tk.HORIZONTAL, length=300, command=lambda x: self.update_delay_labels()).grid(row=0, column=1)
        self.click_delay_label = ttk.Label(delay, text="2.0s")
        self.click_delay_label.grid(row=0, column=2)
        self.q_load_delay_var = tk.DoubleVar(value=3.0)
        ttk.Scale(delay, from_=0.5, to=15.0, variable=self.q_load_delay_var, orient=tk.HORIZONTAL, length=300, command=lambda x: self.update_delay_labels()).grid(row=1, column=1)
        self.q_load_label = ttk.Label(delay, text="3.0s")
        self.q_load_label.grid(row=1, column=2)
        self.a_load_delay_var = tk.DoubleVar(value=2.0)
        ttk.Scale(delay, from_=0.1, to=10.0, variable=self.a_load_delay_var, orient=tk.HORIZONTAL, length=300, command=lambda x: self.update_delay_labels()).grid(row=2, column=1)
        self.a_load_label = ttk.Label(delay, text="2.0s")
        self.a_load_label.grid(row=2, column=2)

        opts = ttk.LabelFrame(main, text="Options", padding="10")
        opts.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=5)
        self.skip_explanation_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Skip Explanation Wait", variable=self.skip_explanation_var, command=self.update_scraper_params).grid(row=0, column=0, sticky=tk.W)
        self.save_screenshots_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Save Screenshots", variable=self.save_screenshots_var, command=self.update_scraper_params).grid(row=0, column=1, sticky=tk.W)
        self.save_html_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Save HTML", variable=self.save_html_var, command=self.update_scraper_params).grid(row=0, column=2, sticky=tk.W)

        ctrl = ttk.Frame(main)
        ctrl.grid(row=4, column=0, columnspan=3, pady=10)
        self.start_btn = ttk.Button(ctrl, text="Start", command=self.start_scraper)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.confirm_login_btn = ttk.Button(ctrl, text="Confirm Login", command=self.confirm_login, state=tk.DISABLED)
        self.confirm_login_btn.pack(side=tk.LEFT, padx=5)
        self.pause_btn = ttk.Button(ctrl, text="Pause", command=self.toggle_pause, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(ctrl, text="Stop", command=self.stop_scraper, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.log_text = tk.Text(main, height=15, width=90, state=tk.DISABLED)
        self.log_text.grid(row=6, column=0, columnspan=3, sticky=tk.NSEW, pady=5)
        scrollbar = ttk.Scrollbar(main, command=self.log_text.yview)
        scrollbar.grid(row=6, column=3, sticky=tk.NS)
        self.log_text.config(yscrollcommand=scrollbar.set)
        main.rowconfigure(6, weight=1); main.columnconfigure(1, weight=1)

    def toggle_scrape_mode(self):
        state = tk.DISABLED if self.is_new_scrape_var.get() else tk.NORMAL
        self.browse_proj_btn.config(state=state)
        self.project_entry.config(state=tk.NORMAL if self.is_new_scrape_var.get() else tk.DISABLED)

    def browse_existing_project(self):
        folder = filedialog.askdirectory(initialdir="scrapes")
        if folder: self.project_name_var.set(os.path.basename(folder))

    def setup_exporter_tab(self):
        frame = ttk.Frame(self.exporter_tab, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Select JSON file to convert to CSV:").pack(pady=5)
        self.json_source_var = tk.StringVar()
        entry_f = ttk.Frame(frame); entry_f.pack(fill=tk.X)
        ttk.Entry(entry_f, textvariable=self.json_source_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(entry_f, text="Browse", command=self.browse_json_source).pack(side=tk.LEFT)
        ttk.Button(frame, text="Convert to CSV", command=self.run_manual_export).pack(pady=20)

    def browse_json_source(self):
        f = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if f: self.json_source_var.set(f)

    def run_manual_export(self):
        json_path = self.json_source_var.get()
        if not json_path or not os.path.exists(json_path): return
        csv_path = json_path.replace(".json", ".csv")
        try:
            with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
            if not data: return
            with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Question Number", "Exam", "Date", "Lesson", "Subject", "Difficulty", "Success Rate", "Position", "Question Text", "Option 1", "Option 2", "Option 3", "Option 4", "Correct Options", "Explanation"])
                for q in data:
                    meta, opts = q.get("metadata", {}), q.get("options", [])
                    opt_texts = ["", "", "", ""]
                    for o in opts:
                        idx = o.get("number", 1) - 1
                        if 0 <= idx < 4: opt_texts[idx] = o.get("text", "")
                    writer.writerow([q.get("question_number", ""), meta.get("آزمون", ""), meta.get("تاریخ", ""), meta.get("درس", ""), meta.get("موضوع", ""), meta.get("سطح دشواری", ""), meta.get("درصد پاسخ صحیح", ""), meta.get("موقعیت سوال", ""), q.get("question_text", ""), opt_texts[0], opt_texts[1], opt_texts[2], opt_texts[3], ", ".join(map(str, q.get("correct_options", []))), q.get("answer_explanation", "")])
            messagebox.showinfo("Success", "Exported to CSV successfully.")
        except Exception as e: messagebox.showerror("Error", str(e))

    def update_scraper_params(self):
        if self.scraper:
            self.scraper.skip_explanation = self.skip_explanation_var.get()
            self.scraper.save_screenshots = self.save_screenshots_var.get()
            self.scraper.save_html = self.save_html_var.get()

    def update_delay_labels(self):
        self.click_delay_label.config(text=f"{self.click_delay_var.get():.1f}s")
        self.q_load_label.config(text=f"{self.q_load_delay_var.get():.1f}s")
        self.a_load_label.config(text=f"{self.a_load_delay_var.get():.1f}s")
        if self.scraper:
            self.scraper.click_delay = self.click_delay_var.get()
            self.scraper.question_load_delay = self.q_load_delay_var.get()
            self.scraper.answer_load_delay = self.a_load_delay_var.get()

    def start_scraper(self):
        if not self.url_var.get() or not self.project_name_var.get(): return
        self.save_settings()
        base_dir = Path("scrapes") / self.project_name_var.get()
        base_dir.mkdir(parents=True, exist_ok=True)
        self.scraper = MedofastScraper(logger_callback=lambda m: self.root.after(0, self.log, m))
        self.scraper.url = self.url_var.get()
        self.scraper.json_path = base_dir / "questions.json"
        self.scraper.csv_path = base_dir / "questions.csv"
        self.scraper.images_dir = base_dir / "images"
        self.scraper.screenshots_dir = base_dir / "screenshots"
        self.scraper.html_dir = base_dir / "html"
        self.update_scraper_params(); self.update_delay_labels()
        self.start_btn.config(state=tk.DISABLED); self.stop_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.NORMAL); self.confirm_login_btn.config(state=tk.NORMAL)
        self.scraper_thread = threading.Thread(target=self.run_async_scraper, daemon=True); self.scraper_thread.start()

    def run_async_scraper(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.login_confirmed_event = asyncio.Event()
        try: self.loop.run_until_complete(self.scraper.run(self.login_confirmed_event))
        except Exception as e: self.root.after(0, self.log, f"CRITICAL ERROR: {str(e)}")
        finally: self.root.after(0, self.on_scraper_finished)

    def confirm_login(self):
        if self.loop and self.login_confirmed_event:
            self.loop.call_soon_threadsafe(self.login_confirmed_event.set)
            self.confirm_login_btn.config(state=tk.DISABLED)

    def toggle_pause(self):
        if not self.scraper: return
        self.scraper.pause() if not self.scraper.is_paused else self.scraper.resume()
        self.pause_btn.config(text="Resume" if self.scraper.is_paused else "Pause")
        self.log("Paused." if self.scraper.is_paused else "Resumed.")

    def stop_scraper(self):
        if self.scraper: self.scraper.stop(); self.stop_btn.config(state=tk.DISABLED)

    def on_scraper_finished(self):
        self.start_btn.config(state=tk.NORMAL); self.stop_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.DISABLED, text="Pause"); self.confirm_login_btn.config(state=tk.DISABLED)
        self.log("Scraper finished.")

    def log(self, m):
        self.log_text.config(state=tk.NORMAL); self.log_text.insert(tk.END, m + "\n")
        self.log_text.see(tk.END); self.log_text.config(state=tk.DISABLED)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    s = json.load(f); self.url_var.set(s.get("url", ""))
                    self.project_name_var.set(s.get("project_name", "my_scrape"))
                    self.click_delay_var.set(s.get("click_delay", 2.0))
                    self.q_load_delay_var.set(s.get("q_load_delay", 3.0))
                    self.a_load_delay_var.set(s.get("a_load_delay", 2.0))
                    self.skip_explanation_var.set(s.get("skip_explanation", False))
                    self.save_screenshots_var.set(s.get("save_screenshots", False))
                    self.save_html_var.set(s.get("save_html", False)); self.update_delay_labels()
            except: pass

    def save_settings(self):
        s = {"url": self.url_var.get(), "project_name": self.project_name_var.get(), "click_delay": self.click_delay_var.get(), "q_load_delay": self.q_load_delay_var.get(), "a_load_delay": self.a_load_delay_var.get(), "skip_explanation": self.skip_explanation_var.get(), "save_screenshots": self.save_screenshots_var.get(), "save_html": self.save_html_var.get()}
        with open(SETTINGS_FILE, 'w') as f: json.dump(s, f)

if __name__ == "__main__":
    root = tk.Tk(); MedofastGUI(root); root.mainloop()
