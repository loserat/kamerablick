# Architektur und Datenhaltung

Kamerablick trennt die Einrichtung im Browser von den Gerätefunktionen des Raspberry Pi. Die TV-Fernbedienung wird über HDMI-CEC an den Pi weitergegeben; ein eigener IR-Empfänger gehört nicht zum geprüften Aufbau.

## Komponenten

| Komponente | Quelle | Aufgabe |
| --- | --- | --- |
| Dashboard | `app/server.py`, `app/static/` | Anmeldung, Kameraverwaltung, Einstellungen, Status, Standbilder und Updatebestätigung. |
| Protect-Anbindung | `app/protect.py`, `app/local_protect.py` | Lokaler UniFi-Login oder API-Schlüssel, Zertifikatprüfung und Stream-Ermittlung. |
| Ereignisverarbeitung | `app/telemetry.py` | Kamerastatus und zuletzt empfangene Ereignisse mit Aktualitätsprüfung. |
| Pi-Dienst | `pi/agent.py` | GPIO-Taster, Playerstart, Abschaltzeit und Geräteaktionen. |
| CEC-Brücke | `pi/cec_bridge.py` | Verbundenen Adapter wählen, Tasten empfangen und Schaltbefehle über denselben `cec-client` übergeben. |
| TV-Browser | `pi/kiosk.py`, `app/static/tv.*` | Eigenes Chromium-Profil und vereinfachte TV-Auswahl. |
| Playerüberwachung | `pi/player_health.py` | Fortschritt von mpv prüfen und Wiederverbindung unterstützen. |
| Sitzungsstart | `pi/session.py` | Grafische Desktop-Umgebung an die Benutzer-Dienste übergeben. |
| Wartung | `pi/maintenance.py`, `pi/update_job.py`, `pi/update.py` | Unabhängiger Updateauftrag, Sicherung, Versionswechsel und Wiederherstellung. |
| Installation und Diagnose | `pi/install.py`, `pi/doctor.py`, `pi/reinstall.py` | Voraussetzungen prüfen, verwaltete Laufzeit einrichten und bestehende Daten erhalten. |

Das Livevideo wird von **mpv auf dem Pi** ausgegeben. Im Dashboard erscheinen Status und bei Protect ein ausdrücklich geladenes Standbild. Es gibt kein Livevideo-Streaming vom Pi in den Dashboard-Browser.

## Zugänge und Ports

| Verbindung | Standard | Zugriff |
| --- | --- | --- |
| Browser → Dashboard | `http://PI-IP:8088` | Dashboard-Passwort und danach eine zeitlich begrenzte Sitzung. |
| Dashboard → Pi-Dienst | `127.0.0.1:8091` | Privater lokaler Dienstschlüssel. |
| Dashboard → Wartung | `127.0.0.1:8093` | Privater lokaler Dienstschlüssel. |
| Pi → Protect | Konfigurierte lokale Konsole und Stream-Adresse | UniFi-Sitzung beziehungsweise API-Schlüssel; Zertifikatprüfung für die Konsolenverbindung. |
| TV-Browser → Dashboard | Lokaler Dashboard-Aufruf | Begrenzter TV-Zugang sowie eigener reiner Empfangszugang für CEC-Tasten. |

Die normale Pi-Compose-Konfiguration nutzt das Host-Netzwerk, damit das Dashboard lokale Dienste erreichen kann. Der Container hat dennoch keinen Docker-Socket, keine Gerätemounts, keine zusätzlichen Linux-Fähigkeiten und kein beschreibbares Root-Dateisystem. `/data` ist ein eigenes persistentes Volume, `/tmp` temporär. Die Containerlogs sind begrenzt.

Dashboard- und TV-Berechtigungen sind getrennt. Der TV-Zugang erlaubt keine Kameraeinrichtung oder Passwortänderung. Nur die lokale Kiosk-Instanz erhält den Empfangszugang für die TV-Fernbedienung. Der zeitlich begrenzte Update-Statuszugang erlaubt ausschließlich das Beobachten des bereits bestätigten Auftrags.

## Betriebsarten

| Modus | Kameraverbindung | Geräteaktionen | Daten |
| --- | --- | --- | --- |
| Pi-Installation | Echter NVR oder gespeicherter Stream | Lokaler Pi-Dienst für CEC, GPIO und mpv | Produktives Datenvolume. |
| Heimtest | Echter NVR möglich | Simuliert; keine GPIO-/TV-Befehle | Eigenes Heimtest-Volume und nur lokaler Browserport. |
| Demo | Erzeugte Beispielkameras und Statuswerte | Simuliert | Separat zu haltende Testdaten. |

Demo- oder Heimtest-Ergebnisse bestätigen keine tatsächliche TV-, GPIO- oder Kamerafunktion. Details stehen in [Entwicklung](ENTWICKLUNG.md) und [Geräteprüfung](ABNAHME.md).

## Persistente Daten

| Datei/Ort | Zweck |
| --- | --- |
| `.env` | Anfängliches Dashboard-Passwort, lokaler Dienstschlüssel, Bindung, Port und Image-/App-Version. |
| `/data/config.json` | Ausgewählte Kamera, privater Stream, GPIO-Pin, Qualität und Abschaltzeit. |
| `/data/protect.json` | Gespeicherter lokaler NVR-Zugang und bestätigter Zertifikat-Fingerabdruck. |
| `/data/manual-cameras.json` | Eigene Kameraeinträge mit privaten Stream-Adressen. |
| `/data/dashboard-auth.json` | Gesalzener Passwortprüfwert nach einer Passwortänderung. Danach gilt der anfängliche `.env`-Zugang nicht mehr. |
| `/data/tv-access.json`, `/data/tv-receiver.json` | Getrennte TV- und Empfangsberechtigung. |
| `/data/telemetry.json` | Letzte empfangene Ereigniszeitpunkte und Kamerazuordnung. |
| `~/.config/oma-tv/` | Einstellungen und Dienstumgebung des Installationsbenutzers. |
| `.runtime/releases/`, `.runtime/current` | Versionierte Pi-Dateien und Verweis auf die aktive Laufzeit. |
| `.install.json`, `.maintenance/`, `backups/` | Installationszuordnung, Wartungsauftrag und private Sicherungen. |

Private Dateien werden mit eingeschränkten Dateirechten geschrieben und gehören nicht in GitHub. Normale Updates sichern die JSON-Daten einschließlich Passwortprüfwert und TV-Kopplung. Eine Wiederherstellung verwendet den jeweils gesicherten Zustand und kann damit auch ein früheres Passwort zurückbringen. Rückkehr zu einer alten App-Version ohne Passwortverwaltung ist gesondert in [SECURITY.md](../SECURITY.md) beschrieben.

## Versionswechsel

GitHub-Tags erzeugen geprüfte Docker-Images für ARM64, ARMv7 und AMD64. Der Wartungsdienst akzeptiert veröffentlichte stabile Releases der festen Projektquelle. Er führt einen unabhängigen Auftrag aus, sichert die aktuelle Installation, wechselt Container und Pi-Laufzeit und prüft den Start. Bei einem Fehler versucht er die Rückkehr zum gesicherten Stand.

Ein Browser-Update verändert nicht zwingend den ausgecheckten Git-Quellstand. Die installierte App-Version und das laufende Image sind deshalb aussagekräftiger als `git describe`. [Bedienung des Updatewegs](BROWSER-UPDATES.md) · [Sicherungen und Speicher](WARTUNG.md).
