# Termux-Shopkasse

Lokal laufende **Shopkasse** für kleine Gruppen: Mitglieder buchen Artikel am Kiosk, Saldo und Abrechnungen laufen über eine **SQLite**-Datenbank. **Keine Cloud** — Buchungen, Kontostände und Abrechnungen laufen lokal; Styles und Skripte kommen aus dem Projekt (`/static`). Internet wird nur für Installation, Updates und den optionalen Online-/Versionscheck genutzt.

**Aktuelle Version:** **1.4.0** (Git-Tag [`v1.4.0`](https://github.com/chrishaef/termux-kasse/releases/tag/v1.4.0)) — GitHub-Release: [anlegen](https://github.com/chrishaef/termux-kasse/releases/new?tag=v1.4.0) (einmal `gh auth login` oder im Browser veröffentlichen).

**Zugehörige Android-Kiosk-App:** [`chrishaef/kiosk-app`](https://github.com/chrishaef/kiosk-app) (WebView-Wrapper, Vollbild/Kiosk-Steuerung, PIN/Admin-Menü).

---

## Inhalt

1. [Funktionen](#funktionen) — [Shop/Kiosk](#shop-und-kiosk-im-detail) · [Abrechnung](#abrechnung-im-detail) · [Statistik](#statistik-im-detail) · [Jahresabschluss](#jahresabschluss-im-detail)  
2. [Technik](#technik)  
3. [Installation auf Android (Termux)](#installation-auf-android-termux)  
4. [Start und Betrieb (`run.sh`)](#start-und-betrieb-runsh)  
5. [Android-Einrichtung (Install + Autostart + Widgets)](#android-einrichtung-install--autostart--widgets)  
6. [Schnelle Inbetriebnahme auf Android-Tablet (Kiosk)](#schnelle-inbetriebnahme-auf-android-tablet-kiosk)  
7. [Netzwerk (LAN vs. nur Gerät)](#netzwerk-lan-vs-nur-gerät)  
8. [Daten, Backup, Umgebungsvariablen](#daten-backup-umgebungsvariablen)  
9. [Admin-Bereich](#admin-bereich)  
10. [Systemstatus, Online-Erkennung und Update-Flow](#systemstatus-online-erkennung-und-update-flow)  
11. [Entwicklung (Windows / Linux / macOS)](#entwicklung-windows--linux--macos)  
12. [Repository und Releases bei GitHub](#repository-und-releases-bei-github)  
13. [Lizenz / Hinweise](#lizenz--hinweise)

---

## Funktionen

| Bereich | Kurzbeschreibung |
|--------|-------------------|
| **Kiosk** | Gruppe wählen → Nutzer → Kontostand, letzte Abrechnung, Artikel mit einem Tipp buchen (Klicksound + visuelles Feedback) |
| **Kiosk Extra** | Top-Ten-Seite (umschaltbar nach Buchungen oder Zahlungen), Preisliste, automatischer Preisliste-Bildschirmschoner bei Inaktivität |
| **Warnstufen** | 3 konfigurierbare Schwellen mit individuellen Texten und Sounds pro Stufe (einmalig beim Erreichen der nächsten Stufe) |
| **Admin** | Login, Gruppen, Nutzer, Artikel inkl. Sortierung und Bearbeiten, Kiosk-Nachricht |
| **Abrechnung** | Geführter Ablauf: Gruppe/Nutzer wählen → offene Posten prüfen → Zahlungseingang bestätigen → Konten begleichen, **PDF** und **XLSX** exportieren |
| **Jahresabschluss** | Admin unter Abrechnungen: erstellt **PDF**, **XLSX** und **ZIP** im Archiv `data/jahresabschluss/` (immer nur der neueste Abschluss bleibt gespeichert); löscht nur **beglichene** Abrechnungen inkl. zugehöriger Buchungszeilen (**offene Posten und Kontostände bleiben**). Erfordert **Master-Passwort** |
| **Statistik** | Zeitraum- und Gruppenfilter, Toplisten/Auswertung, Export als **PDF** und **XLSX** |
| **Backup** | Datenbank **exportieren/importieren**; zusätzlich **System Reset** (Master-Passwort): alle Buchungen und Abrechnungen löschen, **Nutzer, Gruppen und Artikel** bleiben |

### Shop und Kiosk im Detail

Die **Shopkasse** ist eine **Vertrauenskasse auf Kontobasis**: Es gibt keine Warenkorb-Session und keinen Bezahlvorgang am Gerät — stattdessen bucht das Mitglied am Kiosk einen Artikel, und der Betrag wird als **Buchung** auf dem **persönlichen Konto** verbucht. Die Kernfunktionen (Buchung, Saldo, Abrechnung) laufen vollständig lokal in **SQLite**.

**Buchungen, offene Posten, Saldo**

- Jeder Kauf legt eine Zeile im Kontobuch (`ledger_entries`) an (Artikel, Betrag, Zeitstempel).
- Der **Kiosk-Kontostand** ist die Summe aller Buchungen, die noch **keiner Abrechnung zugeordnet** sind („offene Posten“). Eine **Abrechnung** im Admin fasst diese Posten zusammen, legt einen Abrechnungsdatensatz an und **schließt** die zugehörigen Buchungen ab — der offene Saldo sinkt entsprechend (siehe Spalte **Abrechnung** in der Tabelle oben).
- In der Oberfläche werden **Schulden** und **Guthaben** farblich unterschieden; die **Warnstufen** beziehen sich auf den **internen** offenen Saldo (höhere Schulden → höhere Stufe).

**Ablauf am Kiosk**

1. **Startseite** (`/`): Nutzergruppen zur Auswahl (Reihenfolge wie im Admin unter Gruppen).
2. **Gruppe** (`/g/<id>`): Mitglieder dieser Gruppe (Sortierung wie im Admin).
3. **Nutzer** (`/u/<id>`): Kopfbereich mit **Kontostand**, Kurzinfo zur **letzten Abrechnung** (Datum, optional Notiz), ggf. **Warnbanner** nach den konfigurierten Schwellen. Darunter erscheinen nur **aktive** Artikel als große Buttons; inaktive Artikel sind im Kiosk unsichtbar.

**Buchen und Feedback**

- Ein Klick auf einen Artikel bucht **genau eine Einheit** und lädt die Nutzerseite per Formular-POST neu (klassisches Webverhalten, gut für Tablets).
- **Klicksound** und kurzes **visuelles Aufleuchten** des Buttons bestätigen die Buchung.
- **Warnsounds**: Steigt durch den **nächsten** Kauf die **Warnstufe** (weil der offene Saldo eine Schwelle überschreitet), wird **zuerst** der Sound dieser Stufe abgespielt, **danach** wird gebucht. So bleibt der Hinweis an der Schwelle hörbar, ohne jeden einzelnen Kauf mit Warnsound zu überladen.
- Beim **Seitenaufruf** (z. B. Lesezeichen oder Zurück im Browser) kann eine Stufe **einmal** signalisiert werden, wenn sie seit dem letzten Besuch dieses Nutzers gestiegen ist (Merker im Browser-`localStorage` pro Nutzer).

**Top Ten** (`/top-ten`)

- Die Seite bietet zwei Ansichten: **„Nach Buchungen“** und **„Nach Zahlungen“**.
- Beide Ansichten zeigen immer die **Top 10** über die gesamte Laufzeit (auch bereits abgerechnete Buchungen).
- In der Tabelle stehen bewusst nur **Rang, Nutzer und Gruppe** (keine Mengen- oder Euro-Spalten), damit die Anzeige am Kiosk kompakt bleibt.
- Sortierung:
  - **Nach Buchungen**: zuerst Anzahl Buchungen, dann Umsatz, dann Name.
  - **Nach Zahlungen**: zuerst Umsatz, dann Anzahl Buchungen, dann Name.

**Preisliste und automatischer Wechsel bei Untätigkeit**

- **Preisliste** (`/preisliste`): Alle **aktiven** Artikel mit Preis; geeignet als Schaukasten am Kiosk.
- **Ruhemodus**: Ohne Bedienung springt die Anzeige von einer **Buchungsseite** (`/u/…`) nach **30 Sekunden** zurück zur **Gruppenauswahl** (`/`). Von **allen anderen** Kiosk-Seiten (z. B. Gruppe, Top Ten) wechselt sie nach **60 Sekunden** auf die **Preisliste** — wirkt wie ein einfacher Bildschirmschoner mit Preisen.
- Auf der Preisliste führt ein **Tipp auf den freien Bereich** (oder eine Taste) zurück zum **Kiosk-Start**.

**Hinweise für Betreuer**

- **Admin** ohne URL tippen: Im Header das **Logo** **fünfmal** innerhalb von etwa **2,2 Sekunden** antippen — dann öffnet sich `/admin` (siehe `app/templates/base.html`).
- **Kiosk-Nachricht** (Admin): Erscheint oben auf den Kiosk-Seiten als Hinweis an die Gruppe (z. B. Öffnungszeiten, Sonderpreise).

### Abrechnung im Detail

Unter **`/admin/settlements`** (Menü **Abrechnungen**) läuft die Abwicklung **pro Nutzer** und **für den gesamten offenen Saldo** dieses Nutzers — es gibt keinen Teilbetrag und keinen Zeitraum-Filter in der Oberfläche: alle noch nicht abgerechneten Buchungszeilen werden in **einem** Schritt einer neuen Abrechnung zugeordnet.

**Ablauf**

1. **„Neue Abrechnung starten“** (`/admin/settlements/start`): Nutzergruppe und Mitglied wählen; der angezeigte Betrag entspricht der Summe aller **offenen** `ledger_entries` (gleiche Logik wie der Kiosk-Saldo).
2. **Kontrolle & Quittung** (`/admin/settlements/confirm`):  
   - Kasten **„Bisher abgerechnet“**: Summe und Anzahl aller **früheren** Abrechnungen dieses Nutzers.  
   - Kasten **„Jetzt offen“**: Summe der **aktuell** beglichenen Posten.  
   - Tabelle **„Offene Posten (zusammengefasst)“**: identische Artikel mit gleichem Einzelbetrag werden zu Zeilen **Anzahl × Bezeichnung, Einzelpreis, Summe** zusammengefasst (entspricht der späteren PDF-/XLSX-Logik).
3. **Zahlungseingang**: Die Checkbox **„Betrag erhalten“** ist Pflicht — ohne Häkchen wird nichts gebucht (`received_confirmed` im Backend).
4. Nach dem Speichern: Seite **„PDF wird geladen“** — ein eingebetteter Aufruf startet den **PDF-Download** automatisch; gibt es Probleme, reicht der Link **„PDF jetzt herunterladen“**. Nach etwa **1,4 Sekunden** erfolgt die **Weiterleitung** zurück zur **Abrechnungsübersicht**.

**Liste und Export**

- Die Übersicht listet die **letzten 100** Abrechnungen (neueste zuerst) mit Datum, Gruppe, Nutzer und Gesamtbetrag.
- Zu jeder Abrechnung gibt es erneut **PDF** und **XLSX** (`/admin/settlements/<id>/pdf` bzw. `…/xlsx`); die Dateinamen folgen dem Muster `Abrechnung_<Nutzername>_<Datum>.pdf` / `.xlsx` (Sonderzeichen werden abgesichert).

**Randfälle**

- Hat ein Nutzer **keine** offenen Posten, verweigert die Bestätigungsseite die Anzeige und leitet mit Fehlerhinweis zum Start zurück.

### Statistik im Detail

Unter **`/admin/statistics`** wertet die App **Buchungen** (`ledger_entries`) nach **Zeit** und optional **Nutzergruppe** aus — **unabhängig davon**, ob eine Buchung schon zu einer Abrechnung gehört oder noch offen ist. Maßgeblich ist allein der **Zeitstempel** der Buchung (`created_at`).

**Filter**

- **Von** / **Bis** (optional): Datum im Format **YYYY-MM-DD**. Intern: Beginn am **Tagesanfang** des Von-Datums, Ende am **Tagesende** des Bis-Datums.
- **Nutzergruppe** (optional): nur Mitglieder dieser Gruppe; ohne Auswahl **alle** Gruppen.

**Inhalt der Auswertung**

- **Gesamtkennzahlen** im gewählten Zeitraum: Anzahl Buchungen, Anzahl **unterschiedlicher** Nutzer mit mindestens einer Buchung, Summe der Beträge.
- **Nutzer-Topliste**: pro Person Anzahl Buchungen, Summe in Euro/Cent sowie eine **Kurz-Zusammenfassung** der gekauften Positionen (z. B. `3× Cola, 2× Schokoriegel` — Häufigkeiten absteigend). Sortierung: **höchster Umsatz** zuerst, bei Gleichstand **mehr Buchungen**, dann Name.
- **Artikelstatistik**: verkaufte Positionen **aggregiert** (gleiche Artikel und gleicher Einzelpreis zu Mengen und Summen — vergleichbar mit der Abrechnungstabelle).

**Export**

- **PDF** und **XLSX** nutzen dieselben Filter wie die Seite (Query-Parameter `start`, `end`, `group_id`); der Download-Dateiname ist fest **`Statistik_Zeitraum`**.pdf bzw. .xlsx (ohne Datumszusatz im Namen — der Inhalt entspricht aber den gewählten Filtern).

### Jahresabschluss im Detail

Unter **`/admin/settlements/year-end`** (von der Abrechnungsübersicht aus erreichbar) liegt ein **sicherheitskritischer** Vorgang: Es werden **nur** bereits **abgeschlossene** Abrechnungen samt ihrer Buchungszeilen aus der Datenbank entfernt; **offene** Buchungen und damit die **Kontostände am Kiosk** bleiben bestehen.

**Voraussetzungen**

- Anmeldung im Admin reicht nicht: Es wird das **Master-Passwort** verlangt (Konfiguration über **`.master_pwd`** bzw. `KASSE_MASTER_PASSWORD_FILE` — siehe Abschnitt [Daten, Backup, Umgebungsvariablen](#daten-backup-umgebungsvariablen)).
- Zusätzlich eine **explizite Bestätigung**, dass der Schritt **irreversibel** ist (Checkbox im Formular).

**Was beim Auslösen passiert**

1. **Snapshot** (`year_end_snapshot`): Kennzahlen **unmittelbar vor** der Löschung — globale Zähler und Summen für alle / offene / abgerechnete Buchungen und für Abrechnungen; **Nutzer-Tabelle** mit offenen Beträgen, Anzahl Abrechnungen, Summen und Lebenszeit-Buchungsstatistik; **Artikelübersicht** über die **gesamte** Historie (ohne Datumsfilter, für den Archivbericht).
2. Daraus werden **PDF** und **XLSX** generiert.
3. Beide Dateien werden im Ordner **`jahresabschluss/`** unter dem Datenverzeichnis abgelegt (`data/jahresabschluss/` oder `KASSE_DATA_DIR/jahresabschluss/`), Dateiname z. B. `Jahresabschluss_<ISO-Zeitstempel>.pdf` / `.xlsx`.
4. Gleichzeitig wird ein **ZIP** (enthält dieselben PDF- und XLSX-Dateien) erzeugt und im Archivordner gespeichert.
5. Anschließend **`purge_settled_ledger_and_settlements`**: SQL löscht alle `ledger_entries` mit gesetzter `settlement_id` sowie **alle** Zeilen in **`settlements`**. Zeilen mit `settlement_id IS NULL` (offene Käufe) werden **nicht** angerührt.
6. Vor dem Schreiben eines neuen Jahresabschlusses wird das Archiv bereinigt, sodass dort jeweils nur der **aktuellste** Abschluss liegt.

**Abgrenzung**

- **Jahresabschluss** ≠ **System Reset** (`/admin/backup`): Der Reset (ebenfalls Master-Passwort) entfernt **alle** Buchungen und Abrechnungen inklusive **offener** Posten — Kontostände werden null, Stammdaten bleiben. Der Jahresabschluss **kürzt nur die Historie beglichener** Vorgänge.

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

Installiere die Basis-Tools zuerst manuell:

```bash
pkg install -y git python
```

`run.sh` kommt **erst nach dem Klonen** zum Einsatz, weil es im Projektordner liegt.

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

Alle folgenden Befehle (`install.sh`, `run.sh`, `stop.sh`, `uninstall.sh`) beziehen sich auf diesen Ordner (Projektroot).

**pip / Termux:** In `requirements.txt` gilt:

- **Kein** `uvicorn[standard]` — die Extras ziehen u. a. **watchfiles** (Rust/Maturin) nach; unter **Android (aarch64)** schlägt das oft fehl (`Target triple not supported`). Normales **uvicorn** reicht hier.
- **FastAPI 0.99.x** und **Pydantic v1** — neuere FastAPI-Versionen brauchen **pydantic-core** (ebenfalls Rust). Ohne vorgefertigtes Rad für `cpython-313-aarch64-linux-android` muss pip kompilieren, was in Termux scheitert. Pydantic v1 ist für diese Kasse ausreichend.
- **httpx unter 0.28** — passt zur mitgelieferten **Starlette 0.27**-Testumgebung; nur für Entwickler-Tests relevant, nicht für den Kiosk-Betrieb.
- **passlib** (PBKDF2) statt **bcrypt** — kein Rust-Compiler nötig; alte bcrypt-Hashes in der DB werden weiter erkannt, **wenn** optional `bcrypt` installiert ist (sonst Passwort im Admin neu setzen).
- **fpdf** (PyFPDF 1.7) statt **reportlab** / **fpdf2** — **fpdf2** zieht **Pillow** als feste Abhängigkeit; das klassische **fpdf**-Paket nicht.

---

## Start und Betrieb (`run.sh`)

### Schnellstart (empfohlen auf dem Tablet)

```bash
cd ~/termux-kasse
bash run.sh
```

`run.sh` uebernimmt den kompletten Ablauf:

1. prueft/ installiert `git` und Python bei Bedarf
2. prueft, ob GitHub (`origin`) erreichbar ist
3. wenn erreichbar: `git fetch --tags --prune origin` + `git pull --ff-only` + `pip install -r requirements.txt`
4. wenn nicht erreichbar: Start ohne Update mit Hinweis
5. startet Uvicorn im Hintergrund

Log-Datei: `server.log`  
PID-Datei: `.server.pid`

Server sauber stoppen:

```bash
cd ~/termux-kasse
bash stop.sh
```

### Admin-Zugang

Im Browser auf demselben Gerät (oder im LAN, siehe unten):

- Login unter [http://127.0.0.1:8000/admin/login](http://127.0.0.1:8000/admin/login) nur per Passwort (kein Benutzername).
- Es gibt zwei gueltige Passwoerter:
  - **Admin-Passwort** (standardmaessig `admin`), im Admin-Bereich unter `/admin/password` aenderbar.
  - **Master-Passwort** aus Datei `.master_pwd` (standardmaessig `master`), nur per Dateisystem aenderbar.

Standardport ist **8000** (änderbar mit `PORT`, siehe nächster Abschnitt).

---

## Android-Einrichtung (Install + Autostart + Widgets)

Fuer einen stabilen Betrieb werden **Termux** und **Termux:Boot** benoetigt.  
**Termux:Widget** ist je nach Termux-Build optional (wenn Widget-Eintraege fehlen, installieren).

### Einrichten

1. **Termux** installieren und einmal oeffnen
2. **Termux:Boot** installieren und einmal oeffnen
3. Optional: **Termux:Widget** installieren und einmal oeffnen
4. Im Projekt ausfuehren:

```bash
cd ~/termux-kasse
bash install.sh
```

Das erstellt automatisch:

- `~/.termux/boot/start-shopkasse.sh` (ruft `run.sh` auf)
- `~/.shortcuts/shopkasse-start.sh`
- `~/.shortcuts/shopkasse-stop.sh`
- `~/.shortcuts/shopkasse-status.sh`
- `~/.termux/termux.properties`: setzt `allow-external-apps = true`

### Android-Einstellungen

- Akku-Optimierung fuer **Termux** und **Termux:Boot** deaktivieren
- Hintergrundstart/Autostart erlauben (je nach Hersteller unterschiedlich)
- Tablet neu starten und `server.log` pruefen

---

## Schnelle Inbetriebnahme auf Android-Tablet (Kiosk)

Dieser Ablauf ist fuer ein **neues oder zurueckgesetztes Tablet** gedacht und fuehrt bis zum stabilen Kiosk-Betrieb.

### Quickstart (Copy/Paste)

```bash
pkg update && pkg upgrade -y
pkg install -y git python
cd ~
git clone https://github.com/DEIN_USER/DEIN_REPO.git termux-kasse
cd ~/termux-kasse
bash run.sh
```

Danach ist der Shop lokal unter `http://127.0.0.1:8000` erreichbar.

### 1) Erstinbetriebnahme (Schritt fuer Schritt)

1. **Termux installieren** (F-Droid empfohlen) und oeffnen.
2. **Termux aktualisieren**:

```bash
pkg update && pkg upgrade -y
```

3. **Git + Python installieren**:

```bash
pkg install -y git python
```

4. **Repository klonen**:

```bash
cd ~
git clone https://github.com/DEIN_USER/DEIN_REPO.git termux-kasse
cd ~/termux-kasse
```

5. **Erststart mit Installation + Start ueber `run.sh`**:

```bash
bash run.sh
```

`run.sh` installiert beim ersten Lauf ggf. fehlende Python-Abhaengigkeiten und startet danach den Server.

6. **Funktion pruefen**:
   - lokal: `http://127.0.0.1:8000`
   - optional im LAN: `http://<tablet-ip>:8000`

7. **Kiosk-App einrichten** (falls genutzt):
   - App installieren/starten
   - unten rechts 5 Sekunden druecken -> Admin-Menue
   - **Server-Adresse aendern** auf `http://127.0.0.1:8000` (oder LAN-IP)
   - **Verbindung testen** und **Speichern**

### 2) Autostart und Widgets einrichten

1. **Termux:Boot installieren** (F-Droid) und einmal oeffnen.
2. Optional: **Termux:Widget** installieren, falls keine Widget-Eintraege sichtbar sind.
3. Im Projektordner:

```bash
cd ~/termux-kasse
bash install.sh
```

4. Android-Einstellungen setzen:
   - Akku-Optimierung fuer **Termux** und **Termux:Boot** deaktivieren
   - Hintergrundstart/Autostart erlauben
5. Tablet neu starten und pruefen:
   - startet `run.sh` automatisch (Log: `~/termux-kasse/server.log`)?
   - ist der Shop danach unter `http://127.0.0.1:8000` erreichbar?

### 3) Betrieb im Alltag

- Starten (falls nicht per Boot aktiv): `bash run.sh`
- Stoppen: `bash stop.sh`
- Admin: `http://127.0.0.1:8000/admin/login`
- Backups regelmaessig in `/admin/backup` erstellen

---

## Netzwerk (LAN vs. nur Gerät)

`run.sh` setzt standardmäßig:

- **`HOST=0.0.0.0`** — Server lauscht auf allen Schnittstellen; im **WLAN** erreichbar unter `http://<IP-des-Tablets>:8000` (IP z. B. unter Android *WLAN-Details* oder mit `ip addr` / `ifconfig` in Termux).  
- **`PORT=8000`**

Nur auf diesem Gerät (kein Zugriff von anderen Rechnern im Netz):

```bash
HOST=127.0.0.1 bash run.sh
```

Anderer Port:

```bash
PORT=9000 bash run.sh
```

Wenn aus dem LAN nichts antwortet: **Firewall** auf dem Gerät, VPN oder Router prüfen; für den Standardport **TCP 8000** freigeben bzw. testen.

---

## Daten, Backup, Umgebungsvariablen

| Thema | Details |
|--------|---------|
| **Datenbank** | `data/kasse.db` relativ zum Projektroot |
| **Datenverzeichnis** | Überschreibbar mit **`KASSE_DATA_DIR`** (absoluter Pfad zum Ordner; die Datei heißt darin weiter `kasse.db`) |
| **Session-Secret** | Datei **`.secret_key`** im Projektroot (von Git ignoriert) oder Umgebungsvariable **`KASSE_SECRET_KEY`** |
| **Master-Passwort** | Datei **`.master_pwd`** im Projektroot (Inhalt = Passwort, Standard `master`). Beim ersten `run.sh` wird zusätzlich `.master_pwd.example` angelegt. Alternativer Dateipfad via **`KASSE_MASTER_PASSWORD_FILE`** |
| **Backup (Datei)** | Ordner `data/` kopieren oder nur `kasse.db` sichern — idealerweise bei **gestopptem** Server (`bash stop.sh`) |
| **Backup (Admin-UI)** | Unter `/admin/backup`: Backup erstellen (wird im Archiv gespeichert), Import mit Vorschau, Archivansicht mit Download/Loeschen, System Reset |
| **Jahresabschluss-Archive** | Ordner **`jahresabschluss/`** unter `KASSE_DATA_DIR` (neben `kasse.db`): gespeicherte PDF-, XLSX- und ZIP-Dateien des zuletzt erzeugten Jahresabschlusses |
| **System-Backup-Archiv** | Ordner **`system_backups/`** unter `KASSE_DATA_DIR` |

---

## Admin-Bereich

Nach dem Login (`/admin`):

- **Gruppen, Nutzer, Artikel** pflegen (inkl. manueller Reihenfolge via Pfeile und Bearbeiten-Ansichten)  
- **Abrechnungen** (`/admin/settlements`): Liste vergangener Abrechnungen mit XLS/PDF; neue Abrechnung über **„Neue Abrechnung starten“** (Gruppe/Nutzer wählen → Beträge prüfen → Zahlungseingang bestätigen → PDF); **Jahresabschluss** mit Archivdownload (Master-Passwort)  
- **Statistik** (`/admin/statistics`): Zeitraum + Nutzergruppe filtern, Toplisten sehen, PDF/XLSX herunterladen  
- **Warnstufen** (`/admin/debt-thresholds`): Schwellen und Meldungstexte für Kiosk-Warnungen pflegen  
- **Kiosk-Nachricht** (`/admin/news`): Text oben auf allen Kiosk-Seiten; leer speichern stellt den Standardhinweis wieder her  
- **Backup & Recovery & Reset** (`/admin/backup`): Backup erstellen (Archiv), Import mit Vorschau, Archivliste, optional **System Reset** (Master-Passwort)  
- **System-Update** (`/admin/system-update`): Online-/Versionscheck, Start nur mit Master-Passwort, Update-Neustart mit Warteseite und separater Log-Ergebnisseite

Hinweis: **Kontostände** ergeben sich nur aus Buchungen; eine manuelle Saldo-Korrektur im Nutzer-Edit gibt es nicht (dafür System Reset oder Jahresabschluss-Archiv nutzen).

---

## Systemstatus, Online-Erkennung und Update-Flow

Dieser Abschnitt ist bewusst für den Alltag geschrieben: Was sehe ich in der Oberfläche, und was bedeutet es?

### Was bedeutet die Versionsanzeige?

- Auf Startseite und Preisliste steht unten die aktuelle **Version** (mit kurzer Kennung in Klammern).
- Im Admin-Bereich steht derselbe Stand in der Systemübersicht.
- So erkennt ihr schnell, ob das Gerät wirklich auf dem gewünschten Stand läuft.

### Was bedeutet das `online`-Badge?

- Oben rechts im Header erscheint ein grünes **`online`**.
- Das heißt: Das Gerät hat gerade Verbindung zum Update-Server (GitHub).
- Kein Badge heißt in der Regel: aktuell keine Verbindung (z. B. offline ohne Hotspot/WLAN).
- Der Status wird regelmäßig geprüft (etwa minütlich), damit er nicht „hängen bleibt“.

### Was bedeuten `latest`, `outdated`, `unknown`?

- **`latest`**: Alles aktuell.
- **`outdated`**: Es gibt eine neuere Version.
- **`unknown`**: Der Stand konnte gerade nicht geprüft werden (typisch offline).

### Update über Admin (`update / reboot`) – einfacher Ablauf

1. Im Admin-Dashboard auf **`update / reboot`** tippen.
2. Es erscheint eine Vorbereitungsseite mit:
   - Netzwerkstatus,
   - installierter Version,
   - neuester verfügbarer Version,
   - klarer Empfehlung (nur Neustart oder Update + Neustart).
3. Zur Sicherheit muss das **Master-Passwort** eingegeben werden.
4. Das System führt den Vorgang aus und startet den Dienst neu.
5. Danach erscheint eine **eigene Protokollseite** mit den letzten Meldungen.
6. Mit **„Zurück zum System“** zurück ins normale Admin-Menü.

### Update-Protokoll (Log)

- Auf der Vorbereitungsseite seht ihr die letzten bisherigen Meldungen.
- Nach dem Vorgang seht ihr auf der Ergebnisseite die aktuellen Meldungen.
- Der Bereich ist scrollbar, damit mehr Einträge sichtbar sind.

### Automatische Backups – kurz erklärt

- Das System erstellt automatische Backups im **7-Tage-Rhythmus**.
- Sehr alte automatische Backups werden entfernt (älter als 28 Tage).
- Zusätzlich gibt es eine Gesamtgrenze im Archiv, damit der Speicher nicht vollläuft.
- Falls alle Auto-Backups gelöscht wurden:
  - wartet das System kurz (5 Minuten),
  - erstellt dann ein neues Auto-Backup,
  - und läuft danach wieder normal im 7-Tage-Rhythmus weiter.

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

- Aktueller Git-Tag: **v1.4.0** — Übersicht: [Tag v1.4.0](https://github.com/chrishaef/termux-kasse/releases/tag/v1.4.0).
- **GitHub-Release** (Titel + Release Notes im UI): [Neues Release mit Tag v1.4.0](https://github.com/chrishaef/termux-kasse/releases/new?tag=v1.4.0) öffnen, Titel z. B. `Termux-Shopkasse 1.4.0`, Beschreibung einfügen, *Publish release*.
- **GitHub CLI** (einmalig `gh auth login`):  
  `gh release create v1.4.0 --title "Termux-Shopkasse 1.4.0" --generate-notes`
- Änderungsübersicht im Repo: [`CHANGELOG.md`](./CHANGELOG.md)

**v1.4.0** (Kurzüberblick): Artikel-Sichtbarkeit pro Gruppe und getrennte Preisliste-Steuerung ergänzt, Master-Passwort-Datei auf `.master_pwd` vereinheitlicht und Android-/Kiosk-Dokumentation inkl. Repo-Verlinkung erweitert.

---

## Lizenz / Hinweise

Nutzt u. a. **Pico.css** (MIT), **FastAPI**, **openpyxl**, **fpdf** — Lizenzbedingungen der jeweiligen Pakete beachten. Die Kiosk-Oberfläche nutzt eigene statische Assets unter `app/static/` (lokal eingebunden).
