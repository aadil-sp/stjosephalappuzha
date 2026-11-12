# Smart Farm Android app

A native Android app (Android 8.0 or newer) to watch and control the farm controller
from anywhere: live sensors, pump 1 (water, AUTO / MANUAL), pump 2 (fertilizer, timed),
rain tank full alert with reset, today's watering / fertilizer plan, Farm AI brief and
questions, crop, growth stage, watering limits and the tank alert level.

It talks to the same REST API as the web dashboard (`web_server.py`). Plain Java with
the platform widgets only - no libraries.

## Install on a phone

1. Send `release/SmartFarm.apk` to the phone (WhatsApp, Drive, USB...).
2. Open it. Android asks to allow installing from that app - allow it, then Install.
3. Open **Smart Farm** → **Settings**, enter the farm address and access key → **Save and connect**.

## Farm address and access key

* **From anywhere:** the farm controller needs an internet address. Run once on the Pi:
  `bash setup_remote_access.sh <ngrok-authtoken> <static-domain>` (free ngrok account;
  the dashboard gives one free static domain like `calm-owl-123.ngrok-free.app`).
  The script prints the address and key to type into the app.
* **On the farm Wi-Fi:** the address on the touchscreen, Device → Web app
  (for example `192.168.1.20`; the app adds `:8000`).
* **Access key:** touchscreen → Device → App key (format `XXXX-XXXX-XXXX`). It is created
  on first use and kept in `config/.env` as `APP_KEY`. Requests from the local network
  do not need it; everything from the internet does. To change it, delete the `APP_KEY`
  line and restart the service - a new one is made.

## Build

```bash
./build_apk.sh        # -> build/SmartFarm.apk
```

Uses the Android SDK command-line tools (platform 34, build-tools 35) and a JDK 11+
(Android Studio's bundled one is found automatically). The signing key is
`~/.android/smartfarm-release.jks`, created on the first build. **Back it up**: phones
only install updates signed with the same key. Raise `versionCode` / `versionName` in
`app/src/main/AndroidManifest.xml` for each new release.
