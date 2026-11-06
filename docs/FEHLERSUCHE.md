# Fehlersuche

Zuerst das konkrete Symptom eingrenzen. Einstellungen und Sicherungen erhalten; eine Neuinstallation ist nicht der erste Diagnoseschritt. Die folgenden Befehle werden als bisheriger Installationsbenutzer im Projektordner ausgeführt.

## Dashboard über die Pi-IP nicht erreichbar

```sh
hostname -I
docker compose ps
curl --max-time 5 http://127.0.0.1:8088/healthz
```

Die WLAN-/LAN-Adresse des Pi verwenden, nicht die interne Docker-Adresse. Ein erfolgreicher Ping bestätigt nur die Erreichbarkeit des Geräts, nicht den Webdienst. Bei lokal erfolgreichem Bereitschaftstest die gespeicherte Bindung prüfen:

```sh
grep -E '^(BIND|PORT)=' .env
```

Für den direkten Heimnetzzugriff ist `BIND=0.0.0.0` vorgesehen. Bestehende Installationen mit `127.0.0.1` behalten diese Einstellung bewusst. Die gesicherte Umstellung steht in [Installation](INSTALLATION.md). Bei abweichendem Port diesen in der URL verwenden. Gastnetzisolierung und eine vorhandene Firewall getrennt prüfen; keine pauschale Firewall-Abschaltung durchführen.

## Kein Updateknopf

Unter Wartung **Version prüfen** wählen. Sind „Installiert“ und „GitHub“ gleich, ist das System aktuell. **Jetzt aktualisieren** erscheint erst bei einer neueren veröffentlichten Version. Einzelne GitHub-Commits und Dokumentationsänderungen sind keine neuen App-Versionen.

Wird eine neuere Version angezeigt, aber der Knopf bleibt gesperrt, die Wartungsbereitschaft und einen eventuell laufenden Auftrag prüfen. Im Heimtest und in der Demo werden keine Pi-Updates installiert. [Updateablauf](BROWSER-UPDATES.md).

## Versionsprüfung oder Update fehlgeschlagen

Die angezeigte Fehlermeldung und **Letzter Updateversuch** lesen. Ein laufender Auftrag arbeitet trotz kurz unterbrochener Dashboard-Verbindung weiter. Den Pi eingeschaltet lassen und nicht gleichzeitig eine weitere Installation starten.

```sh
python3 .runtime/current/doctor.py --root "$PWD"
systemctl --user status oma-tv-maintenance.service
journalctl --user -u oma-tv-maintenance.service -n 50 --no-pager
```

Netzwerk/DNS zum GitHub-Download und die lokale Wartung getrennt betrachten. Für einen offenen Wiederherstellungszustand den [dokumentierten Rückweg](BROWSER-UPDATES.md) verwenden. `.maintenance/`, `.install.json` und `backups/` nicht löschen, um eine Fehlermeldung zu beseitigen.

## „Lokaler Wartungsschlüssel fehlt“

Bei Installationen aus den frühen Versionen war der `EnvironmentFile=`-Pfad in den erzeugten Dienstdateien falsch zitiert. Ein direkt gestarteter Prozess konnte deshalb funktionieren, während der reguläre Dienst seinen Schlüssel nicht erhielt. Ab v0.1.6 ist der Installer korrigiert. Den [Reparaturweg für ältere Dienstdateien](BROWSER-UPDATES.md#korrektur-des-dienststarts-bis-v015) verwenden und die Diagnose erneut ausführen. Keinen Dienstschlüssel in ein öffentliches Issue kopieren.

## Bild vorhanden, aber Fernbedienung ohne Wirkung

HDMI-Bild und CEC-Tasten sind getrennt. Am TV CEC und bei Philips zusätzlich **EasyLink-Fernbedienung** einschalten. Den Pi-Eingang auswählen, das TV-Einstellungsmenü schließen und im Dashboard unter **Wartung → Fernbedienung** Adapter, Empfang und letzte Taste vergleichen.

Am geprüften Philips 55PUS6581/12 war nach einem Gerätewechsel eine veraltete CEC-Quellenzuordnung vorhanden. Beide EasyLink-Optionen waren aktiv, aber erst ein vollständiger TV-Neustart stellte den Tastenempfang wieder her. Der alte Quellenname des vorherigen Players war allein kein Fehlernachweis. Ein ARC-Anschluss allein löst dieses Problem ebenfalls nicht.

Keinen zweiten `cec-client` parallel starten: Der Pi-Dienst hält den Adapter für Empfang und Schaltbefehle offen. Weitere Schritte und die Grenzen des Kompatibilitätstests stehen unter [Fernbedienung](FERNBEDIENUNG.md).

## Schlüsselbund-Abfrage oder Browser bleibt nach einem Update stehen

Der verwaltete TV-Browser verwendet ein eigenes Chromium-Profil mit `--password-store=basic`. Das vermeidet eine interaktive Schlüsselbund-Abfrage im TV-Betrieb. Ab v0.1.10 beendet der Starter seinen eigenen Browserprozess bei einem Dienststopp auch dann ausdrücklich, wenn Chromium in einen separaten Systemd-Bereich gewechselt ist.

Die aktuelle verwaltete Version und Diagnose prüfen. Keine normalen Browserprofile oder System-Schlüsselbünde löschen. Die Profile und Grenzen stehen in [Installation](INSTALLATION.md).

## Passwort abgewiesen

Nach einer Änderung im Dashboard gilt das **zuletzt gespeicherte** Passwort; der anfängliche `.env`-Wert wird dann nicht mehr zur Anmeldung verwendet. Nach mehreren Fehlversuchen eine Minute warten. Dashboard-, UniFi- und SSH-Zugänge sind unterschiedliche Zugangsdaten.

Ein fehlgeschlagenes Speichern verändert den bisherigen Dashboard-Zugang nicht. Eine wiederhergestellte alte Sicherung kann dagegen ihren damaligen Passwortstand zurückbringen. Für eine nötige Wiederherstellung den privaten Datenbestand zuerst sichern und die verwendete Version berücksichtigen. [Passwortverwaltung](BEDIENUNG.md#dashboard-passwort-ändern) · [Sicherungsdaten](WARTUNG.md).

## Kameras, Standbild oder Ereignisse fehlen

Unter **Kameras** den gespeicherten Zugang und die Kamera prüfen. Bei Protect lokale Benutzerrechte, API-Schlüssel, Zertifikat und Stream-Freigabe unterscheiden. Eine erfolgreiche Anmeldung oder ein Standbild beweist noch keine laufende mpv-Wiedergabe.

Die TV-Kameraliste verwendet zwischengespeicherte Metadaten; Änderungen können ungefähr eine Minute benötigen. Manuelle Streams liefern keine erfundenen Protect-Bewegungswerte. Ereignisse bedeuten „zuletzt von Kamerablick empfangen“, keine lückenlose NVR-Historie. [Heimtest](HEIMTEST.md) · [Telemetrie](TELEMETRIE.md).

## Einen Fehler melden

Version aus Wartung, Pi-Modell, Betriebssystem, TV-Modell, konkrete Schritte, Erwartung und tatsächliches Ergebnis angeben. Diagnoseausgaben vor dem Teilen kontrollieren. Passwörter, API-Schlüssel, Tokens, Stream-Adressen und private Bilder entfernen. [Issue erstellen](https://github.com/loserat/kamerablick/issues) · [Sicherheitsproblem melden](../SECURITY.md).
