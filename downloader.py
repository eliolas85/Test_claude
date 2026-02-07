"""
Download engine - gestisce i download concorrenti tramite yt-dlp.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from database import update_video, get_video

MAX_CONCURRENT = 3

QUALITY_MAP = {
    "Migliore": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
    "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
    "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
    "Solo Audio": "bestaudio/best",
}


def get_download_dir() -> str:
    """Ritorna la cartella di download, compatibile Android e desktop."""
    try:
        from android.storage import primary_external_storage_path  # type: ignore
        base = primary_external_storage_path()
        d = os.path.join(base, "YTDownloader")
    except ImportError:
        d = os.path.join(os.path.expanduser("~"), "YTDownloader")
    os.makedirs(d, exist_ok=True)
    return d


class DownloadEngine:
    """Gestisce il pool di download concorrenti."""

    def __init__(self, on_progress=None, on_complete=None, on_error=None, on_info=None):
        self.pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._on_info = on_info
        self._cancelled: set[int] = set()
        self._lock = threading.Lock()

    def start_download(self, vid: int, url: str, quality: str):
        """Invia un download al pool."""
        self.pool.submit(self._run, vid, url, quality)

    def cancel(self, vid: int):
        with self._lock:
            self._cancelled.add(vid)

    def _is_cancelled(self, vid: int) -> bool:
        with self._lock:
            return vid in self._cancelled

    def _run(self, vid: int, url: str, quality: str):
        if yt_dlp is None:
            update_video(vid, status="error", error_msg="yt-dlp non installato")
            if self._on_error:
                self._on_error(vid, "yt-dlp non installato")
            return

        audio_only = quality == "Solo Audio"
        fmt = QUALITY_MAP.get(quality, QUALITY_MAP["Migliore"])
        out_dir = get_download_dir()
        outtmpl = os.path.join(out_dir, "%(title)s.%(ext)s")

        def progress_hook(d):
            if self._is_cancelled(vid):
                raise Exception("Download annullato")

            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total else 0
                speed = d.get("_speed_str", "")
                eta = d.get("_eta_str", "")
                update_video(vid, status="downloading", progress=pct)
                if self._on_progress:
                    self._on_progress(vid, pct, speed, eta)

            elif d["status"] == "finished":
                update_video(vid, progress=100)
                if self._on_progress:
                    self._on_progress(vid, 100, "", "")

        ydl_opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
            "noplaylist": False,
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4" if not audio_only else None,
        }

        if audio_only:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        try:
            update_video(vid, status="downloading", progress=0)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    title = info.get("title", "Video")
                    duration = str(info.get("duration_string", ""))
                    thumb = info.get("thumbnail", "")
                    update_video(vid, title=title, duration=duration, thumbnail=thumb)
                    if self._on_info:
                        self._on_info(vid, title)

                if self._is_cancelled(vid):
                    update_video(vid, status="cancelled")
                    return

                ydl.download([url])

            # Determina filepath
            ext = "mp3" if audio_only else "mp4"
            title = info.get("title", "video") if info else "video"
            filepath = os.path.join(out_dir, f"{title}.{ext}")
            filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0

            update_video(
                vid,
                status="completed",
                progress=100,
                filepath=filepath,
                filesize=filesize,
            )
            if self._on_complete:
                self._on_complete(vid)

        except Exception as e:
            if self._is_cancelled(vid):
                update_video(vid, status="cancelled")
            else:
                msg = str(e)[:200]
                update_video(vid, status="error", error_msg=msg)
                if self._on_error:
                    self._on_error(vid, msg)

    def shutdown(self):
        self.pool.shutdown(wait=False)
