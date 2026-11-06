# Entwicklung und Tests

## Lokale Vorschau

Im Projektordner:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DASHBOARD_PASSWORD='eigenes-langes-passwort'
DEMO_MODE=true .venv/bin/python app/server.py
```

`http://127.0.0.1:8088` öffnen und mit dem selbst gewählten Passwort anmelden. Unter „Kameras“ können Beispielkameras gewählt werden. Die Demo steuert keine Hardware und zeigt kein echtes Kamerabild. Für die TV-Ansicht im Dashboard „TV-Ansicht öffnen“ auswählen.

## Automatische Prüfungen

```sh
.venv/bin/python -m unittest discover -s tests -v
node tests/test_tv_navigation.cjs
node tests/test_telemetry_view.cjs
node tests/test_tv_remote.cjs
```

GitHub Actions führt diese Prüfungen für Pull Requests und Änderungen an `main` aus. Der Release-Workflow prüft zusätzlich vor der Image-Veröffentlichung. Die Tests decken unter anderem Anmeldung, Geheimnis-Trennung, Protect-Einrichtung, Telemetrie, Tastennavigation, Installer und Update-Rückwege ab.

## Ergänzende Containerprüfungen

Mit erreichbarer Docker-Engine:

```sh
python3 tests/docker_acceptance.py
python3 tests/docker_acceptance.py --platform linux/arm/v7
python3 tests/cec_acceptance.py
python3 tests/player_acceptance.py
python3 tests/stream_acceptance.py
python3 tests/browser_update_acceptance.py
```

Die Programme bauen eigene Testimages, verwenden eigene Container/Volumes und räumen diese anschließend wieder auf. Container- und ARMv7-Prüfungen sind keine Geräteabnahme. Der CEC-Test verwendet den echten Helfer ohne angeschlossenen Adapter. Die Player-Prüfung verwendet erzeugtes Video und unsichtbare Ausgabe. Der Streamtest nutzt RTSP/RTSPS in einem internen Docker-Netz mit MediaMTX; das Werkzeug gehört nicht zur Produktinstallation.

Das Browser-Update-Labor prüft echte Containerwechsel, Sicherung, fehlerbedingte Rückkehr und Wiederherstellung nach einer Unterbrechung. GitHub-Antworten, Image-Download und systemd werden dort durch Testgegenstellen ersetzt. Ausschließlich sein isolierter Wartungs-Testcontainer erhält Zugriff auf die Docker-Engine; das Dashboard erhält keinen Docker-Socket.

Erzeugte JSON-Prüfberichte und private lokale Nachweise außerhalb des Repositories archivieren. Sie sind Momentaufnahmen eines Testlaufs; die reproduzierbaren Prüfprogramme bleiben in Git. Bekannte Grenzen und die noch offene Prüfung am Pi stehen in [ABNAHME.md](ABNAHME.md).

## App-Icon

Die editierbare Quelle ist [`app/static/icon.svg`](../app/static/icon.svg). PNG-Ableitungen liegen daneben: `icon-512.png` für die App und `apple-touch-icon.png` mit 180 × 180 Pixeln für Lesezeichen. Dashboard, TV-Ansicht und GitHub-Auftritt verwenden dieselbe Gestaltung. SVG und PNG bei einer Änderung gemeinsam aktualisieren.
