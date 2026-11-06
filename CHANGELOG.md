# Änderungen

## v0.1.11

- Große TV-Kameraauswahl mit höchstens zwei Kacheln nebeneinander, an die Auflösung angepassten Schriften und klarer Auswahlmarkierung.
- Mehrere manuelle RTSP-/RTSPS-Kameras speichern, ohne bisherige Einträge zu überschreiben; bestehende einzelne manuelle Kamera übernehmen.
- Kameraliste für Protect und eigene Streams, Einrichtung weiterer Protect-Streams im geschützten Dashboard und getrennte TV-Auswahl ohne Zugriff auf Stream-Adressen oder Zugangswerte.
- Pfeile, OK und Zurück für Kamerawechsel; Rückkehr zur zuletzt gewählten Kachel. Sichere Ausschaltbestätigung bleibt erhalten.
- 152 Python-Tests und 40 JavaScript-Prüfungen in Linux-CI bestanden; öffentliche Images für ARM64, ARMv7 und AMD64. Unabhängiger ARM64-Image-Test ohne GitHub-Anmeldung bestanden.
- Browserprüfung mit vier Beispielkameras bei HD, Full HD und 4K. Dashboard-Update von v0.1.10 auf v0.1.11 auf einem echten Pi 4B erfolgreich, einschließlich Datenerhalt. Die Restmarkierung einer früher abgebrochenen Einrichtung wurde dort gesichert und korrigiert; anschließend war die Installationsdiagnose vollständig erfolgreich.

Echte Protect-Wiedergabe, GPIO und Fernzugriff sind gesondert am Ziel zu prüfen. Die größere Ansicht und der Wechsel aus einem echten Kamerabild benötigen die Beobachtung vor Ort. [Geräteprüfung und Nachweise](docs/ABNAHME.md).

## v0.1.10

- Der verwaltete TV-Browser wird beim Dienststopp ausdrücklich beendet, auch wenn Chromium in einem eigenen Systemd-Bereich läuft.
- Übersetzungshinweise im TV-Browser unterdrückt. Dadurch überlagern sie die Fernbedienungsansicht nicht.

## v0.1.9

- Den tatsächlich verbundenen HDMI-CEC-Adapter auswählen und nach einem Portwechsel erneut prüfen.
- TV-Browser mit eigenem Passwortspeicher starten, damit keine Schlüsselbund-Abfrage eine Tastatur am Pi verlangt.

Ältere Versionshinweise stehen unter [GitHub Releases](https://github.com/loserat/kamerablick/releases). Veröffentlichte Tags werden nicht nachträglich verändert.
