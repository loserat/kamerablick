# Kameras einrichten und am TV bedienen

## Für die Einrichtung

Das Dashboard im selben Heimnetz unter `http://PI-IP:8088` öffnen. Das Dashboard-Passwort gehört zur Kamerablick-Installation; es ist nicht das UniFi-Passwort. Das bei der Installation erzeugte Passwort steht nur lokal in `~/kamerablick/.env`. Zugangswerte nicht in Issues, Screenshots oder GitHub übernehmen.

### UniFi Protect

1. **Kameras** öffnen und den lokalen NVR verbinden. Die unterstützten Anmeldearten und erforderlichen Rechte stehen in [Installation](INSTALLATION.md).
2. Eine Kamera und Bildqualität auswählen, das Standbild prüfen und die Kamera übernehmen.
3. Weitere Kameras stehen unter **Kameras am Fernseher**. Über **Für TV einrichten** den Stream der gewünschten Kamera vorbereiten und sie als Startkamera auswählen. Das kann eine Freigabe des RTSPS-Streams auf dem NVR auslösen; hierfür sind entsprechende Protect-Rechte nötig.

Die TV-Ansicht zeigt die Kameras der verbundenen Protect-Zentrale. Die Metadaten werden zwischengespeichert; eine Änderung im NVR kann deshalb ungefähr eine Minute benötigen. Eine als nicht erreichbar gemeldete Kamera ist nicht auswählbar. Ein erreichbarer NVR oder ein Standbild beweist noch keine funktionierende Livewiedergabe am Pi.

### Eigene Kamera hinzufügen

Unter **Eigene Kamera hinzufügen** einen verständlichen Namen und die vorhandene RTSP-/RTSPS-Adresse eingeben. Weitere Kameras auf dieselbe Weise ergänzen. Frühere Einträge bleiben erhalten; dieselbe Stream-Adresse aktualisiert den vorhandenen Eintrag. Es lassen sich bis zu 24 eigene Kameras speichern. Die App verwahrt diese Adressen privat in `manual-cameras.json` im Datenvolume.

In **Kameras am Fernseher** eine gespeicherte Kamera mit **Als Startkamera** auswählen. Eigene, gerade nicht ausgewählte Kameras lassen sich dort nach Bestätigung entfernen. Protect-Kameras werden auf der Protect-Zentrale verwaltet.

### Weitere Einstellungen

Unter **Einstellungen** GPIO-Pin und automatische Abschaltzeit einstellen. Unter **Wartung** Verbindung, Fernbedienung, TV-Zugang und Updates prüfen. Den internen Pi-Dienst oder Wartungsport nicht im Netzwerk freigeben. Der Zugriff von unterwegs erfolgt über ein gesondert eingerichtetes [VPN](FERNZUGRIFF.md).

## Für die Oma am Fernseher

| Taste/Aktion | Ergebnis |
| --- | --- |
| Pfeile | Eine Kamera auswählen; die helle Kachel zeigt die Auswahl. |
| OK | Die ausgewählte Kamera öffnen. |
| Zurück | Das Bild schließen und wieder Kameras auswählen. |
| Fernseher ausschalten | Bestätigung öffnen; zuerst ist **Nein, zurück** ausgewählt. |

Die Ansicht zeigt höchstens zwei große Kacheln nebeneinander. Schriften und Bedienelemente wachsen mit der Bildschirmauflösung. Bei mehr Kameras kann die Auswahl weiter nach unten führen. Die zuletzt gewählte Kamera bleibt beim Zurückgehen fokussiert. Es wird jeweils ein Kamerabild gezeigt. Zum Wechseln mit **Zurück** in die Auswahl gehen und eine andere Kamera öffnen.

Die TV-Anwendung läuft direkt auf dem Pi. Ein zusätzlich im Laptop-Browser geöffnetes TV-Fenster erhält nicht automatisch die Fernbedienungstasten des Fernsehers. Der Videoplayer läuft außerhalb des Dashboards auf dem Pi; das Dashboard bietet Status und Standbild.

## Wenn etwas nicht reagiert

- **Bild vorhanden, aber keine Pfeiltasten:** [Fernbedienung und HDMI-CEC prüfen](FERNBEDIENUNG.md). Bei Philips auch EasyLink-Fernbedienung aktivieren. Ein TV-Neustart kann nach einem Gerätewechsel eine veraltete CEC-Zuordnung beheben.
- **Kamera nicht erreichbar:** NVR-Verbindung und Kamera im Dashboard prüfen. Keine Zugangswerte zurücksetzen, bevor die Ursache geklärt ist.
- **Keine Kamera auswählbar:** Unter Kameras einen Stream einrichten. Kamera und TV-Zugang bleiben bei normalen App-Updates erhalten.
- **Alte Oberfläche nach einem Update:** Dashboard einmal neu laden und bei Bedarf mit dem bisherigen Passwort anmelden. Der Pi startet seine TV-Anwendung beim Update selbst neu.
