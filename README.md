# Termux-Shopkasse

Lokal laufende **Shopkasse** für kleine Gruppen: Mitglieder buchen Artikel am Kiosk, Saldo und Abrechnungen laufen über eine **SQLite**-Datenbank. **Keine Cloud** — die App spricht im Betrieb keine externen Dienste an; Styles und Skripte kommen aus dem Projekt (`/static`), Internet ist nur für Installation und Updates nötig.

**Aktuelle Version:** **1.0.0** (Git-Tag [`v1.0.0`](https://github.com/chrishaef/termux-kasse/releases/tag/v1.0.0)) — GitHub-Release: [anlegen](https://github.com/chrishaef/termux-kasse/releases/new?tag=v1.0.0) (einmal `gh auth login` oder im Browser veröffentlichen).

---

## Inhalt

1. [Funktionen](#funktionen)  
2. [Technik](#technik)  
3. [Installation auf Android (Termux)](#installation-auf-android-termux)  
4. [Erster Start und Betrieb](#erster-start-und-betrieb)  
5. [Netzwerk (LAN vs. nur Gerät)](#netzwerk-lan-vs-nur-gerät)  
6. [Daten, Backup, Umgebungsvariablen](#daten-backup-umgebungsvariablen)  
7. [Updates (`update.sh`)](#updates-updatesh)  
8. [Admin-Bereich](#admin-bereich)  
9. [Entwicklung (Windows / Linux / macOS)](#entwicklung-windows--linux--macos)  
10. [Repository und Releases bei GitHub](#repository-und-releases-bei-github)  
11. [Lizenz / Hinweise](#lizenz--hinweise)

---

## Funktionen

| Bereich | Kurzbeschreibung |
|--------|-------------------|
| **Kiosk** | Gruppe wählen → Nutzer → Kontostand, letzte Abrechnung, Artikel mit einem Tipp buchen (Klicksound + visuelles Feedback) |
| **Kiosk Extra** | Top-Ten-Seite, Preisliste, automatischer Preisliste-Bildschirmschoner bei Inaktivität |
| **Warnstufen** | 3 konfigurierbare Schwellen mit individuellen Texten und Sounds pro Stufe (einmalig beim Erreichen der nächsten Stufe) |
| **Admin** | Login, Gruppen, Nutzer, Artikel inkl. Sortierung und Bearbeiten, Kiosk-Nachricht |
| **Abrechnung** | Geführter Ablauf: Gruppe/Nutzer wählen → offene Posten prüfen → Zahlungseingang bestätigen → Konten begleichen, **PDF** und **XLSX** exportieren |
| **Jahresabschluss** | Admin unter Abrechnungen: Archiv **PDF**, **XLSX** und **ZIP** nach `data/jahresabschluss/`; löscht nur **beglichene** Abrechnungen inkl. zugehöriger Buchungszeilen (**offene Posten und Kontostände bleiben**). Erfordert **Master-Passwort** |
| **Statistik** | Zeitraum- und Gruppenfilter, Toplisten/Auswertung, Export als **PDF** und **XLSX** |
| **Backup** | Datenbank **exportieren/importieren**; zusätzlich **Daten-Reset** (Master-Passwort): alle Buchungen und Abrechnungen löschen, **Nutzer, Gruppen und Artikel** bleiben |

---

## Technik

- **Backend:** Python 3, **FastAPI**, **Uvicorn**
- **Datenbank:** SQLite (`kasse.db`)
- **Templates:** Jinja2, **Pico.css** + eigenes **`app/static/kasse.css`**
- **Export:** openpyxl (XLS), PyFPDF 1.x / `fpdf` (PDF, ohne Pillow)
- **Tests:** pytest

---

## Installation auf Android (Termux)

### 1. Termux installieren

- **Empfohlen:** [Termux auf F-Droid](https://f-droid.org/packages/com.termux/) — aktuelle Builds, gut gepflegt.  
- Alternativ Releases von den [Termux-Entwicklern auf GitHub](https://github.com/termux/termux-app/releases).  
- Die Play-Store-Version von Termux ist veraltet und wird für neue Nutzung **nicht** empfohlen.

Nach der Installation Termux öffnen und einmal die Basis aktualisieren:

```bash
pkg update && pkg upgrade -y
```

### 2. Git und Python (für Klonen und Server)

Entweder **manuell**:

```bash
pkg install -y git python
```

oder beim ersten Lauf **`bash update.sh`** mitinstallieren lassen (siehe [Updates](#updates-updatesh)) — das Skript erkennt Termux und nutzt `pkg install`.

### 3. Privates GitHub-Repository klonen

Du brauchst ein **privates** (oder öffentliches) Repo mit diesem Code und **Lesezugriff** vom Tablet.

#### Option A: HTTPS mit Personal Access Token (PAT)

1. Auf GitHub: **Settings → Developer settings → Personal access tokens** — Token mit mindestens **repo** (klassisch) bzw. passenden Rechten für private Repos (feingranular).  
2. Auf dem Gerät nur im Termux-Fenster nutzen; Token **nicht** in Screenshots oder geteilten Logs speichern.  
3. Klonen (URL und Benutzername anpassen):

```bash
cd ~
git clone https://github.com/DEIN_USER/DEIN_REPO.git termux-kasse
```

Git fragt nach **Benutzername** (GitHub-Login oder nur der Benutzername) und **Passwort** — hier das **Token** eintragen, nicht das GitHub-Passwort.

#### Option B: SSH-Schlüssel auf dem Gerät

1. Schlüssel erzeugen (Enter für Standardpfad, optional Passphrase):

```bash
ssh-keygen -t ed25519 -C "termux-tablet"
```

2. Öffentlichen Schlüssel anzeigen und kopieren:

```bash
cat ~/.ssh/id_ed25519.pub
```

3. Auf GitHub: **Settings → SSH and GPG keys → New SSH key** — einfügen.  
4. Klonen:

```bash
cd ~
git clone git@github.com:DEIN_USER/DEIN_REPO.git termux-kasse
```

Erster Verbindungsaufbau bestätigt die Host-Key-Frage mit **yes**.

#### Öffentliches Repository

Dann reicht eine normale HTTPS-URL ohne Token:

```bash
git clone https://github.com/DEIN_USER/DEIN_REPO.git termux-kasse
```

### 4. Projektordner

```bash
cd ~/termux-kasse
```

Alle folgenden Befehle (`start.sh`, `update.sh`) beziehen sich auf diesen Ordner (Projektroot).

**pip / Termux:** In `requirements.txt` gilt:

- **Kein** `uvicorn[standard]` — die Extras ziehen u. a. **watchfiles** (Rust/Maturin) nach; unter **Android (aarch64)** schlägt das oft fehl (`Target triple not supported`). Normales **uvicorn** reicht hier.
- **FastAPI 0.99.x** und **Pydantic v1** — neuere FastAPI-Versionen brauchen **pydantic-core** (ebenfalls Rust). Ohne vorgefertigtes Rad für `cpython-313-aarch64-linux-android` muss pip kompilieren, was in Termux scheitert. Pydantic v1 ist für diese Kasse ausreichend.
- **httpx unter 0.28** — passt zur mitgelieferten **Starlette 0.27**-Testumgebung; nur für Entwickler-Tests relevant, nicht für den Kiosk-Betrieb.
- **passlib** (PBKDF2) statt **bcrypt** — kein Rust-Compiler nötig; alte bcrypt-Hashes in der DB werden weiter erkannt, **wenn** optional `bcrypt` installiert ist (sonst Passwort im Admin neu setzen).
- **fpdf** (PyFPDF 1.7) statt **reportlab** / **fpdf2** — **fpdf2** zieht **Pillow** als feste Abhängigkeit; das klassische **fpdf**-Paket nicht.

---

## Erster Start und Betrieb

### Schnellstart mit Update-Skript (empfohlen auf dem Tablet)

Installiert bei Bedarf Pakete, holt den neuesten Stand, richtet die virtuelle Umgebung ein und startet den Server **im Hintergrund**:

```bash
cd ~/termux-kasse
bash update.sh
```

Log-Ausgabe: `server.log` im Projektroot, Prozess-ID: `.server.pid`.

### Nur vordergrund (zum Testen oder Debuggen)

```bash
cd ~/termux-kasse
bash start.sh --sync    # einmalig: venv + pip
bash start.sh           # Server im Vordergrund, Strg+C beendet
```

### Admin-Zugang

Im Browser auf demselben Gerät (oder im LAN, siehe unten):

- Login unter [http://127.0.0.1:8000/admin/login](http://127.0.0.1:8000/admin/login) nur per Passwort (kein Benutzername).
- Es gibt zwei gueltige Passwoerter:
  - **Admin-Passwort** (standardmaessig `admin`), im Admin-Bereich unter `/admin/password` aenderbar.
  - **Master-Passwort** aus Datei `.admin_master_password` (standardmaessig `master`), nur per Dateisystem aenderbar.

Standardport ist **8000** (änderbar mit `PORT`, siehe nächster Abschnitt).

---

## Netzwerk (LAN vs. nur Gerät)

`start.sh` und `update.sh` setzen standardmäßig:

- **`HOST=0.0.0.0`** — Server lauscht auf allen Schnittstellen; im **WLAN** erreichbar unter `http://<IP-des-Tablets>:8000` (IP z. B. unter Android *WLAN-Details* oder mit `ip addr` / `ifconfig` in Termux).  
- **`PORT=8000`**

Nur auf diesem Gerät (kein Zugriff von anderen Rechnern im Netz):

```bash
HOST=127.0.0.1 bash start.sh
# bzw. nach Änderungen:
HOST=127.0.0.1 bash update.sh
```

Anderer Port:

```bash
PORT=9000 bash start.sh
```

Wenn aus dem LAN nichts antwortet: **Firewall** auf dem Gerät, VPN oder Router prüfen; für den Standardport **TCP 8000** freigeben bzw. testen.

---

## Daten, Backup, Umgebungsvariablen

| Thema | Details |
|--------|---------|
| **Datenbank** | `data/kasse.db` relativ zum Projektroot |
| **Datenverzeichnis** | Überschreibbar mit **`KASSE_DATA_DIR`** (absoluter Pfad zum Ordner; die Datei heißt darin weiter `kasse.db`) |
| **Session-Secret** | Datei **`.secret_key`** im Projektroot (von Git ignoriert) oder Umgebungsvariable **`KASSE_SECRET_KEY`** |
| **Master-Passwort** | Datei **`.admin_master_password`** im Projektroot (Inhalt = Passwort, Standard `master`) oder alternativer Dateipfad via **`KASSE_MASTER_PASSWORD_FILE`** |
| **Backup (Datei)** | Ordner `data/` kopieren oder nur `kasse.db` sichern — idealerweise bei **gestopptem** Server (`kill $(cat .server.pid)` im Projektroot oder Prozess beenden), damit die DB nicht mitten im Schreiben kopiert wird |
| **Backup (Admin-UI)** | Unter `/admin/backup`: Datenbank als `.db` exportieren und wieder importieren (Import ersetzt die aktuelle DB) |
| **Jahresabschluss-Archive** | Ordner **`jahresabschluss/`** unter `KASSE_DATA_DIR` (neben `kasse.db`): gespeicherte PDF-, XLSX- und ZIP-Dateien pro Abschluss |

---

## Updates (`update.sh`)

Wenn das Tablet kurz online ist (z. B. Handy-Hotspot):

```bash
cd ~/termux-kasse
bash update.sh
```

Ablauf in Kurzform:

1. **System:** Prüft `git` und Python; unter **Termux** Installation per `pkg`, unter **Debian/Ubuntu** per `apt-get` (optional mit `sudo`).  
2. **`git pull --ff-only`**  
3. Virtuelle Umgebung **`.venv`** anlegen/verwenden, **`pip install -r requirements.txt`**  
4. Laufenden Uvicorn beenden (`.server.pid` und/oder `pkill`) und Server wieder **im Hintergrund** starten → **`server.log`**

Optionen:

```bash
bash update.sh --no-restart           # kein Neustart (nur Systemcheck / pull / pip)
bash update.sh --no-system-install    # keine Paketinstallation (bricht ab, wenn git/Python fehlt)
```

Läuft die Kasse nur mit `bash start.sh` im Vordergrund, gibt es keine `.server.pid` — dann beendet `update.sh` passende `uvicorn`-Prozesse per `pkill`, oder du beendest vorher mit **Strg+C** und startest danach manuell neu.

---

## Admin-Bereich

Nach dem Login (`/admin`):

- **Gruppen, Nutzer, Artikel** pflegen (inkl. manueller Reihenfolge via Pfeile und Bearbeiten-Ansichten)  
- **Abrechnungen** (`/admin/settlements`): Liste vergangener Abrechnungen mit XLS/PDF; neue Abrechnung über **„Neue Abrechnung starten“** (Gruppe/Nutzer wählen → Beträge prüfen → Zahlungseingang bestätigen → PDF); **Jahresabschluss** mit Archivdownload (Master-Passwort)  
- **Statistik** (`/admin/statistics`): Zeitraum + Nutzergruppe filtern, Toplisten sehen, PDF/XLSX herunterladen  
- **Warnstufen** (`/admin/debt-thresholds`): Schwellen und Meldungstexte für Kiosk-Warnungen pflegen  
- **Kiosk-Nachricht** (`/admin/news`): Text oben auf allen Kiosk-Seiten; leer speichern stellt den Standardhinweis wieder her  
- **Backup** (`/admin/backup`): Datenbank exportieren/importieren; optional **Daten-Reset** (alle Buchungen und Abrechnungen löschen, Stammdaten bleiben; Master-Passwort)

Hinweis: **Kontostände** ergeben sich nur aus Buchungen; eine manuelle Saldo-Korrektur im Nutzer-Edit gibt es nicht (dazu Daten-Reset oder Jahresabschluss-Archiv nutzen).

---

## Entwicklung (Windows / Linux / macOS)

```bash
git clone https://github.com/DEIN_USER/DEIN_REPO.git
cd DEIN_REPO
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Für Tests kann `KASSE_DATA_DIR` auf ein temporäres Verzeichnis zeigen (siehe `tests/conftest.py`).

---

## Repository und Releases bei GitHub

Öffentliches Projekt: [github.com/chrishaef/termux-kasse](https://github.com/chrishaef/termux-kasse).

**Neues privates Repo und lokaler Ordner:**

```bash
gh auth login
gh repo create termux-kasse --private --source=. --remote=origin --push
```

**Oder** auf [github.com](https://github.com) ein Repository als **Private** anlegen, dann lokal:

```bash
git remote add origin https://github.com/DEIN_USER/DEIN_REPO.git
git push -u origin main
```

Branchname ggf. an euren Standard anpassen (`main` / `master`).

### Versionierung und Releases

- Aktueller Git-Tag: **v1.0.0** — Übersicht: [Tag v1.0.0](https://github.com/chrishaef/termux-kasse/releases/tag/v1.0.0).  
- **GitHub-Release** (Titel + Release Notes im UI): [Neues Release mit Tag v1.0.0](https://github.com/chrishaef/termux-kasse/releases/new?tag=v1.0.0) öffnen, Titel z. B. `Termux-Shopkasse 1.0.0`, Beschreibung einfügen, *Publish release*.  
- **GitHub CLI** (einmalig `gh auth login`):  
  `gh release create v1.0.0 --title "Termux-Shopkasse 1.0.0" --generate-notes`

**v1.0.0** (Kurzüberblick): Jahresabschluss mit Archiv (PDF/XLSX/ZIP), Backup-Daten-Reset, Kiosk-/Admin-Verbesserungen (Passwort-Login, Schwellen, Footer, Nutzerkopf-Layout), Finanzübersicht netto, ohne manuelle Kontostand-Korrektur im Nutzer-Edit.

---

## Lizenz / Hinweise

Nutzt u. a. **Pico.css** (MIT), **FastAPI**, **openpyxl**, **fpdf** — Lizenzbedingungen der jeweiligen Pakete beachten. Die Kiosk-Oberfläche nutzt eigene statische Assets unter `app/static/` (lokal eingebunden).
