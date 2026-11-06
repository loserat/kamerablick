# Raspberry Pi 4B mit WLAN: normal aufsetzen, später Kamerablick ergänzen

Der Pi 4B ist das aktuelle Zielgerät. Er hat WLAN für 2,4 und 5 GHz eingebaut ([Herstellerangaben](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/specifications/)). Zuerst wird das normale Betriebssystem eingerichtet, danach Kamerablick mit dem bereits veröffentlichten Docker-Image ergänzt. Ein eigenes Kamerablick-Betriebssystemimage ist nicht nötig.

## 1. Betriebssystem und WLAN vorbereiten

1. Im Raspberry Pi Imager **Raspberry Pi 4** und **Raspberry Pi OS (64-bit) mit Desktop** auswählen. Die normale Desktop-Ausgabe genügt. Die TV-Ansicht benötigt die grafische Oberfläche; Lite enthält sie nicht. Der Pi 4B wird von der [64-Bit-Ausgabe](https://www.raspberrypi.com/software/operating-systems/) unterstützt.
2. Einen Hostnamen wie `kamerablick`, einen eigenen Benutzer und das lokale Passwort festlegen. WLAN-Name, WLAN-Passwort und das passende WLAN-Land einstellen. SSH für den späteren Wartungszugang aktivieren, möglichst mit eigenem SSH-Schlüssel. Zugangswerte bleiben lokal.
3. SD-Karte schreiben und den Pi am Fernseher starten. Am Pi 4B wird ein **Micro-HDMI-auf-HDMI-Kabel** benötigt; für den ersten Versuch den Anschluss HDMI0 neben USB-C verwenden. Ein geeignetes USB-C-Netzteil verwenden; Raspberry Pi nennt für den Pi 4B **5 V / 3 A** ([Einrichtung und Stromversorgung](https://www.raspberrypi.com/documentation/computers/getting-started.html)).
4. Die normale Einrichtung abschließen und Desktop, WLAN am späteren TV-Standort und SSH prüfen. Desktop-Autologin anschließend für die Bedienung ohne Anmeldung aktivieren.

Für die lokale Kamera muss der Pi die Protect-Zentrale im Heimnetz erreichen. Ein isoliertes Gast-WLAN verhindert das häufig. Bei schwachem Empfang den Standort prüfen und 2,4 beziehungsweise 5 GHz am tatsächlichen Aufstellort vergleichen.

Damit die TV-Ansicht nach dem Einschalten ohne Passwort startet, am Pi im Control Centre unter System den Start zum Desktop und Desktop-Autologin für den vorgesehenen Benutzer aktivieren. Bei älteren Raspberry-Pi-OS-Versionen heißt das Werkzeug Raspberry Pi Configuration; alternativ `sudo raspi-config` verwenden. Die Bildschirmabschaltung für die TV-Sitzung prüfen. Der Installer ersetzt diese Systemeinstellungen nicht. [Offizielle Konfiguration](https://www.raspberrypi.com/documentation/computers/configuration.html#require-a-password-from-startup)

## 2. Docker und Programme installieren

Zuerst System und Architektur prüfen:

```sh
uname -m
dpkg --print-architecture
cat /etc/os-release
```

Bei der empfohlenen 64-Bit-Installation sind `aarch64` und die Paketarchitektur `arm64` zu erwarten.

Docker Engine und Compose v2 nach der [offiziellen Debian-Anleitung](https://docs.docker.com/engine/install/debian/) für ARM64 installieren. Docker verweist für Raspberry Pi OS in 64 Bit ausdrücklich auf die Debian-Pakete ([Hinweis](https://docs.docker.com/engine/install/raspberry-pi-os/)). Vorhandene Installationen zuerst prüfen. Der vorgesehene Desktop-Benutzer muss Docker ohne `sudo` erreichen können; nach Gruppenänderungen neu anmelden. Der Docker-Dienst muss beim Booten starten.

Zusätzlich die Programme für Taster, TV und Wiedergabe installieren:

```sh
sudo apt update
sudo apt install git python3-gpiozero python3-lgpio cec-utils mpv chromium
docker version
docker compose version
```

## 3. Kamerablick von GitHub installieren

Als normaler Desktop-Benutzer:

```sh
git clone --branch v0.1.13 https://github.com/loserat/kamerablick.git ~/kamerablick
cd ~/kamerablick
sudo loginctl enable-linger "$USER"
python3 pi/install.py --check
```

Fehlende Voraussetzungen aus der Prüfung zuerst ergänzen. Danach:

```sh
python3 pi/install.py --install --image ghcr.io/loserat/kamerablick:v0.1.13
```

Das öffentliche Image enthält bereits **ARM64**; Docker wählt diese Variante automatisch. Für den Wechsel vom Pi 2B zum Pi 4B ist kein neues Anwendungsimage nötig. Der Pi muss den Container nicht selbst bauen.

Das Dashboard läuft in Docker. Taster, HDMI-CEC, Videoplayer und TV-Browser laufen als lokale Pi-Dienste. Nach der Installation am Desktop ab- und wieder anmelden, damit der Autostart geprüft werden kann.

## 4. Kamera und Wartungszugang einrichten

Im Browser auf deinem Rechner oder Smartphone im selben Heimnetz **`http://PI-IP:8088`** öffnen. `PI-IP` durch die WLAN-/LAN-Adresse des Raspberry Pi ersetzen. Bei der neuen Pi-Installation ist dafür kein SSH-Tunnel nötig. Für die erste Anmeldung gilt das zufällig erzeugte Passwort aus `~/kamerablick/.env`. Danach lässt es sich im Dashboard unter Einstellungen ändern.

Vorhandene Installationen behalten ihre bisherige Bindung. Die Umstellung auf direkten Heimnetzzugriff und die Alternative per SSH-Tunnel stehen unter [Installation](INSTALLATION.md#3-kamera-und-privaten-wartungszugang-einrichten). Für den direkten HTTP-Zugriff ein vertrauenswürdiges Heimnetz verwenden; es wird keine Router-Portfreigabe benötigt.

Protect-Adresse und lokalen UniFi-Benutzer oder API-Schlüssel im Einrichtungsdialog hinterlegen, Kamera auswählen und Standbild sowie Livebild prüfen. Der lokale Login unterstützt zusätzlich einen API-Schlüssel für moderne Streams und laufende Ereignisse. Details und der getrennte Heimtest stehen in [HEIMTEST.md](HEIMTEST.md). Zunächst einen H.264-Stream mit niedriger oder mittlerer Qualität testen und die Qualität am Gerät erhöhen. Flüssige Wiedergabe und Grafikbeschleunigung sind noch nicht am echten Pi 4B verifiziert.

Der Zugriff von außerhalb benötigt zusätzlich einen privaten VPN-Zugang. WLAN und aktiviertes SSH allein stellen diesen Fernzugriff noch nicht bereit. Einrichtung und Abnahme: [Fernzugriff](FERNZUGRIFF.md). Weitere Schritte, Updates und Tasteranschluss: [Installation](INSTALLATION.md), [Geräteabnahme](ABNAHME.md).

App-Updates erfolgen nach der einmaligen Einrichtung unter **Wartung** in der Oberfläche. Für bereits installierte Versionen gilt [Browser-Updates aktivieren](BROWSER-UPDATES.md).

## Prüfstand

Die aktuelle Version wird öffentlich mit ARMv7-, ARM64- und AMD64-Varianten veröffentlicht. Lokale ARM64-Containerprüfungen liegen vor; ARMv7 wurde in früheren Versionen zusätzlich unter Emulation geprüft. Auf einem echten Pi 4B wurden Neustart, automatischer Dienststart und Dashboard-Zugriff im Heimnetz geprüft. Eine über einen Philips-TV ausgelöste Pfeiltaste wurde am Pi empfangen. Die echte Philips-Fernbedienung wurde vom Benutzer bestätigt. Drei Browser-Updates bis v0.1.13 und die Passwortbeständigkeit nach Containerneustart sind ebenfalls am Pi geprüft. Protect-Livebild, GPIO, tatsächliche Abschaltzyklen, WLAN-Ausfall und der vollständige Ablauf mit der neuen Kameraauswahl bleiben gesondert zu prüfen. Siehe [Geräteprüfung](ABNAHME.md).
