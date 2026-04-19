# Termux-Vertrauenskasse

Lokal laufende Vertrauenskasse (FastAPI, SQLite, Jinja2). UI: **Pico.css** plus **`app/static/kasse.css`** — Oliv-/Feld-Hintergrund und Goldakzente (rein CSS, offline), optisch in der Tradition öffentlicher Informationsportale; **kein** Bezug zu offiziellen Markenassets der Bundeswehr.

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
bash start.sh          # Vordergrund-Server, Port 8000 (Standard)
```

**Netz:** `start.sh` und `update.sh` binden standardmäßig an **`0.0.0.0`** — der Dienst ist damit im **lokalen Netz** unter `http://<IP-des-Geräts>:8000` erreichbar (und weiterhin auf demselben Gerät unter [http://127.0.0.1:8000](http://127.0.0.1:8000)).

Nur auf diesem Gerät lauschen (kein Zugriff von anderen Rechnern im WLAN):

```bash
HOST=127.0.0.1 bash start.sh
# bzw. nach Update:
HOST=127.0.0.1 bash update.sh
```

Anderer Port:

```bash
PORT=9000 bash start.sh
```

Wenn aus dem LAN nichts erreichbar ist: **Firewall** auf dem Gerät / LXC / Proxmox prüfen (Port **8000/tcp**).

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

**Kiosk-Nachricht:** unter Admin → „News“ / `/admin/news` — erscheint oben auf allen Kiosk-Seiten. Leer speichern stellt den Standard-Hinweis wieder her.

## Entwicklung (Windows / Linux)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Privates GitHub-Repository

Lokal committen, dann z. B. mit [GitHub CLI](https://cli.github.com/):

```bash
gh auth login
gh repo create termux-kasse --private --source=. --remote=origin --push
```

Oder Repo auf github.com als **Private** anlegen und `git remote add origin …` / `git push -u origin main`.
