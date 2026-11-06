# Kamerablick installieren

Zielgerät ist ein Raspberry Pi 4B mit WLAN und Desktop. Start, Dashboard, Wartung und CEC-Tastenempfang wurden am Pi 4B mit Philips 55PUS6581/12 bestätigt. Die genaue Trennung zwischen Gerätetest, Softwaretest und offenen Kamerafunktionen steht im [Prüfprotokoll](ABNAHME.md).

## 1. Raspberry Pi vorbereiten

Ausgangspunkt für den Pi 4B ist Raspberry Pi OS **(64 Bit) mit Desktop**. WLAN, Land, Benutzer und SSH können bereits im Raspberry Pi Imager eingerichtet werden. Der kurze Pi-4-Einstieg steht in [PI4.md](PI4.md); die alternative Pi-2-Anleitung für 32 Bit bleibt in [PI2.md](PI2.md). Der Benutzer, der später automatisch am Desktop angemeldet wird, betreibt auch Kamerablick. WLAN-Empfang und flüssige Wiedergabe am tatsächlichen Aufstellort gesondert prüfen.

Benötigt werden:

- Docker Engine und Compose v2, für diesen Benutzer erreichbar; der Docker-Dienst muss beim Booten starten.
- `python3-gpiozero`, `python3-lgpio`, `mpv` und Chromium aus der Paketverwaltung.
- `cec-utils` aus der Paketverwaltung für den dauerhaft laufenden CEC-Hilfsprozess. Eine zusätzliche Python-CEC-Bindung ist nicht nötig; CEC läuft außerhalb des Dashboard-Containers auf dem Pi.
- Eine funktionierende grafische Sitzung über HDMI.

Docker auf dem Pi 4B mit 64-Bit-System nach der [offiziellen Debian-Anleitung](https://docs.docker.com/engine/install/debian/) für `arm64` installieren. Docker verweist für Raspberry Pi OS in 64 Bit ausdrücklich auf diese Pakete ([Hinweis](https://docs.docker.com/engine/install/raspberry-pi-os/)). Für die alternative Pi-2-Installation gelten die ARMv7-Hinweise in [PI2.md](PI2.md). Docker-Zugriff für den Benutzer erlaubt weitreichende Änderungen am System; nur dem vorgesehenen vertrauenswürdigen Benutzer geben. Vorhandene Docker-Installationen zuerst prüfen und nicht pauschal ersetzen.

Die Bedienung soll später ohne Anmeldung möglich sein. Desktop-Autologin und Bildschirmabschaltung werden bewusst am Gerät in den Pi-Einstellungen eingerichtet. Der Installer verändert weder Desktop-Anmeldungen noch Benutzergruppen, SSH, VPN, Router oder Paketquellen. Basis: [Raspberry-Pi-Konfiguration](https://www.raspberrypi.com/documentation/computers/configuration.html).

## 2. Projekt prüfen und installieren

Den veröffentlichten Quellstand als normaler Desktop-Benutzer beziehen:

```sh
git clone --branch v0.1.13 https://github.com/loserat/kamerablick.git ~/kamerablick
cd ~/kamerablick
sudo loginctl enable-linger "$USER"
```

Voraussetzungen lesend prüfen:

```sh
python3 pi/install.py --check
```

Das liest nur Voraussetzungen. Fehlende Voraussetzungen zuerst ergänzen. Anschließend:

```sh
python3 pi/install.py --install --image ghcr.io/loserat/kamerablick:v0.1.13
```

Quellcode und Container werden über [loserat/kamerablick](https://github.com/loserat/kamerablick) veröffentlicht. Verwende Quellstand und Image derselben Version. Die öffentlich freigegebenen Images lassen sich ohne GitHub-Anmeldung abrufen.

Der Installer:

- erzeugt bei einer frischen Installation eigene zufällige Zugangswerte in `.env` mit privaten Dateirechten;
- erhält vorhandene gültige Werte und lehnt Platzhalter oder einen noch aktiven Demomodus ab;
- lädt das versionierte Image und startet das Dashboard ohne lokalen Containerbau;
- wartet auf den Bereitschaftstest des Containers;
- legt eine versionierte Pi-Laufzeit unter `.runtime/releases/` an;
- richtet Benutzer-Dienste für Taster/TV, Chromium und die unabhängige Wartung ein;
- registriert einen eigenen Desktop-Autostart, der die aktuelle Bildschirmumgebung an die Dienste übergibt.

Eigene bestehende Service- oder Autostartdateien gleichen Namens werden nicht überschrieben. Bei einem Fehler die Meldung prüfen und den Installer erneut ausführen; nicht einfach eigene Desktop-Konfigurationen löschen. Der Installer schreibt keine Zugangswerte in seine Ausgabe. Bei einer vorhandenen verwalteten Installation erfolgen normale App-Updates über Wartung; `pi/update.sh` bleibt ein manueller Wartungsweg. Ohne `--image` ist weiterhin ein lokaler Entwicklerbau möglich.

Nach Ab- und erneuter Anmeldung am Desktop startet die TV-Ansicht automatisch. Der Browser wartet auf das Dashboard und erhält lokal einen eingeschränkten TV-Zugang. Ein Dashboard-Passwort muss nicht am Fernseher eingegeben werden. Die TV-Ansicht zeigt große Kamerakacheln und eine eigene Ausschaltaktion. Ohne eingerichtete Kamera erscheint ein kurzer Hinweis; Einstellungen werden im Dashboard vorgenommen.

Der TV-Browser verwendet ausschließlich das eigene Profil `~/.config/chromium-kamerablick` und startet mit `--password-store=basic`, damit nach Desktop-Autologin keine interaktive Schlüsselbund-Abfrage erscheint. Dieser Chromium-Speicher ist unverschlüsselt; in diesem TV-Profil keine Dashboard- oder UniFi-Passwörter speichern. Die TV-Freigabe erfolgt lokal durch den Pi-Dienst. Normale Browserprofile und der System-Schlüsselbund werden nicht geändert. Die Übersetzungsabfrage ist für den TV-Browser deaktiviert. Bei regulärem Dienststopp oder App-Update beendet der Starter seinen eigenen Browserprozess ausdrücklich, auch wenn Chromium ihn in einen eigenen systemd-Bereich verschoben hat. [Chromium-Dokumentation](https://chromium.googlesource.com/chromium/src/+/main/docs/linux/password_storage.md)

## 3. Kamera und privaten Wartungszugang einrichten

Eine neue Pi-Installation ist im selben Heimnetz direkt unter **`http://PI-IP:8088`** erreichbar. Die WLAN-/LAN-Adresse des Raspberry Pi verwenden; ein SSH-Tunnel ist dafür nicht nötig. Das anfängliche Dashboard-Passwort steht auf dem Pi in `.env`. Danach lässt es sich unter **Einstellungen → Dashboard-Passwort ändern** ändern; anschließend gilt das neu gesetzte Passwort.

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

Unter „Kameras“ die lokale Protect-Adresse eintragen und die Anmeldeart wählen: lokaler UniFi-Benutzer mit Passwort oder API-Schlüssel. Beim lokalen Login kann ein Schlüssel für moderne Streams und laufende Ereignisse ergänzt werden. Kamera und Qualität auswählen, Standbild prüfen und übernehmen. Eine vorhandene RTSP-/RTSPS-Kamera kann alternativ mit „Streamadresse verwenden“ gespeichert werden. Der Ablauf und ein Test ohne Pi stehen in [HEIMTEST.md](HEIMTEST.md). Bei einem eigenen Zertifikat den Fingerabdruck zuerst mit dem echten Konsolenzertifikat über einen vertrauenswürdigen Zugang vergleichen.

VPN und SSH sind getrennte Systemkomponenten. Den privaten Zugang nach [Fernzugriff](FERNZUGRIFF.md) einrichten und aus einem fremden Netzwerk prüfen. Es wird keine öffentliche Portfreigabe für das Dashboard oder Protect benötigt.

## 4. Taster und TV abnehmen

Bei ausgeschaltetem Pi einen spannungsfreien Schließer zwischen GPIO17 (BCM; physischer Pin 11) und GND (z. B. Pin 6) anschließen. Keine Fremdspannung einspeisen. Belegung des tatsächlichen Pi vor dem Anschluss prüfen.

TV-CEC im Fernseher aktivieren. Im Dashboard zuerst Kamera und TV-Befehle prüfen, danach den Taster. GPIO-Taster und CEC funktionieren erst mit passenden Geräteberechtigungen und tatsächlich angeschlossener Hardware.

Die TV-Ansicht ist mit Tastatur nutzbar. CEC-Empfang für Pfeile, OK und Zurück ist implementiert; der Empfang am Philips 55PUS6581/12 ist bestätigt. Andere TV-Modelle und der vollständige Kamera-/Playerablauf müssen am Ziel geprüft werden. Unter „Wartung → Fernbedienung“ stehen Adapterzustand, letzte empfangene Taste und Verbindung zur lokalen TV-Ansicht. Vorgehen und Grenzen: [Fernbedienung](FERNBEDIENUNG.md).

## Dienste und Diagnose

Als bisheriger Installationsbenutzer im Projektordner:

```sh
python3 .runtime/current/doctor.py --root "$PWD"
```

Die Diagnose liest Containerzustand, Dienststatus und Ladepfade, vergleicht die lokalen Pi-Schlüssel und prüft Dashboard, Pi-Dienst und Wartungsdienst. Sie gibt keine Passwörter, Stream-Adressen oder Schlüssel aus und schaltet den TV nicht. Für einen maschinenlesbaren Bericht `python3 .runtime/current/doctor.py --root "$PWD" --json` verwenden. Exitcode 1 bedeutet mindestens einen fehlgeschlagenen Installationstest; Hinweise allein führen nicht zum Fehlercode. Das ist keine Hardwareabnahme.

Bei einer älteren Installation ohne `pi/doctor.py` zuerst den aktuellen Quellstand beziehen. Nach einem Image-Update steht die Diagnose auch unter `.runtime/current/doctor.py` bereit. Der neue Wartungs-Bereitschaftstest benötigt ebenfalls die aktuelle Pi-Laufzeit. Fehlt er bei einer alten Version, heißt das allein noch nicht, dass deren Updatefunktion defekt ist.

Für die gezielte Dienstprüfung:

```sh
systemctl --user status oma-tv-session.target oma-tv-agent.service oma-tv-kiosk.service oma-tv-maintenance.service
journalctl --user -u oma-tv-agent.service -u oma-tv-kiosk.service -u oma-tv-maintenance.service -n 50 --no-pager
```

Der Desktop-Autostart startet das gemeinsame Sitzungsziel. Bei Ende der lokalen grafischen Sitzung beendet die Startbrücke die zugehörigen Dienste. Diese Anbindung erfordert einen tatsächlichen Gerätetest mit der vorgesehenen Desktop-Version.

Das Dashboard bleibt durch die Docker-Neustartregel auch nach einem Neustart des Docker-Diensts verfügbar. Auf dem Pi muss der Docker-Dienst selbst ebenfalls automatisch starten. Der Kameraplayer wartet nicht auf einen Internetdienst; die Protect-Verbindung bleibt lokal.

Die Wiedergabeüberwachung prüft jede Sekunde, ob sich die Wiedergabezeit bei gemeldeter Videoausgabe verändert. Ohne ersten Fortschritt erfolgt nach 30 Sekunden ein Neuversuch; nach vorherigem Fortschritt gilt ein Stillstand von 20 Sekunden als festhängende Wiedergabe. Nach fünf Sekunden ohne Fortschritt wird der Status bereits als nicht aktuell angezeigt. Eine ausgefallene Player-Verbindung wird sofort nicht mehr als aktueller Fortschritt gewertet.

Neuversuche warten mit zunehmendem Abstand von 5 bis 60 Sekunden. Nach mindestens zehn Sekunden stabiler Wiedergabe beginnt diese Staffel wieder von vorn. Der automatische Abschaltzeitpunkt wird durch Neuversuche nicht verlängert. OK/Zurück und Standby bleiben getrennte Bedienaktionen. Der lokale Player-Steuerkanal liegt in einem privaten Verzeichnis; eigene mpv-Konfigurationen und Skripte werden für Kamerablick nicht geladen.

## Updates und Rückweg

Ab v0.1.4 erfolgt die normale Aktualisierung in der Oberfläche unter **Wartung → Jetzt aktualisieren** mit Bestätigung, Sicherung und Startprüfung. Eine vorhandene Installation benötigt einmalig den unabhängigen Wartungsdienst; die genauen Übergangsbefehle und Fehlerfälle stehen in [BROWSER-UPDATES.md](BROWSER-UPDATES.md).

Für dauerhafte Benutzer-Dienste vor der neuen Pi-Installation einmalig `sudo loginctl enable-linger "$USER"` ausführen. Nach der Einrichtung ist kein SSH-Befehl pro App-Update mehr nötig. Der Wartungsdienst ist unabhängig vom TV-Browser und bleibt ausschließlich auf dem Pi erreichbar.

Der manuelle Rückweg bleibt verfügbar:

```sh
./pi/update.sh --recover
```

Container, Pi-Laufzeit, lokale Konfiguration und tatsächliches vorheriges Image werden gemeinsam berücksichtigt. Betriebssystem, Docker, Firmware und VPN werden nicht automatisch mitverändert. Die tatsächlichen Pi-/TV-Funktionen nach einem Update zusätzlich am Gerät prüfen.
