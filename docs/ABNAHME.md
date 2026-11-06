# Prüfprotokoll und Gerätekompatibilität

**Stand: 06.11.2026 · App v0.1.13 · Prüfaufbau: Raspberry Pi 4B und Philips 55PUS6581/12.**

Der reale Aufbau wurde für automatischen Start, Dashboard-Zugriff, HDMI-CEC-Tastenempfang, App-Updates und Passwortverwaltung erfolgreich geprüft. Die echte Philips-Fernbedienung bewegte die sichtbare Auswahl; der Benutzer bestätigte die funktionierende Bedienung. Der abschließende Installationscheck nach dem Update und der Passwortänderung war vollständig erfolgreich.

Das ist eine Bestätigung der hier aufgeführten Funktionen. Eine vollständige Abnahme aller Kameras, des GPIO-Tasters und des Fernzugriffs ist damit nicht verbunden. Private Adressen, Zugangswerte, Rohprotokolle und echte Kamerabilder bleiben außerhalb dieses Repositories.

## Geprüfter Aufbau

| Bestandteil | Festgestellter Stand |
| --- | --- |
| Raspberry Pi | Raspberry Pi 4 Model B Rev 1.2, ARM64 (`aarch64`). |
| Betrieb | Raspberry Pi OS mit grafischer Desktop-Sitzung und Autostart. |
| Fernseher | Philips **55PUS6581/12**. |
| Bedienung | TV-Fernbedienung über HDMI-CEC, EasyLink und EasyLink-Fernbedienung aktiviert. |
| HDMI | Verbindung zwischen Pi und TV; Auswahl des angeschlossenen CEC-Adapters. Zuletzt war `/dev/cec0` verbunden. |
| Dashboard | Passwortgeschützt, direkt über die Pi-IP im Heimnetz von einem zweiten Gerät geöffnet. |
| Installierte App | v0.1.13, offizielles ARM64-Image. |
| GPIO | Kein physischer Taster angeschlossen; keine GPIO-Geräteabnahme. |
| Protect | Zugang und Kamerakonfiguration vorhanden; keine vollständige Livebild-/Ereignisabnahme des realen NVR dokumentiert. |

Der TV-Modellnachweis, die empfangenen CEC-Nachrichten und Screenshots des Auswahlwechsels wurden privat festgehalten. Der Test belegt kein allgemeines Funktionieren mit allen Philips-Geräten oder anderen Herstellern. Ein ARC-Anschluss allein bestätigt keinen CEC-Tastenempfang.

## Am Gerät bestätigte Ergebnisse

| Prüfung | Beobachtung | Umfang |
| --- | --- | --- |
| Automatischer Start | Nach regulärem Pi-Neustart liefen Dashboard und verwaltete Dienste wieder an. | Am Prüfgerät vor den späteren Funktionsupdates beobachtet; beim endgültigen Aufstellen erneut prüfen. |
| Dashboard über Pi-IP | Anmeldung, Einstellungen, Versionsprüfung und Wartung direkt im Browser erreichbar. | Erfolgreich am realen Pi, ohne SSH-Tunnel für den Browseraufruf. |
| TV-Fernbedienung | Vom TV gerichtete CEC-Tasten kamen am Pi an und bewegten die Auswahl. | Benutzer bestätigte die reale Fernbedienungsfunktion; kein kompletter Test aller Tasten und Playerzustände. |
| v0.1.10 → v0.1.11 | Update über die Wartungsseite gestartet, bestätigt und erfolgreich abgeschlossen. | Daten erhalten. Verbliebene Markierung einer früher abgebrochenen Einrichtung gesichert und korrigiert. |
| v0.1.11 → v0.1.12 | Update über die Wartungsseite erfolgreich. Neue Version und Prüfzeit im Browser sichtbar. | Ohne manuelle Dienstreparatur; Kameraeinstellungen, Passwort und TV-Kopplung erhalten. |
| v0.1.12 → v0.1.13 | Update über die Wartungsseite erfolgreich. Container gesund, drei Dienste aktiv, Wartungslaufzeit aktuell. | Vorher-nachher-Vergleich der privaten Einstellungen erfolgreich. |
| Passwortänderung | Authentifizierte App-Schnittstelle speicherte den neuen Zugang; altes Passwort und alte Sitzung wurden abgewiesen. | Echte Anmeldung mit dem neuen Passwort im Browser nach Containerneustart bestätigt. Das Formular wurde angezeigt; das Absenden des Formulars durch einen Benutzer wurde nicht gesondert beobachtet. |
| Abschlussdiagnose | Dashboard, Dienstschlüssel, Dateirechte, Laufzeit, Container und Wartung erfolgreich geprüft. | Alle drei Benutzer-Dienste aktiv, jeweils keine automatischen Fehlerneustarts beim Abschlusscheck. |

Für die Updateaufträge wurde die echte Dashboard-Oberfläche benutzt. SSH diente zusätzlich dem Vergleich der Einstellungen, der Diagnose und der separat angeforderten Passwortumstellung über die App-Schnittstelle. Der reguläre Updateauftrag benötigt keinen SSH-Befehl.

## Software- und Containerprüfungen

Der veröffentlichte App-Quellstand von v0.1.13 ist `c76cd0e1f281745fb4b860577b179b8ae2c00d15`.

| Prüfung | Ergebnis und Nachweis |
| --- | --- |
| Python | **159 Tests erfolgreich** in [Linux-CI](https://github.com/loserat/kamerablick/actions/runs/42277207929). |
| JavaScript | **40 Prüfungen erfolgreich** für Navigation, Statusdarstellung und Fernbedienungszustellung im selben Lauf. |
| Release | [Image-Veröffentlichung](https://github.com/loserat/kamerablick/actions/runs/42277209123) erfolgreich; ARM64, ARMv7 und AMD64 im Image-Index bestätigt. |
| Öffentlicher Download | ARM64-Image ohne GitHub-Anmeldung heruntergeladen; Versions- und Quellstandlabels stimmen mit dem Tag überein. |
| Image-Funktion | Start, Login, geschützte Update-/Kameraschnittstellen, Passwortrotation, Sitzungswiderruf und Ablehnung privater Dateipfade geprüft. |
| Große Kameraauswahl | Vier gespeicherte Beispielkameras im Browser bei 1280×720, 1920×1080 und 3840×2160; Pfeile, OK, Zurück und Ausschaltbestätigung geprüft. |
| Wiederherstellung | Vorhandene isolierte Docker-Labore prüfen echte Containerwechsel, Rückkehr, Unterbrechung und datenerhaltende Neuinstallation mit Testgegenstellen für GitHub und systemd. Diese Labornachweise stammen teilweise aus früheren Versionen und sind keine neue Geräteprüfung von v0.1.13. |

Der lokale Docker-Testlauf von v0.1.13 führte ebenfalls 159 Tests aus und übersprang einen Test für den dort fehlenden systemd-Parser. Der vollständige Linux-CI-Lauf ist der maßgebliche Nachweis für diese Parserprüfung.

Die anonymisierte Zusammenfassung ist als [JSON-Prüfstand](verification/v0.1.13.json) verfügbar. Sie enthält Ergebnisse und öffentliche Referenzen, keine privaten Rohdaten. Reproduzierbare Testbefehle stehen unter [Entwicklung](ENTWICKLUNG.md).

## Noch am Ziel zu verifizieren

| Funktion | Erforderliche Beobachtung |
| --- | --- |
| Echter Protect-NVR | Zugang und Berechtigungen, korrektes Standbild und flüssiges aktuelles Livebild am TV. Protect-/Kameraversion und tatsächlich verwendete Qualität festhalten. |
| Ereignisse | Echte Bewegung, Person und Fahrzeug soweit unterstützt; Zeitpunkte und Aktualitätsanzeige mit der Konsole vergleichen. |
| Mehrere reale Kameras | Jede Kamera öffnen und aus dem echten Player zur neuen großen Auswahl zurückkehren; Fokus und Fernbedienung erneut prüfen. |
| GPIO | Verdrahteten Taster mehrmals betätigen; Einschalten, zweiter Druck Standby und Entprellung beobachten. |
| Abschaltung und Standby | Gewählte Abschaltzeit messen und das tatsächliche Verhalten des Fernsehers prüfen. Ein gesendeter CEC-Befehl allein ist keine Standby-Bestätigung. |
| Ausfälle | Tatsächlichen Stream-/NVR-Ausfall, Rückkehr, sichtbaren Bildfortschritt und unveränderten Abschaltzeitpunkt prüfen. |
| Endgültiger Standort | WLAN, Netzpfade, Kaltstart mit zunächst ausgeschaltetem TV und erneuten Start nach Stromausfall kontrolliert testen. |
| Privater Fernzugriff | VPN einrichten und Dashboard sowie SSH aus einem fremden Netz einschließlich Pi-Neustart prüfen. |
| Alltag | Bedienung gemeinsam mit der Oma vor Ort ausprobieren. |

Diese Punkte bleiben offen, bis ein konkreter Gerätenachweis vorliegt. Erfolgreiche Softwaretests oder ein gespeicherter NVR-Zugang ersetzen sie nicht.

## Eigene Installation abnehmen

1. Im Projektordner als Installationsbenutzer `python3 .runtime/current/doctor.py --root "$PWD"` ausführen. Das Programm liest nur und schaltet den Fernseher nicht.
2. Dashboard auf einem zweiten Gerät über `http://PI-IP:8088` öffnen. Anmeldung, Version und Updatebereitschaft prüfen.
3. Kamera am NVR einrichten, Standbild laden und Livebild am TV durch eine sichtbare Bewegung kontrollieren.
4. Mit der echten Fernbedienung Pfeile, OK, Zurück, Halten/Loslassen und Wechsel aus dem Player prüfen. Ausschalten zuerst abbrechen und danach bewusst bestätigen.
5. Optionalen Taster bei ausgeschaltetem Pi korrekt verdrahten, anschließend Tasterzyklen und Abschaltzeit beobachten.
6. Fehler-/Wiederanlaufprüfung lokal kontrolliert durchführen. Keine WLAN-Unterbrechung über den einzigen Fernzugang auslösen.
7. Ein verfügbares veröffentlichtes Update über Wartung installieren und erhaltene Einstellungen sowie erneute Gerätefunktion prüfen.
8. VPN-Prüfung nach [Fernzugriff](FERNZUGRIFF.md) durchführen und den Alltagstest abschließen.

Für jeden Schritt Datum, App-/OS-Version, Ergebnis und einen konkreten Nachweis privat aufbewahren. Quellen, Sicherungen und bisherige Testnachweise bei der Speicherpflege erhalten. Der öffentliche Prüfstand wird nur um tatsächlich bestätigte Ergebnisse ergänzt.
