#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  YT Downloader - Setup automatico per Termux (Android)
#
#  Copia e incolla questo comando nel terminale Termux:
#
#    bash setup_termux.sh
#
# ============================================================

set -e

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   YT Downloader - Setup per Android      ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# 1. Aggiorna pacchetti
echo "[1/5] Aggiorno i pacchetti..."
pkg update -y && pkg upgrade -y

# 2. Installa Python, ffmpeg, git
echo "[2/5] Installo Python, ffmpeg..."
pkg install -y python ffmpeg

# 3. Installa dipendenze Python
echo "[3/5] Installo le dipendenze Python..."
pip install --upgrade pip
pip install flask yt-dlp

# 4. Permessi storage
echo "[4/5] Configuro i permessi storage..."
termux-setup-storage || true

# 5. Crea shortcut per avvio rapido
echo "[5/5] Creo lo script di avvio..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cat > "$HOME/ytdownloader.sh" << LAUNCHER
#!/data/data/com.termux/files/usr/bin/bash
cd "$SCRIPT_DIR"
echo ""
echo "  Avvio YT Downloader..."
echo "  Apri nel browser: http://localhost:8080"
echo ""
python main.py
LAUNCHER
chmod +x "$HOME/ytdownloader.sh"

# Crea anche un widget Termux (se supportato)
mkdir -p "$HOME/.shortcuts"
cat > "$HOME/.shortcuts/YT Downloader" << SHORTCUT
#!/data/data/com.termux/files/usr/bin/bash
cd "$SCRIPT_DIR"
python main.py &
sleep 2
am start -a android.intent.action.VIEW -d "http://localhost:8080" 2>/dev/null || true
wait
SHORTCUT
chmod +x "$HOME/.shortcuts/YT Downloader"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║         Setup completato!                ║"
echo "  ║                                          ║"
echo "  ║  Per avviare l'app:                      ║"
echo "  ║                                          ║"
echo "  ║  Metodo 1 (terminale):                   ║"
echo "  ║    bash ~/ytdownloader.sh                ║"
echo "  ║                                          ║"
echo "  ║  Metodo 2 (widget home screen):          ║"
echo "  ║    Aggiungi widget Termux alla home      ║"
echo "  ║    e seleziona 'YT Downloader'           ║"
echo "  ║                                          ║"
echo "  ║  Poi apri il browser a:                  ║"
echo "  ║    http://localhost:8080                  ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
