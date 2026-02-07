#!/usr/bin/env python3
"""
YouTube Video Downloader - App Android (Kivy + KivyMD)
======================================================
Scarica video YouTube in locale, gestiscili in un database SQLite,
e visualizzali offline direttamente dal telefono.
"""

import os
import platform
import subprocess
import threading

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.app import MDApp
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.snackbar import Snackbar

from database import (
    add_video,
    delete_video,
    get_all_videos,
    get_completed_videos,
    get_total_size,
    get_video,
    init_db,
    update_video,
)
from downloader import DownloadEngine, get_download_dir


# ---------------------------------------------------------------------------
# Widget per singolo elemento download/libreria
# ---------------------------------------------------------------------------
class DownloadItemWidget(BoxLayout):
    title = StringProperty("Caricamento...")
    status_text = StringProperty("In coda")
    progress = NumericProperty(0)
    speed = StringProperty("")
    bg_dark = BooleanProperty(False)
    vid = NumericProperty(0)

    def play_video(self):
        video = get_video(self.vid)
        if not video or not video.get("filepath"):
            Snackbar(text="File non disponibile").open()
            return
        filepath = video["filepath"]
        if not os.path.exists(filepath):
            Snackbar(text="File non trovato sul dispositivo").open()
            return
        _open_file(filepath)

    def delete_video(self):
        app = MDApp.get_running_app()
        app.root_widget.confirm_delete(self.vid, self.title)


# ---------------------------------------------------------------------------
# Schermata principale
# ---------------------------------------------------------------------------
class RootScreen(BoxLayout):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine = DownloadEngine(
            on_progress=self._on_progress,
            on_complete=self._on_complete,
            on_error=self._on_error,
            on_info=self._on_info,
        )
        self._widgets: dict[int, DownloadItemWidget] = {}
        # Carica la libreria all'avvio (prossimo frame)
        Clock.schedule_once(lambda dt: self.refresh_library(), 0.5)

    # ---- Download ----

    def start_downloads(self):
        url_input = self.ids.url_input
        raw = url_input.text.strip()
        if not raw:
            Snackbar(text="Inserisci almeno un URL").open()
            return

        urls = [u.strip() for u in raw.split("\n") if u.strip()]
        if not urls:
            Snackbar(text="Nessun URL valido").open()
            return

        quality = self.ids.quality_spinner.text
        count = 0

        for url in urls:
            vid = add_video(url, quality)
            widget = DownloadItemWidget(
                vid=vid,
                title=url[:60],
                status_text="In coda",
                bg_dark=(count % 2 == 0),
            )
            self._widgets[vid] = widget
            self.ids.active_downloads_list.add_widget(widget)
            self.engine.start_download(vid, url, quality)
            count += 1

        url_input.text = ""
        self.ids.lbl_queue_info.text = f"{count} download avviati"
        Snackbar(text=f"Avviati {count} download").open()

    def _on_progress(self, vid, pct, speed, eta):
        Clock.schedule_once(lambda dt: self._update_widget(vid, pct, speed, eta), 0)

    def _on_complete(self, vid):
        Clock.schedule_once(lambda dt: self._complete_widget(vid), 0)

    def _on_error(self, vid, msg):
        Clock.schedule_once(lambda dt: self._error_widget(vid, msg), 0)

    def _on_info(self, vid, title):
        Clock.schedule_once(lambda dt: self._info_widget(vid, title), 0)

    def _update_widget(self, vid, pct, speed, eta):
        w = self._widgets.get(vid)
        if not w:
            return
        w.progress = pct
        w.status_text = f"Download... {pct:.0f}%"
        w.speed = speed if speed else ""

    def _complete_widget(self, vid):
        w = self._widgets.get(vid)
        if not w:
            return
        w.progress = 100
        w.status_text = "Completato"
        w.speed = ""
        video = get_video(vid)
        if video:
            w.title = video.get("title", w.title)
        Snackbar(text=f"Download completato: {w.title[:40]}").open()
        self.refresh_library()

    def _error_widget(self, vid, msg):
        w = self._widgets.get(vid)
        if not w:
            return
        w.status_text = "Errore"
        w.speed = ""
        Snackbar(text=f"Errore: {msg[:60]}").open()

    def _info_widget(self, vid, title):
        w = self._widgets.get(vid)
        if w:
            w.title = title[:60]

    # ---- Libreria ----

    def refresh_library(self):
        lib_list = self.ids.library_list
        lib_list.clear_widgets()

        videos = get_completed_videos()
        lbl_empty = self.ids.lbl_empty_library
        lbl_empty.opacity = 0 if videos else 1

        for i, v in enumerate(videos):
            exists = os.path.exists(v.get("filepath", ""))
            title = v.get("title", "Sconosciuto")
            if not exists:
                title += " [mancante]"

            size_mb = v.get("filesize", 0) / (1024 * 1024)
            duration = v.get("duration", "")
            info_text = f"{duration}  -  {size_mb:.1f} MB" if duration else f"{size_mb:.1f} MB"

            widget = DownloadItemWidget(
                vid=v["id"],
                title=title,
                status_text="Completato" if exists else "File mancante",
                progress=100 if exists else 0,
                speed=info_text,
                bg_dark=(i % 2 == 0),
            )
            lib_list.add_widget(widget)

        # Aggiorna info storage
        total = get_total_size()
        if total > 0:
            mb = total / (1024 * 1024)
            if mb > 1024:
                self.ids.lbl_storage.text = f"Spazio usato: {mb / 1024:.1f} GB"
            else:
                self.ids.lbl_storage.text = f"Spazio usato: {mb:.0f} MB"
        else:
            self.ids.lbl_storage.text = ""

    def confirm_delete(self, vid, title):
        dialog = MDDialog(
            title="Elimina video",
            text=f"Eliminare '{title}'?\nIl file verra rimosso dal dispositivo.",
            buttons=[
                MDFlatButton(
                    text="ANNULLA",
                    on_release=lambda x: dialog.dismiss(),
                ),
                MDRaisedButton(
                    text="ELIMINA",
                    md_bg_color=(0.9, 0.2, 0.2, 1),
                    on_release=lambda x: self._do_delete(vid, dialog),
                ),
            ],
        )
        dialog.open()

    def _do_delete(self, vid, dialog):
        dialog.dismiss()
        delete_video(vid)
        # Rimuovi widget dalla lista attivi se presente
        w = self._widgets.pop(vid, None)
        if w and w.parent:
            w.parent.remove_widget(w)
        self.refresh_library()
        Snackbar(text="Video eliminato").open()

    def open_folder(self):
        d = get_download_dir()
        _open_file(d)

    def show_info(self):
        total = get_total_size()
        mb = total / (1024 * 1024)
        n = len(get_completed_videos())
        dialog = MDDialog(
            title="Informazioni",
            text=(
                f"Video scaricati: {n}\n"
                f"Spazio utilizzato: {mb:.1f} MB\n"
                f"Cartella: {get_download_dir()}\n\n"
                "I video vengono salvati in formato MP4\n"
                "e possono essere riprodotti offline."
            ),
            buttons=[
                MDFlatButton(text="OK", on_release=lambda x: dialog.dismiss()),
            ],
        )
        dialog.open()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def _open_file(path: str):
    """Apre un file/cartella con il viewer di sistema / Android."""
    try:
        from android.intent import Intent  # type: ignore
        from jnius import autoclass  # type: ignore

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        File = autoclass("java.io.File")
        FileProvider = autoclass("androidx.core.content.FileProvider")

        context = PythonActivity.mActivity
        java_file = File(path)

        if os.path.isdir(path):
            intent = Intent(Intent.ACTION_VIEW)
            uri = Uri.parse(path)
            intent.setDataAndType(uri, "resource/folder")
        else:
            uri = FileProvider.getUriForFile(
                context,
                context.getPackageName() + ".fileprovider",
                java_file,
            )
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, "video/*")
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

        context.startActivity(intent)
    except ImportError:
        # Desktop fallback
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", path])
        elif system == "Windows":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class YTDownloaderApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_widget = None

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Red"
        self.theme_cls.accent_palette = "Amber"
        self.title = "YT Downloader"

        Builder.load_file("ytdownloader.kv")
        self.root_widget = RootScreen()
        return self.root_widget

    def on_start(self):
        init_db()
        # Android: richiedi permessi storage
        self._request_android_permissions()

    def _request_android_permissions(self):
        try:
            from android.permissions import Permission, request_permissions  # type: ignore
            request_permissions([
                Permission.INTERNET,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
            ])
        except ImportError:
            pass  # non siamo su Android

    def on_stop(self):
        if self.root_widget:
            self.root_widget.engine.shutdown()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    YTDownloaderApp().run()
