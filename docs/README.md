# Kamerablick dokumentiert

Diese Anleitungen beschreiben den veröffentlichten Stand **v0.1.14**. Der dokumentierte Gerätetest stammt von v0.1.13. Für v0.1.14 wurde noch kein neuer Pi-Test durchgeführt. Der Aufbau mit Raspberry Pi 4B und Philips 55PUS6581/12 ist für die in der [Geräteprüfung](ABNAHME.md) genannten Funktionen bestätigt. Softwaretests, Prüfungen am Gerät und noch offene Punkte werden dort getrennt geführt.

## Einrichten

1. [Pi 4B mit WLAN und Desktop vorbereiten](PI4.md).
2. [Kamerablick installieren und die Bereitschaft prüfen](INSTALLATION.md).
3. [Kameras verbinden, Passwort festlegen und den TV bedienen](BEDIENUNG.md).
4. [Fernbedienung und CEC prüfen](FERNBEDIENUNG.md).
5. [Die eigene Installation am Ziel abnehmen](ABNAHME.md).

Ein Test am eigenen NVR ohne TV-/GPIO-Befehle ist über den getrennten [Heimtest](HEIMTEST.md) möglich. Der [Pi 2B mit LAN](PI2.md) bleibt eine Alternative; die Geräteprüfung dieses Projekts bezieht sich auf den Pi 4B.

## Im Alltag

| Aufgabe | Anleitung |
| --- | --- |
| Kamera wechseln oder das Passwort ändern | [Bedienung](BEDIENUNG.md) |
| Neue App-Version installieren | [Browser-Updates](BROWSER-UPDATES.md) |
| Dienste, Sicherungen und Speicher prüfen | [Wartung](WARTUNG.md) |
| Eine konkrete Fehlermeldung eingrenzen | [Fehlersuche](FEHLERSUCHE.md) |
| Letzte Bewegung und Kamerastatus verstehen | [Telemetrie](TELEMETRIE.md) |
| Zugriff von unterwegs einrichten | [Privater Fernzugriff](FERNZUGRIFF.md) |

## Technik und Nachweise

| Inhalt | Quelle |
| --- | --- |
| Komponenten, Ports, Zugang und Datenhaltung | [Architektur](ARCHITEKTUR.md) |
| Testaufbau, Ergebnisse und offene Hardwareprüfungen | [Geräteprüfung](ABNAHME.md) |
| Anonymisierte Zusammenfassung des geprüften Releases | [Prüfstand v0.1.13](verification/v0.1.13.json) |
| Lokale Tests und Docker-Labore | [Entwicklung](ENTWICKLUNG.md) |
| Veröffentlichte Änderungen | [Changelog](../CHANGELOG.md) |
| Projektbeiträge | [Contributing](../CONTRIBUTING.md) |
| Sicherheit und private Fehlermeldungen | [Security](../SECURITY.md) |

Die Dokumentation unter `main` kann nach einem Release ergänzt werden. App-Updates orientieren sich an veröffentlichten Versions-Tags und den zugehörigen Docker-Images, nicht an jeder Dokumentationsänderung. Private Rohprotokolle, Konfigurationen und Gerätescreenshots bleiben außerhalb des öffentlichen Repositories.
