# Goal-Abnahme Kamerablick

Stand: 31.10.2026. Die Software ist vorbereitet; das Goal ist wegen der noch offenen Geräteabnahme nicht erreicht. Das Zielgerät ist jetzt ein Raspberry Pi 4B mit WLAN; vorgesehen ist Raspberry Pi OS (64 Bit) mit Desktop. Adresse und installierter Systemstand sind noch nicht bekannt. „Instant“ wurde als Protect-Zentrale genannt; genaue Gerätebezeichnung/Version und TV-Modell fehlen.

| Anforderung | Aktueller Nachweis | Noch erforderlich |
|---|---|---|
| Wiederholbare Pi-Installation | ARMv7-/ARM64-Voraussetzungenprüfung, Dateierhalt und Installation mit Image-Laufzeit automatisch getestet; CEC als eigener Hilfsprozess | Pi 4B mit 64-Bit-Desktop installieren und Geräteberechtigungen prüfen |
| Dashboard mit Protect-Einrichtung | HTTP-Tests für Anmeldung, Kameraauswahl, Schlüsseltrennung und Zertifikatprüfung; lokaler UniFi-Login mit TLS-Testkonsole, Sitzungsablauf und API-Schlüssel-Alternative geprüft | Live-Verbindung zum Instant, Standbild und Stream prüfen |
| Große TV-Ansicht | Tastatur-/Browserprüfung und Navigationstests | Kioskstart und Browser-/Playerfokus auf dem Pi |
| GPIO und TV-Standby | Steuerlogik in simulierten Hardwaretests | Verdrahteter Taster und echtes HDMI-CEC |
| TV-Fernbedienung | CEC-Empfang und eigene TV-Zustellung implementiert; Dopplungs-/Ausfalltests und Browser mit simulierten Eingaben bestanden; echter ARM64-Trixie-Helfer ohne Adapter geprüft | Modell bestimmen; libCEC-Gerätezugriff, reale Tasten, Halten/Loslassen und Rückkehr aus mpv am Pi prüfen |
| Kamerastatus / letzte Bewegung | Laufende Status-/Ereigniserfassung mit Speicherung und Altersprüfung; gegen lokale TLS-/WebSocket-Konsole geprüft | Version und Ereignisse am Instant prüfen; realen Kamera- und Netzwerkausfall testen |
| Automatischer Start | Installierte Services/Autostartdateien gegen temporäre Benutzerverzeichnisse geprüft | Desktop-Neuanmeldung und Strom-Neustart auf dem Pi |
| Netzwerk-/Kameraausfall | Stillstands-, IPC-Zeitüberschreitungs- und Abschaltlogik automatisch geprüft; echter ARM64-mpv mit erzeugtem Testvideo erkennt Stillstand, startet neu und erhält die Abschaltzeit; echtes RTSP/RTSPS mit Produktionszeitgrenzen für Kameraausfall, lautlosen Stillstand und Serverneustart auf ARM64 geprüft; Ereignisabbruch und Wiederverbindung gegen lokale TLS-/WebSocket-Konsole geprüft | Pi im Zielnetz, echte Protect-Neustarts und das sichtbar aktuelle Kamerabild am TV prüfen |
| Versionierte Updates | Lokale Versionswahl, gemeinsame Pi-Laufzeit und Rückkehrpfade getestet; öffentliches Release v0.1.0 und ARMv7-/ARM64-/AMD64-Image veröffentlicht, anonymer ARMv7-Abruf geprüft | Installation, Aktualisierung und Rückkehr am Pi 4B prüfen |
| Echter Containerbetrieb | Lokale ARM64- sowie ARMv7/32-Bit-Docker-Abnahme unter Emulation; Bericht neben Projektpaket | Keine Gleichsetzung mit GPIO-/CEC-/Pi-Abnahme |
| Privater Fernzugriff | SSH-/VPN-Weg dokumentiert, keine Portfreigabe | VPN/SSH am Ziel einrichten und aus fremdem Netz prüfen |
| Bedienungsanleitung | README, docs/INSTALLATION, docs/FERNBEDIENUNG und diese Abnahme vorhanden | Nach echten Geräteeinstellungen abschließend gegenprüfen |

## Abfolge am späteren Gerät

1. Modell, OS-Architektur und benötigte Geräte/Programme prüfen.
2. Installieren und Anmeldung im Dashboard testen.
3. Protect verbinden; Standbild und flüssige Videowiedergabe prüfen.
4. Taster einschalten, zweiter Druck Standby; Abschaltzeit prüfen.
5. Kamerabild mit Zurück verlassen; TV muss eingeschaltet bleiben.
6. TV- und Pi-Neustart sowie ausgeschalteten TV beim Pi-Boot prüfen.
7. WLAN-Empfang am TV prüfen, Netzwerk trennen und wieder verbinden sowie einen WLAN-Neustart testen; Status darf keinen aktuellen Zustand vortäuschen.
8. Empfangene Fernbedienungstasten prüfen und erst dann als unterstützt markieren.
9. Update mit Sicherung durchführen; Rückkehr zur bekannten Version ausprobieren.
10. VPN-Zugriff von außerhalb und danach die alltägliche Bedienung ohne technische Hilfe prüfen.

Nicht getestete Punkte bleiben offen. Weder ein grüner HTTP-Test noch eine Demo beweisen die physische Funktion.

## Aktueller Abschlussstand

Die lokale Softwareprüfung umfasst 102 Python-Tests, 32 JavaScript-Prüfungen und ergänzende native ARM64-Abnahmen. Die ARMv7/32-Bit-Abnahme hat Anmeldung, Konfigurationsspeicherung, Neustart, Versionswechsel und Rückkehr unter Emulation geprüft. Der Streamtest prüft zehn Fälle mit echtem mpv und MediaMTX einschließlich Ausschalten während einer ausgefallenen Videoquelle. Es wird ausschließlich erzeugtes Testvideo ohne HDMI-Ausgabe genutzt. Die erzeugten JSON-Prüfberichte werden außerhalb des Git-Repositories archiviert; der Streambericht enthält die geprüften Quellprüfsummen. Die reproduzierbaren Prüfprogramme bleiben unter `tests/`.

Für den Abschluss fehlen der Zugriff auf den nun benannten Pi 4B, das TV-Modell und der erreichbare Zielzugang zur Instant-Zentrale. Im Projekt ist keine verwaltete Geräteinstallation und kein produktiver Protect-Zugang vorhanden. Installation, WLAN am TV-Standort, grafischer Autostart nach Stromausfall, GPIO-Verdrahtung, IR-/CEC-Tasten und privater Fernzugriff müssen deshalb noch vor Ort beziehungsweise am Zielgerät geprüft werden.

Der nächste Arbeitsschritt ist die Geräteinbetriebnahme mit Pi-Desktop und SSH-Zugang. Das vollständige Goal bleibt bis zu diesen Nachweisen unerfüllt.
