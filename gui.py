import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import threading
import asyncio
import os
from scraper import MedofastScraper

SETTINGS_FILE = "settings.json"

class MedofastGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Medofast Scraper Pro")
        self.root.geometry("700x650")

        self.scraper = None
        self.loop = None
        self.scraper_thread = None
        self.login_confirmed_event = None

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # URL Input
        ttk.Label(main_frame, text="Start URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(main_frame, textvariable=self.url_var, width=60)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky=tk.W, pady=5)

        # Output Path
        ttk.Label(main_frame, text="Output Path:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_var = tk.StringVar(value="questions.json")
        self.output_entry = ttk.Entry(main_frame, textvariable=self.output_var, width=50)
        self.output_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_output).grid(row=1, column=2, sticky=tk.W, padx=5)

        # Delays / Speed Control
        delay_frame = ttk.LabelFrame(main_frame, text="Speed & Delay Settings (seconds)", padding="10")
        delay_frame.grid(row=2, column=0, columnspan=3, fill=tk.X, pady=10)

        # Click Delay
        ttk.Label(delay_frame, text="Click Delay:").grid(row=0, column=0, sticky=tk.W)
        self.click_delay_var = tk.DoubleVar(value=1.0)
        self.click_delay_scale = ttk.Scale(delay_frame, from_=0.1, to=10.0, variable=self.click_delay_var, orient=tk.HORIZONTAL, length=300, command=lambda x: self.update_delay_labels())
        self.click_delay_scale.grid(row=0, column=1, padx=10)
        self.click_delay_label = ttk.Label(delay_frame, text="1.0s")
        self.click_delay_label.grid(row=0, column=2)

        # Question Load Delay
        ttk.Label(delay_frame, text="Question Load Delay:").grid(row=1, column=0, sticky=tk.W)
        self.q_load_delay_var = tk.DoubleVar(value=2.0)
        self.q_load_delay_scale = ttk.Scale(delay_frame, from_=0.5, to=15.0, variable=self.q_load_delay_var, orient=tk.HORIZONTAL, length=300, command=lambda x: self.update_delay_labels())
        self.q_load_delay_scale.grid(row=1, column=1, padx=10)
        self.q_load_delay_label = ttk.Label(delay_frame, text="2.0s")
        self.q_load_delay_label.grid(row=1, column=2)

        # Answer Load Delay
        ttk.Label(delay_frame, text="Answer Load Delay:").grid(row=2, column=0, sticky=tk.W)
        self.a_load_delay_var = tk.DoubleVar(value=1.0)
        self.a_load_delay_scale = ttk.Scale(delay_frame, from_=0.1, to=10.0, variable=self.a_load_delay_var, orient=tk.HORIZONTAL, length=300, command=lambda x: self.update_delay_labels())
        self.a_load_delay_scale.grid(row=2, column=1, padx=10)
        self.a_load_delay_label = ttk.Label(delay_frame, text="1.0s")
        self.a_load_delay_label.grid(row=2, column=2)

        # Options
        options_frame = ttk.Frame(main_frame)
        options_frame.grid(row=3, column=0, columnspan=3, fill=tk.X, pady=5)

        self.skip_explanation_var = tk.BooleanVar(value=False)
        self.skip_explanation_check = ttk.Checkbutton(options_frame, text="Skip Explanatory Answers (Faster)", variable=self.skip_explanation_var, command=self.update_skip_explanation)
        self.skip_explanation_check.pack(side=tk.LEFT)

        # Controls
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=4, column=0, columnspan=3, pady=10)

        self.start_btn = ttk.Button(control_frame, text="Start Scraper", command=self.start_scraper)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.confirm_login_btn = ttk.Button(control_frame, text="Confirm Login", command=self.confirm_login, state=tk.DISABLED)
        self.confirm_login_btn.pack(side=tk.LEFT, padx=5)

        self.pause_btn = ttk.Button(control_frame, text="Pause", command=self.toggle_pause, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="Stop", command=self.stop_scraper, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # Log Area
        ttk.Label(main_frame, text="Logs:").grid(row=5, column=0, sticky=tk.W, pady=(10, 0))
        self.log_text = tk.Text(main_frame, height=15, width=80, state=tk.DISABLED)
        self.log_text.grid(row=6, column=0, columnspan=3, sticky=tk.NSEW, pady=5)

        scrollbar = ttk.Scrollbar(main_frame, command=self.log_text.yview)
        scrollbar.grid(row=6, column=3, sticky=tk.NS)
        self.log_text.config(yscrollcommand=scrollbar.set)

        main_frame.rowconfigure(6, weight=1)
        main_frame.columnconfigure(1, weight=1)

    def update_skip_explanation(self):
        if self.scraper:
            self.scraper.skip_explanation = self.skip_explanation_var.get()

    def update_delay_labels(self):
        self.click_delay_label.config(text=f"{self.click_delay_var.get():.1f}s")
        self.q_load_delay_label.config(text=f"{self.q_load_delay_var.get():.1f}s")
        self.a_load_delay_label.config(text=f"{self.a_load_delay_var.get():.1f}s")

        # Update scraper settings on the fly if running
        if self.scraper:
            self.scraper.click_delay = self.click_delay_var.get()
            self.scraper.question_load_delay = self.q_load_delay_var.get()
            self.scraper.answer_load_delay = self.a_load_delay_var.get()

    def browse_output(self):
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if filename:
            self.output_var.set(filename)

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    self.url_var.set(settings.get("url", ""))
                    self.output_var.set(settings.get("output", "questions.json"))
                    self.click_delay_var.set(settings.get("click_delay", 1.0))
                    self.q_load_delay_var.set(settings.get("q_load_delay", 2.0))
                    self.a_load_delay_var.set(settings.get("a_load_delay", 1.0))
                    self.skip_explanation_var.set(settings.get("skip_explanation", False))
                    self.update_delay_labels()
            except Exception as e:
                print(f"Failed to load settings: {e}")

    def save_settings(self):
        settings = {
            "url": self.url_var.get(),
            "output": self.output_var.get(),
            "click_delay": self.click_delay_var.get(),
            "q_load_delay": self.q_load_delay_var.get(),
            "a_load_delay": self.a_load_delay_var.get(),
            "skip_explanation": self.skip_explanation_var.get()
        }
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)

    def start_scraper(self):
        if not self.url_var.get():
            messagebox.showerror("Error", "Please enter a start URL.")
            return

        self.save_settings()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.NORMAL)
        self.confirm_login_btn.config(state=tk.NORMAL)

        self.scraper = MedofastScraper(logger_callback=lambda m: self.root.after(0, self.log, m))
        self.scraper.url = self.url_var.get()
        self.scraper.output_path = self.output_var.get()
        self.scraper.click_delay = self.click_delay_var.get()
        self.scraper.question_load_delay = self.q_load_delay_var.get()
        self.scraper.answer_load_delay = self.a_load_delay_var.get()
        self.scraper.skip_explanation = self.skip_explanation_var.get()

        self.scraper_thread = threading.Thread(target=self.run_async_scraper, daemon=True)
        self.scraper_thread.start()

    def run_async_scraper(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.login_confirmed_event = asyncio.Event()
        try:
            self.loop.run_until_complete(self.scraper.run(self.login_confirmed_event))
        except Exception as e:
            self.root.after(0, self.log, f"CRITICAL ERROR: {str(e)}")
        finally:
            self.root.after(0, self.on_scraper_finished)

    def confirm_login(self):
        if self.loop and self.login_confirmed_event:
            self.loop.call_soon_threadsafe(self.login_confirmed_event.set)
            self.confirm_login_btn.config(state=tk.DISABLED)
            self.log("Login confirmed by user.")

    def toggle_pause(self):
        if not self.scraper:
            return

        if self.scraper.is_paused:
            self.scraper.resume()
            self.pause_btn.config(text="Pause")
            self.log("Resumed.")
        else:
            self.scraper.pause()
            self.pause_btn.config(text="Resume")
            self.log("Paused.")

    def stop_scraper(self):
        if self.scraper:
            self.scraper.stop()
            self.log("Stopping scraper...")
            self.stop_btn.config(state=tk.DISABLED)

    def on_scraper_finished(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.DISABLED, text="Pause")
        self.confirm_login_btn.config(state=tk.DISABLED)
        self.log("Scraper execution finished.")

if __name__ == "__main__":
    root = tk.Tk()
    gui = MedofastGUI(root)
    root.mainloop()
