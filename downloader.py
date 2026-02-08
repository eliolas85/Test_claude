"""
Download engine - gestisce i download concorrenti tramite yt-dlp.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from database import update_video, get_video

MAX_CONCURRENT = 3

QUALITY_MAP = {
    # Priorita: formato gia muxato (audio+video insieme) > merge separati
    "best": "best[ext=mp4][acodec!=none][vcodec!=none]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
    "1080p": "best[height<=1080][ext=mp4][acodec!=none][vcodec!=none]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
    "720p": "best[height<=720][ext=mp4][acodec!=none][vcodec!=none]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
    "480p": "best[height<=480][ext=mp4][acodec!=none][vcodec!=none]/bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
    "360p": "best[height<=360][ext=mp4][acodec!=none][vcodec!=none]/bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
    "audio": "bestaudio[ext=m4a]/bestaudio/best",
}

QUALITY_LABELS = {
    "best": "Migliore",
    "1080p": "1080p",
    "720p": "720p",
    "480p": "480p",
    "360p": "360p",
    "audio": "Solo Audio (MP3)",
}


def get_download_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
    os.makedirs(d, exist_ok=True)
    return d


class DownloadEngine:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)
        self._cancelled: set[int] = set()
        self._lock = threading.Lock()

    def start_download(self, vid: int, url: str, quality: str):
        self.pool.submit(self._run, vid, url, quality)

    def cancel(self, vid: int):
        with self._lock:
            self._cancelled.add(vid)
        update_video(vid, status="cancelled")

    def _is_cancelled(self, vid: int) -> bool:
        with self._lock:
            return vid in self._cancelled

    def _run(self, vid: int, url: str, quality: str):
        audio_only = quality == "audio"
        fmt = QUALITY_MAP.get(quality, QUALITY_MAP["best"])
        out_dir = get_download_dir()
        outtmpl = os.path.join(out_dir, "%(title)s.%(ext)s")

        def progress_hook(d):
            if self._is_cancelled(vid):
                raise Exception("Download annullato")
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total else 0
                update_video(vid, status="downloading", progress=round(pct, 1))
            elif d["status"] == "finished":
                update_video(vid, progress=100)

        postprocessors = []
        if audio_only:
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            })
        else:
            # Ri-muxa sempre in mp4 per garantire che audio e video siano uniti
            postprocessors.append({
                "key": "FFmpegVideoRemuxer",
                "prefformat": "mp4",
            })

        ydl_opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
            "noplaylist": False,
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4" if not audio_only else None,
            "postprocessors": postprocessors,
            # Embedding: includi audio nel container mp4
            "postprocessor_args": {"ffmpeg": ["-c:a", "aac", "-c:v", "copy"]},
        }

        try:
            update_video(vid, status="downloading", progress=0)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    title = info.get("title", "Video")
                    duration = str(info.get("duration_string", ""))
                    thumb = info.get("thumbnail", "")
                    update_video(vid, title=title, duration=duration, thumbnail=thumb)

                if self._is_cancelled(vid):
                    update_video(vid, status="cancelled")
                    return

                ydl.download([url])

            ext = "mp3" if audio_only else "mp4"
            title = info.get("title", "video") if info else "video"
            # Sanitizza il nome file come fa yt-dlp
            filename = yt_dlp.utils.sanitize_filename(title) + f".{ext}"
            filepath = os.path.join(out_dir, filename)

            # Cerca il file reale (yt-dlp potrebbe aver usato un nome leggermente diverso)
            if not os.path.exists(filepath):
                for f in os.listdir(out_dir):
                    if f.endswith(f".{ext}") and title[:20].lower() in f.lower():
                        filepath = os.path.join(out_dir, f)
                        filename = f
                        break

            filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0

            update_video(
                vid,
                status="completed",
                progress=100,
                filepath=filepath,
                filename=filename,
                filesize=filesize,
            )

        except Exception as e:
            if self._is_cancelled(vid):
                update_video(vid, status="cancelled")
            else:
                msg = str(e)[:200]
                update_video(vid, status="error", error_msg=msg)

    def shutdown(self):
        self.pool.shutdown(wait=False)
