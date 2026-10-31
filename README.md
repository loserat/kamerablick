# Kamerablick · Oma TV

Eine einfache TV-Ansicht für UniFi Protect: Taster drücken, Kamera ansehen und den Fernseher wieder in Standby schicken. Das geschützte Dashboard dient der Einrichtung und Wartung.

**Noch keine abgeschlossene Inbetriebnahme.** Als Ziel ist jetzt ein Raspberry Pi 2B vorgesehen; die Installation auf diesem Gerät wurde noch nicht geprüft. „Instant“ ist als Protect-Zentrale benannt; genaue Version und TV-Modell sind offen. Softwaretests ersetzen keine Inbetriebnahme am Gerät.

- [Pi 2B normal aufsetzen und später von GitHub installieren](PI2.md)
- [Installation und Updates](INSTALLATION.md)
- [Vollständige Abnahme und offene Punkte](ABNAHME.md)
- [Kamerastatus und Ereignisse](TELEMETRIE.md)
- [Fernbedienung und Tastenprüfung](FERNBEDIENUNG.md)

## Für deine Oma

In der TV-Ansicht gibt es eine große Kamerakachel, eine kurze Hilfe und „Fernseher aus“ mit Bestätigung. Pfeiltasten wählen aus, Enter entspricht OK; Esc oder Rücktaste führt zurück. Die Einstellungen sind dort nicht erreichbar.

Der Taster schaltet Kamera und TV ein. Ein weiterer Druck fordert Standby an. Die automatische Abschaltzeit wird im Dashboard festgelegt. „Zur Übersicht“ beendet das Kamerabild und lässt den Fernseher eingeschaltet.

Tastatur und Weboberfläche sind getestet. Der CEC-Empfang für Pfeile, OK und Zurück ist implementiert und lokal mit simulierten Tasten geprüft. Die echte TV-Fernbedienung ist noch nicht am Gerät verifiziert. Die TV-Ansicht zeigt derzeit eine eingerichtete Kamera.

## Für dich

- Protect-Adresse und API-Schlüssel eintragen, Kamera auswählen und Standbild prüfen; die Stream-Adresse wird übernommen.
- GPIO, Bildqualität und Abschaltzeit einstellen.
- Wiedergabefortschritt prüfen und festhängende Wiedergabe automatisch neu verbinden.
- Kamerastatus und letzte empfangene Bewegung, Person und Fahrzeug mit erkennbarer Aktualität sehen.
- Privater Zugriff über den vorhandenen VPN-/SSH-Weg; Standardbindung bleibt localhost.
- Versionierte Updates über GitHub Container Registry, mit gemeinsamer Pi-Laufzeit, privater Sicherung und Rückkehr nach Startfehlern.

Protect-Zugang, Einstellungen und TV-Freigabe bleiben in lokalen Dateien beziehungsweise im Docker-Volume. Sie gehören nicht ins Repository. TV- und Dashboard-Zugänge sind getrennt.

## Neue Pi-Installation

Projekt herunterladen:

```sh
git clone --branch v0.1.0 https://github.com/loserat/kamerablick.git ~/kamerablick
cd ~/kamerablick
```


Voraussetzung: Raspberry Pi OS mit Desktop, auf dem Pi 2B in 32 Bit, Docker/Compose, GPIO-Bibliothek, Chromium, mpv und cec-utils. Details und Pakete stehen in der Installationsanleitung.

Als normaler Desktop-Benutzer im Projektordner:

```sh
python3 pi/install.py --check
python3 pi/install.py --install --image ghcr.io/loserat/kamerablick:v0.1.0
```

Das öffentliche Projekt liegt unter [loserat/kamerablick](https://github.com/loserat/kamerablick). Verfügbare Versionen stehen unter [Releases](https://github.com/loserat/kamerablick/releases). Für den Pi 2B sind ARMv7-Images vorbereitet. Ohne `--image` bleibt ein lokaler Entwicklerbau möglich; auf dem Pi 2B den fertig veröffentlichten Container verwenden.

Die erste Zeile prüft nur. Die zweite installiert erst nach erfolgreicher Prüfung. Vorhandene eigene gleichnamige Service-/Autostartdateien werden nicht überschrieben; ein vorhandener Demomodus wird nicht stillschweigend auf Echtbetrieb umgestellt.

Eine frische Installation erzeugt zufällige Zugangswerte und startet die TV-Ansicht ab der nächsten Desktop-Anmeldung automatisch. Für die Kameraeinrichtung das Dashboard über den privaten Wartungszugang öffnen. Das Passwort steht auf dem Pi in `.env`; es wird nicht ins Installationsprotokoll geschrieben.

## Lokale Demo ohne Pi

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DASHBOARD_PASSWORD='eigenes-langes-passwort'
DEMO_MODE=true .venv/bin/python app/server.py
```

Im Browser `http://127.0.0.1:8088` öffnen. Das Dashboard kann Beispielkameras laden und die TV-Ansicht öffnen. Es werden keine GPIO-/TV-Befehle gesendet. Eine Demo zeigt kein echtes Kamerabild und keine erfundenen Bewegungserkennungen.

## Updates

Für eine verwaltete Installation mit laufendem Dashboard:

```sh
./pi/update.sh ghcr.io/loserat/kamerablick:v0.1.0
```

Der Updater sichert Einstellungen einschließlich Protect- und TV-Zugang, `.env` und vorhandene Pi-Konfiguration. Er übernimmt Dashboard und die mitgelieferten Pi-Laufzeitdateien gemeinsam. Auch neue Hilfsmodule kommen aus der gewählten Image-Version; Dateipfade und Python-Quellen werden vor dem Wechsel geprüft. Bei einem Fehler stellt er die alte Version einschließlich Daten wieder her und behält das tatsächliche alte Image auch für spätere Neustarts in `.env` bei.

Nach einem unterbrochenen Update:

```sh
./pi/update.sh --recover
```

Die Desktop-Startbrücke führt diese Prüfung vor dem Dienststart ebenfalls aus. Betriebssystem, VPN und Firmware werden nicht mitverändert. Der GitHub-Workflow baut bei `v*`-Tags ARMv7-/ARM64-/AMD64-Images; prüft die enthaltenen Plattformen und erzeugt anschließend automatisch das GitHub-Release für die Versionsprüfung im Dashboard.

Kamera-, GPIO- und CEC-Funktion nach Updates am Gerät prüfen. Bei inaktiver grafischer Sitzung kann der Updater nur das Dashboard prüfen; der Pi-Dienst wird erst beim Desktop-Login gestartet.

## Prüfung

```sh
.venv/bin/python -m unittest discover -s tests -v
node tests/test_tv_navigation.cjs
node tests/test_telemetry_view.cjs
node tests/test_tv_remote.cjs
```

Optional mit erreichbarer Docker-Engine:

```sh
python3 tests/docker_acceptance.py
python3 tests/docker_acceptance.py --platform linux/arm/v7
python3 tests/cec_acceptance.py
python3 tests/player_acceptance.py
python3 tests/stream_acceptance.py
```

Die Containerabnahmen bauen eigene Testimages, starten ausschließlich eigene Testcontainer und entfernen ihre Container, Volumes und temporären Images anschließend. Die CEC-Prozessprüfung nutzt das echte Trixie-Paket ohne angeschlossene Geräte. Die Player-Abnahme verwendet echtes mpv mit einem erzeugten lokalen Video und unsichtbarer Testausgabe. Sie prüft Stillstand, Wiederanlauf und die unveränderte Abschaltzeit; RTSP und die sichtbare TV-Ausgabe werden dabei nicht geprüft. Die zusätzliche Stream-Abnahme nutzt einen echten RTSP/RTSPS-Testserver in einem internen Docker-Netz ohne veröffentlichte Ports. Kameraausfall, lautloser Verbindungsstillstand, Serverneustart und Ausschalten während eines Ausfalls werden mit Produktionszeitgrenzen geprüft. Es werden ausschließlich erzeugte Testbilder verwendet; MediaMTX ist nur ein Testwerkzeug und wird für den Pi-Betrieb nicht benötigt.

89 Python-Tests und 32 JavaScript-Assertions prüfen Authentifizierung, Protect-Einrichtung, Zertifikate, TV-Zugang, getrennten CEC-Empfänger, Tastendopplungen, Navigation, Installation und Fehlerfälle der Pi-/Update-Logik. Zusätzlich ist der Containerbetrieb auf ARM64 sowie ARMv7/32 Bit (unter Emulation) mit echter Docker-Engine geprüft: Anmeldung, Konfigurationsspeicherung, Neustart, Laufzeitwechsel, Rückkehr nach einem absichtlich fehlerhaften Image, Datenwiederherstellung und Wiederaufnahme einer unterbrochenen Aktualisierung.

Das ist keine Live-Verifikation von Protect, GPIO, HDMI-CEC, grafischem Autostart oder VPN. Der Player meldet über einen privaten lokalen Kanal seine Wiedergabezeit und Videoausgabe. Erst eine fortschreitende Wiedergabe wird entsprechend angezeigt; ein laufender Prozess allein genügt nicht. Das ist weiterhin kein Beweis für das tatsächlich sichtbare oder aktuelle Kamerabild am TV. Kameratelemetrie und die letzte empfangene Bewegung sind implementiert und gegen eine lokale Testkonsole geprüft. Die reale Protect-Version und die tatsächlichen Ereignisse am Instant bleiben zu verifizieren.

Technische Grundlagen: [Protect in Home Assistant](https://www.home-assistant.io/integrations/unifiprotect/), [Ubiquiti Protect API](https://developer.ui.com/protect), [Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/configuration.html).
