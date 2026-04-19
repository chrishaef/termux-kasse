# Termux-Vertrauenskasse

Lokal laufende Vertrauenskasse (FastAPI, SQLite, Jinja2). Keine CDN-Assets: `pico.min.css` liegt unter `app/static/`.

## Voraussetzungen (Termux auf dem Tablet)

- `pkg install python git`
- Optional: `pkg install curl` (nur falls du Abhängigkeiten manuell laden willst)

## Installation

```bash
cd ~
git clone <DEIN_PRIVATE_CLONE_URL> termux-kasse
cd termux-kasse
bash start.sh --sync   # einmalig: venv + pip install
bash start.sh           # startet uvicorn auf 127.0.0.1:8000
```

Im Browser auf demselben Gerät: [http://127.0.0.1:8000](http://127.0.0.1:8000)

Anderer Port:

```bash
PORT=9000 bash start.sh
```

## Daten & Backup

- SQLite-Datei: `data/kasse.db` (relativ zum Projektroot), außer du setzt `KASSE_DATA_DIR` auf einen absoluten Pfad.
- Session-Secret: `.secret_key` im Projektroot (von Git ignoriert) oder Umgebungsvariable `KASSE_SECRET_KEY`.
- Backup: Ordner `data/` kopieren oder nur `kasse.db` sichern, während der Server **gestoppt** ist.

## Updates (Hotspot / WLAN)

Wenn das Tablet kurz online ist (z. B. Handy-Hotspot), im Projektordner:

```bash
bash update.sh
```

Das Skript führt `git pull --ff-only`, aktualisiert die Python-Pakete, beendet einen zuvor mit `update.sh` gestarteten Server (über `.server.pid`, sonst Fallback per `pkill`) und startet **uvicorn im Hintergrund** neu. Logdatei: `server.log`.

Nur pull + Pakete, **ohne** Neustart (wenn du weiter `start.sh` im Vordergrund nutzen willst):

```bash
bash update.sh --no-restart
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
