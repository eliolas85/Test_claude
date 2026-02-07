#!/usr/bin/env python3
"""
YouTube Video Downloader
========================
Applicazione desktop per scaricare uno o piu video YouTube contemporaneamente
e visualizzarli offline.

Dipendenze: yt-dlp, tkinter (incluso in Python standard)
Requisiti di sistema: ffmpeg (per merge audio+video), un player video (mpv/vlc/default OS)
"""

import json
import os
import platform
import queue
import subprocess
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import yt_dlp
except ImportError:
    print("yt-dlp non trovato. Installalo con: pip install yt-dlp")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
APP_TITLE = "YouTube Video Downloader"
DEFAULT_DOWNLOAD_DIR = str(Path.home() / "YouTube_Downloads")
MAX_CONCURRENT_DOWNLOADS = 4
QUALITY_OPTIONS = {
    "Migliore (video+audio)": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
    "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
    "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
    "Solo audio (mp3)": "bestaudio/best",
}
HISTORY_FILE = "download_history.json"


# ---------------------------------------------------------------------------
# Modello dati per un singolo download
# ---------------------------------------------------------------------------
class DownloadTask:
    """Rappresenta un singolo task di download."""

    PENDING = "In coda"
    DOWNLOADING = "Download..."
    DONE = "Completato"
    ERROR = "Errore"
    CANCELLED = "Annullato"

    def __init__(self, url: str, quality: str, output_dir: str):
        self.url = url
        self.quality = quality
        self.output_dir = output_dir
        self.status = self.PENDING
        self.progress = 0.0
        self.speed = ""
        self.eta = ""
        self.title = url  # verra aggiornato dopo la risoluzione
        self.filename = ""
        self.filepath = ""
        self.error_msg = ""
        self.cancelled = False


# ---------------------------------------------------------------------------
# Motore di download
# ---------------------------------------------------------------------------
class DownloadEngine:
    """Gestisce i download concorrenti tramite yt-dlp."""

    def __init__(self, max_workers: int = MAX_CONCURRENT_DOWNLOADS):
        self.pool = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: list[DownloadTask] = []
        self.callbacks: dict[str, list] = {
            "progress": [],
            "complete": [],
            "error": [],
            "info": [],
        }

    def on(self, event: str, callback):
        self.callbacks.setdefault(event, []).append(callback)

    def _emit(self, event: str, task: DownloadTask, **kwargs):
        for cb in self.callbacks.get(event, []):
            cb(task, **kwargs)

    def add(self, task: DownloadTask):
        self.tasks.append(task)
        self.pool.submit(self._run, task)

    def _make_progress_hook(self, task: DownloadTask):
        def hook(d):
            if task.cancelled:
                raise Exception("Download annullato dall'utente")
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                task.progress = (downloaded / total * 100) if total else 0
                task.speed = d.get("_speed_str", "")
                task.eta = d.get("_eta_str", "")
                task.status = DownloadTask.DOWNLOADING
                self._emit("progress", task)
            elif d["status"] == "finished":
                task.progress = 100
                task.status = DownloadTask.DOWNLOADING  # post-processing
                self._emit("progress", task)

        return hook

    def _run(self, task: DownloadTask):
        audio_only = task.quality == "Solo audio (mp3)"
        fmt = QUALITY_OPTIONS.get(task.quality, QUALITY_OPTIONS["Migliore (video+audio)"])

        outtmpl = os.path.join(task.output_dir, "%(title)s.%(ext)s")

        ydl_opts: dict = {
            "format": fmt,
            "outtmpl": outtmpl,
            "progress_hooks": [self._make_progress_hook(task)],
            "noplaylist": False,  # supporta anche playlist
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4" if not audio_only else None,
        }

        if audio_only:
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]

        try:
            task.status = DownloadTask.DOWNLOADING
            self._emit("progress", task)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(task.url, download=False)
                if info:
                    task.title = info.get("title", task.url)
                    self._emit("info", task)

                if task.cancelled:
                    task.status = DownloadTask.CANCELLED
                    self._emit("error", task)
                    return

                ydl.download([task.url])

                # Determina il filepath effettivo
                if info:
                    ext = "mp3" if audio_only else "mp4"
                    task.filename = f"{info.get('title', 'video')}.{ext}"
                    task.filepath = os.path.join(task.output_dir, task.filename)

            task.status = DownloadTask.DONE
            task.progress = 100
            self._emit("complete", task)

        except Exception as e:
            if task.cancelled:
                task.status = DownloadTask.CANCELLED
            else:
                task.status = DownloadTask.ERROR
                task.error_msg = str(e)
            self._emit("error", task)

    def cancel_task(self, task: DownloadTask):
        task.cancelled = True

    def shutdown(self):
        self.pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Cronologia download
# ---------------------------------------------------------------------------
class DownloadHistory:
    """Salva e carica la cronologia dei download per la visione offline."""

    def __init__(self, base_dir: str):
        self.path = os.path.join(base_dir, HISTORY_FILE)

    def load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, records: list[dict]):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def add(self, title: str, filepath: str, url: str):
        records = self.load()
        records.insert(
            0,
            {
                "title": title,
                "filepath": filepath,
                "url": url,
                "date": datetime.now().isoformat(),
            },
        )
        self.save(records)

    def remove(self, filepath: str):
        records = self.load()
        records = [r for r in records if r["filepath"] != filepath]
        self.save(records)


# ---------------------------------------------------------------------------
# Player video
# ---------------------------------------------------------------------------
def play_video(filepath: str):
    """Apre il file video con il player predefinito del sistema operativo."""
    if not os.path.exists(filepath):
        messagebox.showerror("Errore", f"File non trovato:\n{filepath}")
        return

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", filepath])
        elif system == "Windows":
            os.startfile(filepath)
        else:
            subprocess.Popen(["xdg-open", filepath])
    except Exception as e:
        messagebox.showerror("Errore", f"Impossibile aprire il video:\n{e}")


# ---------------------------------------------------------------------------
# GUI principale
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x680")
        self.minsize(750, 550)

        # Stile
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Header.TLabel", font=("Helvetica", 14, "bold"))
        style.configure("Status.TLabel", font=("Helvetica", 9))

        self.download_dir = tk.StringVar(value=DEFAULT_DOWNLOAD_DIR)
        self.quality_var = tk.StringVar(value="Migliore (video+audio)")

        self.engine = DownloadEngine()
        self.engine.on("progress", self._on_progress)
        self.engine.on("complete", self._on_complete)
        self.engine.on("error", self._on_error)
        self.engine.on("info", self._on_info)

        self.history = DownloadHistory(DEFAULT_DOWNLOAD_DIR)
        self.ui_queue = queue.Queue()

        self._build_ui()
        self._poll_queue()

    # ----- Layout -----
    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Tab 1: Download
        self.tab_download = ttk.Frame(notebook)
        notebook.add(self.tab_download, text="  Download  ")
        self._build_download_tab()

        # Tab 2: Libreria / Visione offline
        self.tab_library = ttk.Frame(notebook)
        notebook.add(self.tab_library, text="  Libreria Offline  ")
        self._build_library_tab()

        # Barra di stato
        self.status_var = tk.StringVar(value="Pronto")
        status_bar = ttk.Label(
            self, textvariable=self.status_var, style="Status.TLabel", relief=tk.SUNKEN, anchor=tk.W
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 4))

    def _build_download_tab(self):
        parent = self.tab_download

        # --- Header ---
        header = ttk.Label(parent, text="Scarica video da YouTube", style="Header.TLabel")
        header.pack(pady=(12, 4))

        # --- URL input ---
        url_frame = ttk.LabelFrame(parent, text="URL dei video (uno per riga)")
        url_frame.pack(fill=tk.X, padx=12, pady=6)

        self.url_text = tk.Text(url_frame, height=5, wrap=tk.WORD, font=("Consolas", 10))
        self.url_text.pack(fill=tk.X, padx=8, pady=8)
        self.url_text.insert("1.0", "")

        # --- Opzioni ---
        opts_frame = ttk.Frame(parent)
        opts_frame.pack(fill=tk.X, padx=12, pady=4)

        ttk.Label(opts_frame, text="Qualita:").pack(side=tk.LEFT, padx=(0, 4))
        quality_combo = ttk.Combobox(
            opts_frame,
            textvariable=self.quality_var,
            values=list(QUALITY_OPTIONS.keys()),
            state="readonly",
            width=30,
        )
        quality_combo.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(opts_frame, text="Cartella:").pack(side=tk.LEFT, padx=(0, 4))
        dir_entry = ttk.Entry(opts_frame, textvariable=self.download_dir, width=30)
        dir_entry.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(opts_frame, text="Sfoglia...", command=self._browse_dir).pack(side=tk.LEFT)

        # --- Pulsanti azione ---
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=12, pady=8)

        self.btn_download = ttk.Button(
            btn_frame, text="Avvia Download", command=self._start_downloads
        )
        self.btn_download.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_clear = ttk.Button(
            btn_frame, text="Pulisci lista", command=self._clear_tasks
        )
        self.btn_clear.pack(side=tk.LEFT)

        # --- Tabella download ---
        columns = ("title", "status", "progress", "speed", "eta")
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=10)
        self.tree.heading("title", text="Titolo")
        self.tree.heading("status", text="Stato")
        self.tree.heading("progress", text="Progresso")
        self.tree.heading("speed", text="Velocita")
        self.tree.heading("eta", text="ETA")

        self.tree.column("title", width=340, minwidth=200)
        self.tree.column("status", width=100, minwidth=80)
        self.tree.column("progress", width=100, minwidth=60)
        self.tree.column("speed", width=100, minwidth=60)
        self.tree.column("eta", width=80, minwidth=50)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mappa task -> tree item
        self.task_items: dict[int, str] = {}

        # Context menu
        self.tree_menu = tk.Menu(self, tearoff=0)
        self.tree_menu.add_command(label="Annulla download", command=self._cancel_selected)
        self.tree.bind("<Button-3>", self._show_tree_menu)

    def _build_library_tab(self):
        parent = self.tab_library

        header = ttk.Label(parent, text="Libreria Video Offline", style="Header.TLabel")
        header.pack(pady=(12, 4))

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=12, pady=6)

        ttk.Button(btn_frame, text="Aggiorna lista", command=self._refresh_library).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(btn_frame, text="Apri cartella", command=self._open_download_dir).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(
            btn_frame, text="Riproduci selezionato", command=self._play_selected
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_frame, text="Elimina selezionato", command=self._delete_selected
        ).pack(side=tk.LEFT)

        lib_columns = ("title", "date", "filepath")
        lib_frame = ttk.Frame(parent)
        lib_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        self.lib_tree = ttk.Treeview(lib_frame, columns=lib_columns, show="headings", height=14)
        self.lib_tree.heading("title", text="Titolo")
        self.lib_tree.heading("date", text="Data download")
        self.lib_tree.heading("filepath", text="Percorso file")

        self.lib_tree.column("title", width=320, minwidth=200)
        self.lib_tree.column("date", width=160, minwidth=120)
        self.lib_tree.column("filepath", width=350, minwidth=200)

        lib_scroll = ttk.Scrollbar(lib_frame, orient=tk.VERTICAL, command=self.lib_tree.yview)
        self.lib_tree.configure(yscrollcommand=lib_scroll.set)
        self.lib_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lib_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Doppio click per riprodurre
        self.lib_tree.bind("<Double-1>", lambda e: self._play_selected())

        self._refresh_library()

    # ----- Azioni -----
    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.download_dir.get())
        if d:
            self.download_dir.set(d)
            self.history = DownloadHistory(d)

    def _start_downloads(self):
        raw = self.url_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("Attenzione", "Inserisci almeno un URL.")
            return

        urls = [u.strip() for u in raw.splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning("Attenzione", "Nessun URL valido trovato.")
            return

        out_dir = self.download_dir.get()
        os.makedirs(out_dir, exist_ok=True)

        quality = self.quality_var.get()

        for url in urls:
            task = DownloadTask(url, quality, out_dir)
            item_id = self.tree.insert(
                "",
                tk.END,
                values=(task.title, task.status, "0%", "", ""),
            )
            self.task_items[id(task)] = item_id
            self.engine.add(task)

        self.status_var.set(f"Avviati {len(urls)} download...")

    def _clear_tasks(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.task_items.clear()

    def _cancel_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        # Trova il task corrispondente
        for task in self.engine.tasks:
            item_id = self.task_items.get(id(task))
            if item_id in sel and task.status == DownloadTask.DOWNLOADING:
                self.engine.cancel_task(task)

    def _show_tree_menu(self, event):
        try:
            self.tree.selection_set(self.tree.identify_row(event.y))
            self.tree_menu.post(event.x_root, event.y_root)
        except tk.TclError:
            pass

    # ----- Libreria -----
    def _refresh_library(self):
        for item in self.lib_tree.get_children():
            self.lib_tree.delete(item)

        records = self.history.load()
        for r in records:
            exists = os.path.exists(r.get("filepath", ""))
            date_str = r.get("date", "")[:19].replace("T", " ")
            title = r.get("title", "Sconosciuto")
            if not exists:
                title += " [file mancante]"
            self.lib_tree.insert("", tk.END, values=(title, date_str, r.get("filepath", "")))

    def _play_selected(self):
        sel = self.lib_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Seleziona un video dalla lista.")
            return
        filepath = self.lib_tree.item(sel[0])["values"][2]
        play_video(filepath)

    def _delete_selected(self):
        sel = self.lib_tree.selection()
        if not sel:
            return
        filepath = self.lib_tree.item(sel[0])["values"][2]
        title = self.lib_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Conferma", f"Eliminare '{title}' e il file associato?"):
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError:
                pass
            self.history.remove(filepath)
            self._refresh_library()

    def _open_download_dir(self):
        d = self.download_dir.get()
        os.makedirs(d, exist_ok=True)
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", d])
            elif system == "Windows":
                os.startfile(d)
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    # ----- Callbacks (thread-safe via queue) -----
    def _on_progress(self, task: DownloadTask):
        self.ui_queue.put(("progress", task))

    def _on_complete(self, task: DownloadTask):
        self.ui_queue.put(("complete", task))

    def _on_error(self, task: DownloadTask):
        self.ui_queue.put(("error", task))

    def _on_info(self, task: DownloadTask):
        self.ui_queue.put(("info", task))

    def _poll_queue(self):
        try:
            while True:
                event, task = self.ui_queue.get_nowait()
                item_id = self.task_items.get(id(task))
                if not item_id:
                    continue

                if event == "info":
                    self.tree.set(item_id, "title", task.title[:60])

                elif event == "progress":
                    self.tree.set(item_id, "status", task.status)
                    self.tree.set(item_id, "progress", f"{task.progress:.1f}%")
                    self.tree.set(item_id, "speed", task.speed)
                    self.tree.set(item_id, "eta", task.eta)

                elif event == "complete":
                    self.tree.set(item_id, "status", task.status)
                    self.tree.set(item_id, "progress", "100%")
                    self.tree.set(item_id, "speed", "")
                    self.tree.set(item_id, "eta", "")
                    # Salva nella cronologia
                    self.history.add(task.title, task.filepath, task.url)
                    self._refresh_library()
                    self.status_var.set(f"Completato: {task.title}")

                elif event == "error":
                    self.tree.set(item_id, "status", task.status)
                    self.tree.set(item_id, "speed", "")
                    self.tree.set(item_id, "eta", "")
                    if task.error_msg:
                        self.status_var.set(f"Errore: {task.error_msg[:80]}")

        except queue.Empty:
            pass

        self.after(250, self._poll_queue)

    # ----- Chiusura -----
    def destroy(self):
        self.engine.shutdown()
        super().destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
