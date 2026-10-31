# Kamerablick installieren

Aktueller Stand: Raspberry Pi 4B mit WLAN als Zielgerät benannt; Einrichtung und Zugriff stehen noch aus. Die Protect-Zentrale wurde als „Instant“ benannt, vorläufig als UNVR Instant eingeordnet. TV-Modell, Speicherausstattung des Pi und genaue Protect-Version sind noch offen. Diese Anleitung beschreibt den vorbereiteten Weg, keine bereits abgeschlossene Geräteinstallation.

## 1. Raspberry Pi vorbereiten

Ausgangspunkt für den Pi 4B ist Raspberry Pi OS **(64 Bit) mit Desktop**. WLAN, Land, Benutzer und SSH können bereits im Raspberry Pi Imager eingerichtet werden. Der kurze Pi-4-Einstieg steht in [PI4.md](PI4.md); die alternative Pi-2-Anleitung für 32 Bit bleibt in [PI2.md](PI2.md). Der Benutzer, der später automatisch am Desktop angemeldet wird, betreibt auch Kamerablick. WLAN-Empfang am TV und die tatsächlich flüssig wiedergegebene Auflösung prüfen wir beim ersten Gerätetest.

Benötigt werden:

- Docker Engine und Compose v2, für diesen Benutzer erreichbar; der Docker-Dienst muss beim Booten starten.
- `python3-gpiozero`, `python3-lgpio`, `mpv` und Chromium aus der Paketverwaltung.
- `cec-utils` aus der Paketverwaltung für den dauerhaft laufenden CEC-Hilfsprozess. Eine zusätzliche Python-CEC-Bindung ist nicht nötig; CEC läuft außerhalb des Dashboard-Containers auf dem Pi.
- Eine funktionierende grafische Sitzung über HDMI.

Docker auf dem Pi 4B mit 64-Bit-System nach der [offiziellen Debian-Anleitung](https://docs.docker.com/engine/install/debian/) für `arm64` installieren. Docker verweist für Raspberry Pi OS in 64 Bit ausdrücklich auf diese Pakete ([Hinweis](https://docs.docker.com/engine/install/raspberry-pi-os/)). Für die alternative Pi-2-Installation gelten die ARMv7-Hinweise in [PI2.md](PI2.md). Docker-Zugriff für den Benutzer erlaubt weitreichende Änderungen am System; nur dem vorgesehenen vertrauenswürdigen Benutzer geben. Vorhandene Docker-Installationen zuerst prüfen und nicht pauschal ersetzen.

Die Bedienung soll später ohne Anmeldung möglich sein. Desktop-Autologin und Bildschirmabschaltung werden bewusst am Gerät in den Pi-Einstellungen eingerichtet. Der Installer verändert weder Desktop-Anmeldungen noch Benutzergruppen, SSH, VPN, Router oder Paketquellen. Basis: [Raspberry-Pi-Konfiguration](https://www.raspberrypi.com/documentation/computers/configuration.html).

## 2. Projekt prüfen und installieren

Den Projektordner beispielsweise nach `~/oma-tv` kopieren. Als normaler Desktop-Benutzer im Projektordner:

```sh
python3 pi/install.py --check
```

Das liest nur Voraussetzungen. Fehlende Voraussetzungen zuerst ergänzen. Anschließend:

```sh
python3 pi/install.py --install --image ghcr.io/loserat/kamerablick:v0.1.3
```

Quellcode und Container werden über [loserat/kamerablick](https://github.com/loserat/kamerablick) veröffentlicht. Verwende Quellstand und Image derselben Version. Die öffentlich freigegebenen Images lassen sich ohne GitHub-Anmeldung abrufen.

Der Installer:

- erzeugt bei einer frischen Installation eigene zufällige Zugangswerte in `.env` mit privaten Dateirechten;
- erhält vorhandene gültige Werte und lehnt Platzhalter oder einen noch aktiven Demomodus ab;
- lädt das versionierte Image und startet das Dashboard ohne lokalen Containerbau;
- wartet auf den Bereitschaftstest des Containers;
- legt eine versionierte Pi-Laufzeit unter `.runtime/releases/` an;
- richtet Benutzer-Dienste für Taster/TV und Chromium ein;
- registriert einen eigenen Desktop-Autostart, der die aktuelle Bildschirmumgebung an die Dienste übergibt.

Eigene bestehende Service- oder Autostartdateien gleichen Namens werden nicht überschrieben. Bei einem Fehler die Meldung prüfen und den Installer erneut ausführen; nicht einfach eigene Desktop-Konfigurationen löschen. Der Installer schreibt keine Zugangswerte in seine Ausgabe. Bei einem bereits installierten Image ist ein Versionswechsel über `pi/update.sh` vorgesehen. Ohne `--image` ist weiterhin ein lokaler Entwicklerbau möglich.

Nach Ab- und erneuter Anmeldung am Desktop startet die TV-Ansicht automatisch. Der Browser wartet auf das Dashboard und erhält lokal einen eingeschränkten TV-Zugang. Ein Dashboard-Passwort muss nicht am Fernseher eingegeben werden. Ohne eingerichtete Kamera bleibt die Kamerakachel im Echtbetrieb gesperrt, Hilfe und Ausschalten bleiben verfügbar.

## 3. Kamera und privaten Wartungszugang einrichten

Eine neue Pi-Installation ist im selben Heimnetz direkt unter **`http://PI-IP:8088`** erreichbar. Die WLAN-/LAN-Adresse des Raspberry Pi verwenden; ein SSH-Tunnel ist dafür nicht nötig. Das neu erzeugte Dashboard-Passwort steht auf dem Pi in `.env`.

Bei einer vorhandenen Installation bleibt die gespeicherte Einstellung erhalten. Für direkten Zugriff auf dem Pi:

```sh
cd ~/kamerablick
cp -p .env ".env.before-lan-$(date +%Y%m%d-%H%M%S)"
sed -i 's/^BIND=.*/BIND=0.0.0.0/' .env
docker compose up -d --no-build --wait --wait-timeout 120
```

Die Datei und Sicherung enthalten private Zugangswerte und bleiben lokal. Die Öffnung gilt nur für das Dashboard; `AGENT_URL` bleibt `http://127.0.0.1:8091`.

HTTP überträgt die Anmeldung unverschlüsselt. Den direkten Aufruf nur im vertrauenswürdigen Heimnetz nutzen. Für ausschließlich lokalen Zugriff stattdessen `BIND=127.0.0.1` setzen und den Container auf dieselbe Weise neu starten. Auf dem eigenen Rechner kann dann weiterhin ein SSH-Tunnel verwendet werden:

```sh
ssh -L 8099:127.0.0.1:8088 BENUTZER@PI-ADRESSE
```

Anschließend `http://127.0.0.1:8099` öffnen. Es ist keine öffentliche Portfreigabe vorgesehen.

Unter „Kamera einrichten“ die lokale Protect-Adresse eintragen und die Anmeldeart wählen: lokaler UniFi-Benutzer mit Passwort oder API-Schlüssel. Beim lokalen Login kann ein Schlüssel für moderne Streams und laufende Ereignisse ergänzt werden. Kamera und Qualität auswählen, Standbild prüfen und übernehmen. Eine vorhandene RTSP-/RTSPS-Kamera kann alternativ mit „Kamera manuell hinzufügen“ gespeichert werden. Der Ablauf und ein Test ohne Pi stehen in [HEIMTEST.md](HEIMTEST.md). Bei einem eigenen Zertifikat den Fingerabdruck zuerst mit dem echten Konsolenzertifikat über einen vertrauenswürdigen Zugang vergleichen.

VPN und SSH sind getrennte Systemkomponenten und noch nicht eingerichtet. Es wird keine öffentliche Portfreigabe für das Dashboard oder Protect benötigt. Die SSH-Weiterleitung und der tatsächliche Fernzugriff werden später von einem anderen Netzwerk aus getestet.

## 4. Taster und TV abnehmen

Bei ausgeschaltetem Pi einen spannungsfreien Schließer zwischen GPIO17 (BCM; physischer Pin 11) und GND (z. B. Pin 6) anschließen. Keine Fremdspannung einspeisen. Belegung des tatsächlichen Pi vor dem Anschluss prüfen.

TV-CEC im Fernseher aktivieren. Im Dashboard zuerst Kamera und TV-Befehle prüfen, danach den Taster. GPIO-Taster und CEC funktionieren erst mit passenden Geräteberechtigungen und tatsächlich angeschlossener Hardware.

Die TV-Ansicht ist mit Tastatur nutzbar. CEC-Empfang für Pfeile, OK und Zurück ist implementiert; ob die TV-Fernbedienung diese Tasten weitergibt, muss am Fernseher geprüft werden. Unter „Wartung → Tastenempfang prüfen“ stehen Adapterzustand, letzte empfangene Taste und Verbindung zur lokalen TV-Ansicht. Vorgehen und Grenzen: [Fernbedienung](FERNBEDIENUNG.md).

## Dienste und Diagnose

```sh
systemctl --user status oma-tv-session.target oma-tv-agent.service oma-tv-kiosk.service
journalctl --user -u oma-tv-agent -u oma-tv-kiosk -n 50
```

Der Desktop-Autostart startet das gemeinsame Sitzungsziel. Bei Ende der lokalen grafischen Sitzung beendet die Startbrücke die zugehörigen Dienste. Diese Anbindung erfordert einen tatsächlichen Gerätetest mit der vorgesehenen Desktop-Version.

Das Dashboard bleibt durch die Docker-Neustartregel auch nach einem Neustart des Docker-Diensts verfügbar. Auf dem Pi muss der Docker-Dienst selbst ebenfalls automatisch starten. Der Kameraplayer wartet nicht auf einen Internetdienst; die Protect-Verbindung bleibt lokal.

Die Wiedergabeüberwachung prüft jede Sekunde, ob sich die Wiedergabezeit bei gemeldeter Videoausgabe verändert. Ohne ersten Fortschritt erfolgt nach 30 Sekunden ein Neuversuch; nach vorherigem Fortschritt gilt ein Stillstand von 20 Sekunden als festhängende Wiedergabe. Nach fünf Sekunden ohne Fortschritt wird der Status bereits als nicht aktuell angezeigt. Eine ausgefallene Player-Verbindung wird sofort nicht mehr als aktueller Fortschritt gewertet.

Neuversuche warten mit zunehmendem Abstand von 5 bis 60 Sekunden. Nach mindestens zehn Sekunden stabiler Wiedergabe beginnt diese Staffel wieder von vorn. Der automatische Abschaltzeitpunkt wird durch Neuversuche nicht verlängert. OK/Zurück und Standby bleiben getrennte Bedienaktionen. Der lokale Player-Steuerkanal liegt in einem privaten Verzeichnis; eigene mpv-Konfigurationen und Skripte werden für Kamerablick nicht geladen.

## Updates und Rückweg

Nach Veröffentlichung einer passenden Version:

```sh
./pi/update.sh ghcr.io/loserat/kamerablick:v0.1.3
```

Es werden Dashboard und mitgelieferter Pi-Dienst gemeinsam aktualisiert. Die gewählte Image-Version bestimmt auch ihre zusätzlichen Hilfsmodule; der Updater übernimmt diese nach einer Pfad- und Quellprüfung. Einstellungen, Protect-Zugang und TV-Freigaben sowie vorhandene Pi-Konfiguration werden gesichert. Der tatsächliche vorherige Container wird als lokales Rückfallimage erhalten. Bei fehlgeschlagenem Start oder Health-Test werden altes Image, alte Pi-Laufzeit und gesicherte Daten wiederhergestellt.

Ein laufendes Update kann nicht parallel ein zweites Mal gestartet werden. Bleibt nach Stromausfall ein unvollständiger Updatezustand zurück, versucht der Desktop-Autostart vor dem Dienststart die Wiederherstellung. Manuell:

```sh
./pi/update.sh --recover
```

Ein absichtlich fehlerhaftes Container-Image und die Wiederherstellung wurden lokal auf ARM64 Docker geprüft. Benutzer-Dienste und Hardware waren dabei nicht aktiv. Daher ersetzt der Test nicht die Pi-Abnahme. Wenn kein Desktop aktiv ist, prüft der Updater den Container; die Prüfung des Pi-Diensts erfolgt bei der nächsten grafischen Anmeldung.

Der Updater ändert keine Betriebssystempakete, VPN-Einstellungen oder Firmware. Diese Updates benötigen eigene Wartung und Tests.
