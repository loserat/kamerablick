# Zu Kamerablick beitragen

Kamerablick soll im Alltag einfach bleiben: große Bedienelemente, gut sichtbarer Fokus und wenige Schritte bis zum Kamerabild.

Für Fehler und Vorschläge bitte ein [Issue](https://github.com/loserat/kamerablick/issues) erstellen. Hilfreich sind Pi-Modell, Betriebssystem, Kamerablick-Version, erwartetes Verhalten und die Schritte zum Nachstellen. Bei HDMI-CEC auch das TV-Modell nennen. Passwörter, API-Schlüssel, Stream-Adressen und private Kamerabilder vorher entfernen.

Für Änderungen einen kleinen Pull Request mit Beschreibung und passenden Prüfergebnissen öffnen. Die lokale Einrichtung und Prüfprogramme stehen in [Entwicklung und Tests](docs/ENTWICKLUNG.md). Automatische Prüfungen laufen für Pull Requests und Änderungen an `main`; Container werden erst mit einem Versions-Tag veröffentlicht.

Quellcode liegt in `app/` und `pi/`, Tests in `tests/`, Anleitungen in `docs/`. Erzeugte Prüfberichte, lokale Konfiguration, Sicherungen und Zugangsdaten gehören nicht in Git. Hardwaretests getrennt von Simulationen und Containerprüfungen beschreiben.

Ein Sicherheitsproblem bitte über den in [SECURITY.md](SECURITY.md) beschriebenen Weg melden.
