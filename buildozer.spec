[app]

# Metadata
title = YT Downloader
package.name = ytdownloader
package.domain = org.ytdownloader
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0.0

# Requisiti Python
requirements = python3,kivy==2.3.0,kivymd==1.2.0,yt-dlp,pillow,certifi,urllib3,requests,brotli,websockets,mutagen,pycryptodomex

# Android
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 26
android.ndk = 25b
android.sdk = 33
android.accept_sdk_license = True

# Architetture (arm64 per telefoni moderni, armeabi-v7a per compatibilita)
android.archs = arm64-v8a, armeabi-v7a

# Orientamento
orientation = portrait

# Fullscreen
fullscreen = 0

# Icona e presplash (opzionale - metti i file in assets/)
# icon.filename = assets/icon.png
# presplash.filename = assets/presplash.png

# Android specifici
android.enable_androidx = True

# FileProvider per condivisione file video
android.add_src = .

# Gradle dependencies per FileProvider
android.gradle_dependencies = androidx.core:core:1.6.0

# Log level per debug
log_level = 2

# Manifest
android.manifest.intent_filters =

[buildozer]
log_level = 2
warn_on_root = 1
