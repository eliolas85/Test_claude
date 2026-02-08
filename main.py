#!/usr/bin/env python3
"""
YT Downloader - Server web locale per Android (Termux) e desktop.
Avvia e apri http://localhost:8080 dal browser del telefono.
"""

import os
import sys

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_from_directory,
    url_for,
)

from database import (
    add_video,
    delete_video,
    get_all_videos,
    get_completed_videos,
    get_downloading_videos,
    get_total_size,
    get_video,
    init_db,
)
from downloader import DownloadEngine, QUALITY_LABELS, get_download_dir

app = Flask(__name__)
engine = DownloadEngine()

# ---------------------------------------------------------------------------
# Template HTML unico, mobile-first
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#1a1a2e">
<title>YT Downloader</title>
<style>
  :root {
    --bg: #1a1a2e;
    --bg2: #16213e;
    --bg3: #0f3460;
    --red: #e94560;
    --red-dark: #c23152;
    --text: #eee;
    --text2: #aab;
    --text3: #778;
    --green: #4ecca3;
    --yellow: #f0c040;
    --radius: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding-bottom: 80px;
  }

  /* Header */
  .header {
    background: linear-gradient(135deg, var(--red) 0%, var(--bg3) 100%);
    padding: 20px 16px 16px;
    text-align: center;
    position: sticky; top: 0; z-index: 100;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
  }
  .header h1 { font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }
  .header .subtitle { font-size: 12px; color: rgba(255,255,255,0.7); margin-top: 2px; }

  /* Tab bar */
  .tabs {
    display: flex;
    position: fixed; bottom: 0; left: 0; right: 0;
    background: var(--bg2);
    border-top: 1px solid rgba(255,255,255,0.08);
    z-index: 100;
    box-shadow: 0 -2px 12px rgba(0,0,0,0.3);
  }
  .tab {
    flex: 1; text-align: center; padding: 10px 0 8px;
    text-decoration: none; color: var(--text3);
    font-size: 12px; font-weight: 500;
    transition: color 0.2s;
  }
  .tab.active { color: var(--red); }
  .tab svg { display: block; margin: 0 auto 3px; width: 24px; height: 24px; }
  .tab.active svg { fill: var(--red); }
  .tab svg { fill: var(--text3); }

  /* Container */
  .container { padding: 16px; max-width: 600px; margin: 0 auto; }

  /* Card */
  .card {
    background: var(--bg2);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  }

  /* Form */
  textarea {
    width: 100%; border: 1px solid rgba(255,255,255,0.12);
    background: var(--bg); color: var(--text);
    border-radius: 8px; padding: 12px; font-size: 15px;
    resize: vertical; min-height: 100px;
    font-family: inherit;
  }
  textarea:focus { outline: none; border-color: var(--red); }
  textarea::placeholder { color: var(--text3); }

  select {
    width: 100%; background: var(--bg); color: var(--text);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px; padding: 12px; font-size: 15px;
    margin-top: 10px; appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23aab' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
  }

  .btn {
    display: block; width: 100%;
    padding: 14px; margin-top: 12px;
    background: var(--red); color: white;
    border: none; border-radius: 8px;
    font-size: 16px; font-weight: 600;
    cursor: pointer; text-align: center;
    text-decoration: none;
    transition: background 0.2s;
  }
  .btn:active { background: var(--red-dark); }
  .btn-sm {
    display: inline-block; width: auto;
    padding: 8px 16px; font-size: 13px; margin: 0;
    border-radius: 6px;
  }
  .btn-ghost {
    background: transparent; border: 1px solid var(--red);
    color: var(--red);
  }
  .btn-danger { background: #c0392b; }
  .btn-play { background: var(--green); }

  /* Video item */
  .video-item {
    background: var(--bg2);
    border-radius: var(--radius);
    padding: 14px;
    margin-bottom: 10px;
    display: flex; gap: 12px; align-items: flex-start;
  }
  .video-item .thumb {
    width: 100px; min-width: 100px; height: 56px;
    border-radius: 6px; object-fit: cover;
    background: var(--bg3);
  }
  .video-info { flex: 1; min-width: 0; }
  .video-info h3 {
    font-size: 14px; font-weight: 600;
    line-height: 1.3;
    overflow: hidden; text-overflow: ellipsis;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  }
  .video-meta {
    font-size: 12px; color: var(--text2); margin-top: 4px;
  }
  .video-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }

  /* Progress bar */
  .progress-wrap {
    background: var(--bg); border-radius: 4px;
    height: 6px; margin-top: 8px; overflow: hidden;
  }
  .progress-bar {
    height: 100%; border-radius: 4px;
    background: linear-gradient(90deg, var(--red), var(--yellow));
    transition: width 0.5s ease;
  }
  .progress-bar.done { background: var(--green); }

  /* Status badges */
  .badge {
    display: inline-block; padding: 2px 8px;
    border-radius: 10px; font-size: 11px; font-weight: 600;
  }
  .badge-downloading { background: rgba(240,192,64,0.2); color: var(--yellow); }
  .badge-completed { background: rgba(78,204,163,0.2); color: var(--green); }
  .badge-error { background: rgba(233,69,96,0.2); color: var(--red); }
  .badge-pending { background: rgba(170,170,187,0.15); color: var(--text2); }
  .badge-cancelled { background: rgba(170,170,187,0.1); color: var(--text3); }

  /* Stats */
  .stats {
    display: flex; gap: 10px; margin-bottom: 14px;
  }
  .stat {
    flex: 1; background: var(--bg2);
    border-radius: 10px; padding: 12px; text-align: center;
  }
  .stat-num { font-size: 22px; font-weight: 700; color: var(--red); }
  .stat-label { font-size: 11px; color: var(--text3); margin-top: 2px; }

  /* Empty state */
  .empty {
    text-align: center; padding: 40px 20px;
    color: var(--text3);
  }
  .empty svg { width: 48px; height: 48px; fill: var(--text3); margin-bottom: 12px; }

  /* Toast */
  .toast {
    position: fixed; top: 80px; left: 50%; transform: translateX(-50%);
    background: var(--green); color: #000; padding: 10px 20px;
    border-radius: 8px; font-size: 14px; font-weight: 600;
    z-index: 200; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    animation: fadeInOut 3s forwards;
  }
  .toast.error { background: var(--red); color: white; }
  @keyframes fadeInOut {
    0% { opacity: 0; transform: translateX(-50%) translateY(-10px); }
    10% { opacity: 1; transform: translateX(-50%) translateY(0); }
    80% { opacity: 1; }
    100% { opacity: 0; }
  }

  /* Confirm dialog */
  .overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.6); z-index: 150;
    align-items: center; justify-content: center;
  }
  .overlay.show { display: flex; }
  .dialog {
    background: var(--bg2); border-radius: 16px;
    padding: 24px; margin: 20px; max-width: 340px; width: 100%;
    text-align: center;
  }
  .dialog h3 { margin-bottom: 8px; }
  .dialog p { color: var(--text2); font-size: 14px; margin-bottom: 20px; }
  .dialog-btns { display: flex; gap: 10px; }
  .dialog-btns .btn { flex: 1; margin: 0; }
</style>
</head>
<body>

{% if toast %}
<div class="toast {{ toast_type }}">{{ toast }}</div>
{% endif %}

<div class="header">
  <h1>&#9655; YT Downloader</h1>
  <div class="subtitle">Scarica e guarda video offline</div>
</div>

{% if page == 'download' %}
<!-- ======================== TAB DOWNLOAD ======================== -->
<div class="container">
  <form method="POST" action="/download">
    <div class="card">
      <textarea name="urls" placeholder="Incolla qui gli URL YouTube&#10;(uno per riga per download multipli)"
        >{{ urls or '' }}</textarea>
      <select name="quality">
        {% for key, label in qualities.items() %}
        <option value="{{ key }}" {% if key == selected_quality %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
      <button type="submit" class="btn">&#11015; SCARICA</button>
    </div>
  </form>

  {% if active_downloads %}
  <h2 style="font-size:16px; margin: 16px 0 10px;">Download in corso</h2>
  {% for v in active_downloads %}
  <div class="video-item">
    <div class="video-info" style="width:100%">
      <h3>{{ v.title or v.url }}</h3>
      <div class="video-meta">
        <span class="badge badge-{{ v.status }}">
          {% if v.status == 'downloading' %}Scaricando...
          {% elif v.status == 'pending' %}In coda
          {% elif v.status == 'error' %}Errore
          {% elif v.status == 'cancelled' %}Annullato
          {% else %}{{ v.status }}{% endif %}
        </span>
        {% if v.status == 'error' and v.error_msg %}
          <span style="color:var(--red);font-size:11px;"> {{ v.error_msg[:60] }}</span>
        {% endif %}
      </div>
      {% if v.status == 'downloading' or v.status == 'pending' %}
      <div class="progress-wrap">
        <div class="progress-bar" style="width:{{ v.progress }}%"></div>
      </div>
      <div class="video-meta" style="margin-top:4px">{{ v.progress|round(1) }}%</div>
      {% endif %}
      {% if v.status in ('downloading', 'pending') %}
      <div class="video-actions">
        <a href="/cancel/{{ v.id }}" class="btn btn-sm btn-danger">Annulla</a>
      </div>
      {% endif %}
    </div>
  </div>
  {% endfor %}

  {% if has_active %}
  <script>setTimeout(function(){ location.reload(); }, 4000);</script>
  {% endif %}
  {% endif %}
</div>

{% elif page == 'library' %}
<!-- ======================== TAB LIBRERIA ======================== -->
<div class="container">
  <div class="stats">
    <div class="stat">
      <div class="stat-num">{{ video_count }}</div>
      <div class="stat-label">Video</div>
    </div>
    <div class="stat">
      <div class="stat-num">{{ storage_used }}</div>
      <div class="stat-label">Spazio</div>
    </div>
  </div>

  {% if videos %}
    {% for v in videos %}
    <div class="video-item">
      {% if v.thumbnail %}
      <img class="thumb" src="{{ v.thumbnail }}" alt="" loading="lazy">
      {% else %}
      <div class="thumb" style="display:flex;align-items:center;justify-content:center;">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="#555"><path d="M8 5v14l11-7z"/></svg>
      </div>
      {% endif %}
      <div class="video-info">
        <h3>{{ v.title or 'Video senza titolo' }}</h3>
        <div class="video-meta">
          {{ v.duration }}
          {% if v.filesize %} &middot; {{ (v.filesize / 1048576)|round(1) }} MB{% endif %}
          &middot; {{ v.created_at[:10] }}
        </div>
        <div class="video-actions">
          <a href="/play/{{ v.id }}" class="btn btn-sm btn-play">&#9655; Play</a>
          <a href="#" onclick="confirmDelete({{ v.id }}, '{{ v.title|e }}')" class="btn btn-sm btn-danger">Elimina</a>
        </div>
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">
      <svg viewBox="0 0 24 24"><path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8 12.5v-9l6 4.5-6 4.5z"/></svg>
      <p>Nessun video scaricato</p>
      <a href="/" class="btn btn-sm" style="margin-top:12px">Vai ai download</a>
    </div>
  {% endif %}
</div>

<!-- Dialog conferma eliminazione -->
<div class="overlay" id="deleteOverlay">
  <div class="dialog">
    <h3>Elimina video</h3>
    <p id="deleteMsg">Eliminare questo video?</p>
    <div class="dialog-btns">
      <button class="btn btn-ghost" onclick="closeDelete()">Annulla</button>
      <a id="deleteLink" href="#" class="btn btn-danger">Elimina</a>
    </div>
  </div>
</div>
<script>
function confirmDelete(id, title) {
  document.getElementById('deleteMsg').textContent = 'Eliminare "' + title + '"? Il file verra rimosso.';
  document.getElementById('deleteLink').href = '/delete/' + id;
  document.getElementById('deleteOverlay').classList.add('show');
}
function closeDelete() {
  document.getElementById('deleteOverlay').classList.remove('show');
}
</script>
{% endif %}

<!-- ======================== BOTTOM TABS ======================== -->
<div class="tabs">
  <a href="/" class="tab {% if page == 'download' %}active{% endif %}">
    <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
    Download
  </a>
  <a href="/library" class="tab {% if page == 'library' %}active{% endif %}">
    <svg viewBox="0 0 24 24"><path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8 12.5v-9l6 4.5-6 4.5z"/></svg>
    Libreria
  </a>
</div>

</body>
</html>
"""


PLAYER_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="theme-color" content="#000">
<title>{{ video.title or 'Player' }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #000; color: #eee; font-family: -apple-system, sans-serif; min-height: 100vh; }
  .player-wrap {
    width: 100%; max-width: 800px; margin: 0 auto;
    display: flex; flex-direction: column; min-height: 100vh;
  }
  video, audio {
    width: 100%; max-height: 60vh;
    background: #000; display: block;
  }
  audio { margin-top: 30vh; }
  .info {
    padding: 16px; flex: 1;
    background: #1a1a2e;
  }
  .info h2 { font-size: 16px; line-height: 1.4; margin-bottom: 8px; }
  .info .meta { font-size: 13px; color: #aab; margin-bottom: 16px; }
  .back-btn {
    display: inline-block; padding: 10px 20px;
    background: #e94560; color: #fff; text-decoration: none;
    border-radius: 8px; font-weight: 600; font-size: 14px;
  }
  .back-btn:active { background: #c23152; }
</style>
</head>
<body>
<div class="player-wrap">
  {% if is_audio %}
  <audio controls autoplay preload="auto">
    <source src="/stream/{{ vid }}" type="audio/mpeg">
    Il browser non supporta la riproduzione audio.
  </audio>
  {% else %}
  <video controls autoplay playsinline preload="auto">
    <source src="/stream/{{ vid }}" type="video/mp4">
    Il browser non supporta la riproduzione video.
  </video>
  {% endif %}
  <div class="info">
    <h2>{{ video.title or 'Video' }}</h2>
    <div class="meta">
      {{ video.duration }}
      {% if video.filesize %} &middot; {{ (video.filesize / 1048576)|round(1) }} MB{% endif %}
    </div>
    <a href="/library" class="back-btn">&larr; Torna alla libreria</a>
  </div>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    active = get_downloading_videos()
    # Includi anche gli errori/cancellati recenti
    all_vids = get_all_videos()
    recent_non_completed = [
        v for v in all_vids
        if v["status"] in ("pending", "downloading", "error", "cancelled")
    ][:20]

    has_active = any(v["status"] in ("pending", "downloading") for v in recent_non_completed)

    return render_template_string(
        HTML_TEMPLATE,
        page="download",
        qualities=QUALITY_LABELS,
        selected_quality="best",
        active_downloads=recent_non_completed,
        has_active=has_active,
        urls="",
        toast=request.args.get("toast"),
        toast_type=request.args.get("toast_type", ""),
    )


@app.route("/download", methods=["POST"])
def start_download():
    raw = request.form.get("urls", "").strip()
    quality = request.form.get("quality", "best")

    if not raw:
        return redirect("/?toast=Inserisci+almeno+un+URL&toast_type=error")

    urls = [u.strip() for u in raw.splitlines() if u.strip()]
    if not urls:
        return redirect("/?toast=Nessun+URL+valido&toast_type=error")

    for url in urls:
        vid = add_video(url, quality)
        engine.start_download(vid, url, quality)

    msg = f"{len(urls)}+download+avviati"
    return redirect(f"/?toast={msg}")


@app.route("/cancel/<int:vid>")
def cancel_download(vid):
    engine.cancel(vid)
    return redirect("/?toast=Download+annullato")


@app.route("/library")
def library():
    videos = get_completed_videos()
    total_bytes = get_total_size()
    if total_bytes > 1073741824:
        storage = f"{total_bytes / 1073741824:.1f} GB"
    elif total_bytes > 0:
        storage = f"{total_bytes / 1048576:.0f} MB"
    else:
        storage = "0 MB"

    return render_template_string(
        HTML_TEMPLATE,
        page="library",
        videos=videos,
        video_count=len(videos),
        storage_used=storage,
        toast=request.args.get("toast"),
        toast_type=request.args.get("toast_type", ""),
    )


@app.route("/stream/<int:vid>")
def stream(vid):
    """Serve il file video/audio raw con MIME type corretto."""
    video = get_video(vid)
    if not video or not video.get("filename"):
        return "File non trovato", 404
    filename = video["filename"]
    mimetype = "audio/mpeg" if filename.endswith(".mp3") else "video/mp4"
    return send_from_directory(
        get_download_dir(),
        filename,
        as_attachment=False,
        mimetype=mimetype,
    )


@app.route("/play/<int:vid>")
def play(vid):
    video = get_video(vid)
    if not video or not video.get("filename"):
        return redirect("/library?toast=File+non+trovato&toast_type=error")
    is_audio = video["filename"].endswith(".mp3")
    return render_template_string(PLAYER_TEMPLATE, video=video, vid=vid, is_audio=is_audio)


@app.route("/delete/<int:vid>")
def delete(vid):
    delete_video(vid)
    return redirect("/library?toast=Video+eliminato")


@app.route("/api/status")
def api_status():
    """API JSON per polling AJAX (opzionale)."""
    active = get_downloading_videos()
    return jsonify([
        {"id": v["id"], "title": v["title"], "status": v["status"],
         "progress": v["progress"]}
        for v in active
    ])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    init_db()
    port = int(os.environ.get("PORT", 8080))
    print(f"""
    ╔══════════════════════════════════════════╗
    ║       YT Downloader - Avviato!           ║
    ║                                          ║
    ║   Apri nel browser:                      ║
    ║   http://localhost:{port:<5}                 ║
    ║                                          ║
    ║   Premi Ctrl+C per fermare               ║
    ╚══════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
