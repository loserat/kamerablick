# Öffentlicher Quellstand und ausgelieferte Dateien

Kamerablick veröffentlicht den nachvollziehbaren Projektquellstand. Für den Betrieb auf dem Pi wird daraus ein begrenztes Docker-Image gebaut. Eine Testdatei im Repository ist deshalb nicht automatisch eine Datei im laufenden Produkt.

## Was öffentlich bleibt

| Inhalt | Zweck |
| --- | --- |
| `app/`, `pi/`, `requirements.txt` | Anwendung und erforderliche Pi-Werkzeuge. |
| Docker-/Compose-Dateien und Workflows | Reproduzierbarer Bau, Installation und Veröffentlichung. |
| `tests/` | Automatisierte Prüfprogramme und isolierte Labore mit Testdaten. Sie prüfen unter anderem Anmeldung, Updates, Rückkehr und Datenerhalt. |
| `docs/`, README und Projekttexte | Bedienung, Einrichtung, Grenzen und bestätigter Prüfstand. |
| `tools/` | Lokale und in GitHub ausgeführte Qualitätskontrollen. |
| `.env.example` | Eindeutige Platzhalter für den eigenen lokalen Zugang, keine echten Zugangswerte. |

Die Testquellen bleiben bewusst öffentlich: Sie machen die Prüfaussagen nachvollziehbar und helfen, Fehler bei späteren Updates zu erkennen. Private Testdaten und erzeugte Laborberichte gehören nicht dazu. Die anonymisierte Zusammenfassung unter `docs/verification/` ist ausdrücklich zur Veröffentlichung bestimmt und enthält keine Rohkonfiguration.

## Was lokal bleiben muss

`.env`, Kamera- und Protect-Konfiguration, Passwortprüfwerte, TV-Zugänge, Schlüsseldateien, Datenbanken, Browserprofile, Sicherungen, Protokolle und erzeugte Testberichte. `.gitignore` schließt diese typischen Pfade und Dateinamen aus. Persönliche Arbeitsarchive und Testnachweise werden außerhalb des Repositories aufbewahrt.

`tools/check_repository.py` kontrolliert den erfassten Dateibestand zusätzlich. Es weist gesperrte Dateien auch dann zurück, wenn sie mit `git add -f` hinzugefügt wurden, und erkennt eindeutige private Schlüssel- und GitHub-Token-Signaturen, ohne Werte auszugeben. Die Prüfung läuft für Änderungen an `main`, Pull Requests und neue Release-Tags. Sie ergänzt die Kontrolle auf Geheimnisse; sie ersetzt keine vollständige Inhaltsprüfung beliebiger Dateien.

## Was an Docker übergeben wird

Die `.dockerignore` schließt zunächst alles aus und gibt nur die benötigten Dateien frei: Dockerfile, Abhängigkeiten, Python-Quellen aus `app/` und `pi/` sowie die verwendeten statischen App-Dateien. Neue Verzeichnisse werden dadurch nicht versehentlich zu Bauinputs. Bei einer neuen benötigten Dateiendung muss die Freigabe gezielt ergänzt werden.

Tests, Dokumentation, Git-Historie, lokale Werkzeuge, Sicherungen und private Konfigurationsdateien werden nicht an den produktiven Docker-Bau übergeben. Das Dockerfile kopiert App-Dateien nach `/app` und Pi-Python-Dateien nach `/opt/kamerablick/pi`. Echte Einstellungen entstehen erst im lokalen Datenvolume beziehungsweise auf dem Pi.

Die Entwicklungs-Testprogramme bauen bei Bedarf eigene, getrennte Laborcontainer. Diese Testimages sind nicht die veröffentlichten App-Images und werden von den Laborprogrammen wieder entfernt.

## Repositoryprüfung vom 06.11.2026

- Der geprüfte Ausgangsstand umfasste 83 Dateien mit zusammen rund 0,7 MB; davon waren 19 Testquellen mit rund 174 KB. Die Git-Historie ist in dieser Inhaltsgröße nicht enthalten.
- Der aktuelle Bestand und die gesamte lokal vorhandene Historie mit allen Branch-/Tag-Referenzen wurden mit Gitleaks 8.30.1 geprüft: keine Funde. Zusätzlich wurden 311 historische Dateiobjekte auf bekannte private Werte und Schlüsselsignaturen kontrolliert: keine Funde.
- Sämtliche 15 damaligen GitHub-Releases hatten keine zusätzlichen Dateianhänge. Automatisch von GitHub bereitgestellte Quellarchive entsprechen dem jeweiligen öffentlichen Tag.
- In älteren Git-Ständen liegen fünf kleine Laborberichte mit Testresultaten. Die Kontrolle fand darin keine privaten Netzwerkadressen, Benutzerpfade oder erkannten Geheimnisse. Die Berichte sind aus dem aktuellen Stand entfernt; bestehende Tags und die Historie wurden nicht umgeschrieben.
- Das öffentliche Image v0.1.14 wurde isoliert geprüft: keine Projekt-Tests, keine Dokumentation, keine `.git`, keine `.env` und keine Sicherungen im App-Paket.
- Die strengere Docker-Auswahl wurde in einer isolierten Kopie mit zehn künstlichen privaten Dateien geprüft. Alle wurden ausgeschlossen; benötigte Quelldateien blieben bytegleich erhalten. Ein danach gebautes Produktimage bestand Bereitschaftstest, Anmeldung, Status- und Kameraabfrage.
- Der ungenutzte alte Helfer `pi/restore.py` wurde aus dem aktuellen Stand entfernt. Der dokumentierte Wiederherstellungsweg über `pi/update.sh --recover` verwendet ihn nicht und bleibt erhalten.

Die Ergebnisse sind eine Prüfung des genannten Stands, keine Garantie gegen jede denkbare sensible Information. Geschwärzte Scanberichte und Paketprüfnachweise werden privat aufbewahrt. Später hinzugefügte Dateien müssen erneut geprüft werden.

## Vor dem Push prüfen

```sh
python3 tools/check_repository.py
python3 tools/check_docs.py
git diff --check
```

Für einen ergänzenden Geheimnisscan Gitleaks aus der offiziellen Quelle verwenden und die Ausgabe schwärzen:

```sh
gitleaks git . --log-opts=--all --redact=100
gitleaks dir . --redact=100
```

Keine Scanberichte mit echten Trefferwerten veröffentlichen. Werden tatsächlich Zugangswerte gefunden, diese an ihrer Quelle erneuern und die weitere Bereinigung gezielt planen. Das bloße Löschen einer Datei aus `main` entfernt sie nicht aus älteren Commits oder Tags.

Diese Quellstandsbereinigung verändert kein bereits veröffentlichtes Image und startet kein Pi-Update. v0.1.14 bleibt für den eigenen Dashboard-Test verfügbar. Änderungen am Docker-Bau gelten für künftige Images.
