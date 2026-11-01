# Raspberry Pi 2B: normal aufsetzen, später Kamerablick ergänzen

Diese Anleitung bleibt als Alternative für einen Pi 2B mit LAN erhalten. Das aktuelle Zielgerät ist ein **Pi 4B mit WLAN**; dafür gilt [PI4.md](PI4.md).

Der vorgesehene Weg benötigt kein eigenes Kamerablick-Betriebssystemimage. Zuerst Raspberry Pi OS installieren; Kamerablick wird anschließend aus dem GitHub-Projekt und einem fertig gebauten Docker-Image ergänzt.

## Jetzt: Pi normal einrichten

1. Im Raspberry Pi Imager den Pi 2 auswählen und **Raspberry Pi OS (32-bit) mit Desktop** installieren. Die normale Desktop-Ausgabe genügt; „Full“ ist nicht nötig. Die aktuelle 32-Bit-Ausgabe ist laut [Raspberry Pi](https://www.raspberrypi.com/software/operating-systems/) mit allen Pi-Modellen kompatibel. Für den bestehenden TV-Browser wird eine grafische Sitzung gebraucht.
2. Einen eigenen Benutzernamen, das lokale Passwort, einen Hostnamen wie `kamerablick` und SSH im Imager einrichten. Zugangswerte bleiben lokal.
3. Den Pi per LAN anschließen, starten und die normale Einrichtung abschließen. Das Dashboard und die Kamera müssen dabei noch nicht installiert sein.
4. Desktop, Netzwerk und SSH prüfen. Desktop-Autologin wird für die spätere Bedienung ohne Anmeldung benötigt und kann anschließend in den Pi-Einstellungen aktiviert werden.

## Später: Docker und Voraussetzungen

Der Pi 2B wird hier über **ARMv7/32 Bit** unterstützt; damit ist keine bestimmte spätere Pi-2-Revision mit 64-Bit-CPU nötig. Eine tatsächlich flüssige Videowiedergabe ist noch am Gerät nachzuweisen. Für den ersten Kameratest niedrige Qualität und nach Möglichkeit H.264 wählen. RAM, Decoder und Streamformat begrenzen die nutzbare Auflösung; 4K/H.265 sind keine zugesicherte Funktion dieser Vorbereitung.

Auf dem Pi zunächst prüfen:

```sh
uname -m
dpkg --print-architecture
cat /etc/os-release
```

Bei der vorgesehenen 32-Bit-Installation ist die Paketarchitektur `armhf`; der Kernel meldet typischerweise `armv7l`.

Docker Engine und Compose nach der [Debian-Anleitung für ARMv7/armhf](https://docs.docker.com/engine/install/debian/) installieren. Wichtig: Die alten dedizierten Raspbian-Pakete enden mit Docker 28. Docker verweist ARMv7-Nutzer für neuere Versionen auf Debian-armhf-Pakete ([offizieller Hinweis](https://docs.docker.com/engine/install/raspberry-pi-os/)). Deshalb kein beliebiges altes Installationsskript übernehmen. Die genaue Einrichtung am vorhandenen Pi richtet sich nach dessen `/etc/os-release`.

Benötigte normale Betriebssystempakete:

```sh
sudo apt update
sudo apt install git python3-gpiozero python3-lgpio cec-utils mpv chromium
```

Der normale Desktop-Benutzer muss Docker ausführen können. Nach einer Änderung der Benutzergruppen neu anmelden. Der Projektinstaller verändert Benutzergruppen, Router und SSH nicht selbstständig.

## Nach Veröffentlichung auf GitHub

Repository: [loserat/kamerablick](https://github.com/loserat/kamerablick). Verfügbare Versionen: [GitHub Releases](https://github.com/loserat/kamerablick/releases). Die Installation einer veröffentlichten Version verwendet diese Befehle:

```sh
git clone --branch v0.1.6 https://github.com/loserat/kamerablick.git ~/kamerablick
cd ~/kamerablick
python3 pi/install.py --check
python3 pi/install.py --install --image ghcr.io/loserat/kamerablick:v0.1.6
```

Der GitHub-Workflow ist für `linux/arm/v7`, `linux/arm64` und `linux/amd64` vorbereitet. Docker wählt beim Herunterladen die passende Variante. Der Pi baut dabei kein Container-Image selbst.

Der Installer lädt die zum Image gehörenden Pi-Laufzeitdateien, richtet die Benutzer-Dienste und den Desktop-Autostart ein und startet das Dashboard mit Bereitschaftsprüfung. Die automatische TV-Anwendung startet bei der nächsten Desktop-Anmeldung. Das öffentlich freigegebene Image benötigt keine GitHub-Anmeldung auf dem Pi.

Das Dashboard läuft in Docker. GPIO-Taster, HDMI-CEC, Videoplayer und Kiosk laufen als lokale Pi-Dienste. Der Dashboard-Container erhält weder privilegierten Gerätezugriff noch den Docker-Socket.

## Einrichten und aktualisieren

Vom eigenen Rechner einen privaten SSH-Tunnel zum Pi öffnen:

```sh
ssh -L 8088:127.0.0.1:8088 BENUTZER@kamerablick.local
```

Bei fehlender Namensauflösung stattdessen die lokale IP des Pi verwenden. Danach am eigenen Rechner `http://127.0.0.1:8088` öffnen. Das Dashboard-Passwort steht auf dem Pi in der privaten Datei `~/kamerablick/.env`. Protect-Adresse und API-Schlüssel werden im Einrichtungsdialog eingegeben.

Spätere App-Updates erfolgen mit einer konkreten veröffentlichten Version:

```sh
cd ~/kamerablick
./pi/update.sh ghcr.io/loserat/kamerablick:v0.1.6
```

Der Updater sichert die Konfiguration und übernimmt Container und Pi-Dienste gemeinsam. Hardware, echtes Kamerabild, CEC und der Fernzugriff von außerhalb des Heimnetzes werden am Pi gesondert geprüft. Der vorbereitete SSH-Tunnel ersetzt noch kein eingerichtetes VPN.

## Bisher geprüft

Das ARMv7-Containerimage ist unter Emulation gebaut und ausgeführt worden. 32-Bit-Python, Anmeldung, Konfigurationsspeicherung, Neustart, gemeinsamer Laufzeitwechsel, zusätzliche Pi-Hilfsdateien sowie Wiederherstellung nach einem absichtlich fehlerhaften Image sind geprüft. Der Download-Installationspfad mit `--image` und ohne lokalen Containerbau ist automatisiert geprüft. Die echten GPIO-/CEC-Dienste, Grafikbeschleunigung und flüssige Wiedergabe auf dem Pi 2B sind weiterhin offen. GitHub Actions prüft vor jedem Release die Anwendung und veröffentlicht ein Image mit ARMv7-, ARM64- und AMD64-Variante. Erst nach erfolgreicher Image-Veröffentlichung wird das GitHub-Release angelegt.
