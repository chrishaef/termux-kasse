# Termux-Vertrauenskasse

Lokal laufende Vertrauenskasse (FastAPI, SQLite, Jinja2). Keine CDN-Assets: `pico.min.css` liegt unter `app/static/`.

## Voraussetzungen (Termux auf dem Tablet)

- Entweder manuell: `pkg install python git`
- Oder automatisch beim ersten Lauf von **`update.sh`** (siehe unten)

## Installation

```bash
cd ~
git clone <DEIN_PRIVATE_CLONE_URL> termux-kasse
cd termux-kasse
bash update.sh          # installiert bei Bedarf git/python (Termux/apt), pull, pip, startet Server im Hintergrund
# oder klassisch:
bash start.sh --sync   # nur venv + pip
bash start.sh          # Vordergrund-Server auf 127.0.0.1:8000
```

Im Browser auf demselben Gerät: [http://127.0.0.1:8000](http://127.0.0.1:8000)

Anderer Port:

```bash
PORT=9000 bash start.sh
```

### Zugriff aus dem lokalen Netz (z. B. LXC / Debian-Test)

Standardmäßig lauscht der Dienst nur auf **`127.0.0.1`** — damit ist er **nur auf demselben Rechner** im Browser erreichbar, nicht unter `http://192.168.x.x:8000` von anderen Geräten.

Für Tests aus dem LAN den Server an **alle Schnittstellen** binden:

```bash
HOST=0.0.0.0 PORT=8000 bash start.sh
# oder mit update.sh (Server neu starten):
HOST=0.0.0.0 bash update.sh
```

Dann im Browser z. B. `http://192.168.178.123:8000` (IP des Containers/Hosts). **Hinweis:** Im Heimnetz meist unkritisch; in fremden Netzen wieder `HOST=127.0.0.1` nutzen.

Wenn weiterhin nichts erreichbar ist: **Firewall** im LXC oder auf Proxmox prüfen, ob Port **8000/tcp** durchgelassen wird.

## Daten & Backup

- SQLite-Datei: `data/kasse.db` (relativ zum Projektroot), außer du setzt `KASSE_DATA_DIR` auf einen absoluten Pfad.
- Session-Secret: `.secret_key` im Projektroot (von Git ignoriert) oder Umgebungsvariable `KASSE_SECRET_KEY`.
- Backup: Ordner `data/` kopieren oder nur `kasse.db` sichern, während der Server **gestoppt** ist.

## Updates (Hotspot / WLAN)

Wenn das Tablet kurz online ist (z. B. Handy-Hotspot), im Projektordner:

```bash
bash update.sh
```

**`update.sh`** ist Install- und Update-Skript in einem:

1. **System:** Prüft `git` und Python; fehlt etwas, wird installiert — **Termux** mit `pkg`, **Debian/Ubuntu** (und typische LXC) mit `apt-get` (bei Bedarf `sudo`). Ohne erkanntes System: Hinweis und Abbruch.
2. **`git pull --ff-only`**
3. **`.venv`** anlegen falls nötig, **`pip install -r requirements.txt`**
4. Laufenden Server beenden (`.server.pid` oder `pkill`) und **uvicorn im Hintergrund** neu starten. Log: `server.log`.

Optionen:

```bash
bash update.sh --no-restart          # kein Neustart (nur Systemcheck/pull/pip)
bash update.sh --no-system-install   # keine Paketinstallation (nur prüfen; bricht ab, wenn git/Python fehlt)
```

Hinweis: Läuft die Kasse nur mit `bash start.sh` im Vordergrund, hat sie keine `.server.pid` — dann beendet `update.sh` per `pkill` passende `uvicorn app.main:app`-Prozesse oder du stoppt vorher manuell (Strg+C) und startest danach `bash start.sh`.

## Offline

Die App spricht keine externen Dienste an. Internet ist nur für `git pull` / `pip install` nötig, nicht für den laufenden Kiosk.

## Admin

Nach dem ersten Start: [http://127.0.0.1:8000/admin/setup](http://127.0.0.1:8000/admin/setup) — ersten Administrator anlegen. Anschließend Gruppen, Nutzer, Warengruppen und Artikel pflegen; Abrechnungen inkl. **XLS** und **PDF** unter `/admin/settlements`.

## Entwicklung (Windows / Linux)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Privates GitHub-Repository

Lokal committen, dann z. B. mit [GitHub CLI](https://cli.github.com/):

```bash
gh auth login
gh repo create termux-kasse --private --source=. --remote=origin --push
```

Oder Repo auf github.com als **Private** anlegen und `git remote add origin …` / `git push -u origin main`.
