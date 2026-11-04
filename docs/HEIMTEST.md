# Zu Hause mit dem eigenen NVR testen

NVR-Zugang, Kameraauswahl, Standbild und manuell eingetragene Kameras lassen sich vor dem Einsatz am Fernseher in der Oberfläche einrichten. Für den Heimtest gibt es einen getrennten Betriebsmodus mit eigenem Datenvolume. Er verbindet echte Protect-Kameras; Taster und TV-Aktionen bleiben simuliert.

## Einmal starten

Mit installierter Docker Engine beziehungsweise Docker Desktop und Compose v2:

```sh
git clone --branch v0.1.8 https://github.com/loserat/kamerablick.git ~/kamerablick-heimtest
cd ~/kamerablick-heimtest
cp .env.example .env
```

In der lokalen `.env` einen eigenen Wert für `DASHBOARD_PASSWORD` eintragen und den Platzhalter ersetzen. Die Datei bleibt privat. Danach:

```sh
docker compose -f compose.home-test.yaml up -d
```

`http://127.0.0.1:8088` öffnen und mit dem selbst gewählten Dashboard-Passwort anmelden. Falls Port 8088 bereits belegt ist, `HOME_TEST_PORT=8089` in `.env` ergänzen und anschließend Port 8089 im Browser öffnen. Der Heimtest verwendet weder GPIO noch HDMI noch den Docker-Socket.

## Den NVR in der App anmelden

1. **Kamera** öffnen und die lokale NVR-Adresse eingeben.
2. **Lokaler UniFi-Benutzer** auswählen, lokalen Benutzernamen und Passwort eintragen. Ein ui.com-Konto beziehungsweise eine Anmeldung mit MFA wird nicht unterstützt.
3. Falls die Konsole ein eigenes Zertifikat verwendet, den angezeigten SHA-256-Fingerabdruck über einen vertrauenswürdigen Zugang mit der Konsole vergleichen und erst dann bestätigen.
4. Verbinden, eine erreichbare Kamera auswählen und das Standbild prüfen. Qualität auswählen und die Kamera übernehmen.

Der lokale Anmeldeweg nutzt die UniFi-OS-Sitzung. Je nach Protect-Version wird für die Stream-Schnittstelle zusätzlich ein API-Schlüssel benötigt. Er kann im selben Formular unter **API-Schlüssel (optional)** eingetragen werden. Laufende Bewegungsereignisse verwenden die öffentliche Integration-API und benötigen diesen Schlüssel. Alternativ lässt sich direkt die Anmeldung **API-Schlüssel** wählen.

Für die lokale Anmeldung werden bestehende RTSP-Freigaben erkannt. Fehlt eine Freigabe oder liefert die Protect-Version keine Stream-Aliase mehr, zeigt die Oberfläche den nächsten Schritt an. Ohne API-Schlüssel werden keine privaten Kamera-Einstellungen umgeschrieben. Mit Schlüssel kann ein fehlender Stream nach ausdrücklicher Freigabe im Assistenten aktiviert werden.

Passwort, API-Schlüssel und Sitzungs-Cookies werden nicht an die Browser-Antworten angehängt. Der lokale Benutzername ist für den angemeldeten Dashboard-Benutzer sichtbar. Passwort und Schlüssel werden erst zusammen mit der übernommenen Kamera in der privaten lokalen Konfiguration gespeichert; ein abgebrochener Assistent überschreibt keinen vorhandenen Zugang. UniFi-Sitzungs-Cookies werden nur im Speicher gehalten.

## Standbild in der Übersicht

Nach dem Übernehmen der Protect-Kamera unter **Übersicht → Standbild laden** ein Bild abrufen. **Aktualisieren** lädt ein neues Bild; der angezeigte Zeitpunkt bezeichnet den Abruf. Es gibt keine automatische Bildabfrage. Beim Wechsel der Kamera oder Abmelden wird die Vorschau entfernt. Manuelle Streams und Beispielkameras haben hier kein Standbild. Das Livebild läuft später direkt auf dem Pi am Fernseher.

## Manuell hinzufügen und prüfen

Mit **Streamadresse verwenden** einen Namen und die vorhandene RTSP-/RTSPS-Adresse eingeben. **Kamera speichern** wählt diese Kamera für die TV-Ansicht aus. Der vorhandene NVR-Zugang bleibt erhalten. Aktuell gibt es eine aktive TV-Kamera.

Unter **Wartung → Verbindung prüfen** werden die gespeicherte NVR-Anmeldung, Kameraliste, das Standbild und die Stream-Adresse erneut gelesen. Eine erfolgreiche Prüfung bestätigt noch keine laufende Videowiedergabe. Bei einer manuell eingegebenen Kamera ohne NVR-Zuordnung erfolgt die Livebildprüfung später am Pi.

NVR-Zugang, Bildqualität, aktive Kamera, GPIO-Pin und Abschaltzeit werden in der Oberfläche verwaltet. Betriebssystem, Docker, WLAN, SSH und VPN werden einmalig am Gerät eingerichtet. App-Updates auf einer verwalteten Pi-Installation erfolgen über [Browser-Updates](BROWSER-UPDATES.md). Der getrennte Heimtest installiert keine Pi-Updates.

## Danach am Pi

Für echte Wiedergabe, Taster und Fernseher gilt die [Pi-4-Installation](PI4.md). Den NVR-Zugang dort im Dashboard einrichten. Die Daten des Heimtests sind absichtlich von der späteren Pi-Installation getrennt. WLAN am Aufstellort, Livebild, GPIO, HDMI-CEC, Wiederanlauf und Fernzugriff anschließend nach [ABNAHME.md](ABNAHME.md) prüfen.
