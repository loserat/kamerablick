# Goal-Abnahme Kamerablick

Stand: 04.11.2026. Das Gesamtziel ist offen. Ein Pi 4B wurde bereits installiert; sein aktueller Dienststand ist nicht verifiziert. Der Pi ist laut Nutzer derzeit ausgeschaltet. Protect-Version, TV-Modell, echte Tasterverdrahtung und privater Fernzugriff müssen am Ziel geprüft werden. Private Adressen und Zugangsdaten werden in diesem öffentlichen Dokument nicht gespeichert.

## Nachweise zu den neun Abnahmekriterien

| Kriterium | Umgesetzt und Software-Nachweis | Für die Abnahme noch erforderlich |
| --- | --- | --- |
| 1. GitHub, Docker, automatischer Start | Öffentliche ARM64-/ARMv7-/AMD64-Images, versionierte Pi-Laufzeit, Docker-Neustartregel und Desktop-Startbrücke. Installer-, systemd- und Containerprüfungen. | Vorhandene Pi-Installation prüfen; regulären Neustart mit Desktop-Autologin, WLAN und angeschlossenem TV abnehmen. |
| 2. Schlichte Oberfläche über Pi-IP | Neutrale Gestaltung, kurze Beschriftungen, aufklappbare Hilfen und passwortgeschütztes Dashboard. Neue Pi-Installationen binden an das Heimnetz; bestehende Bindung bleibt erhalten. Browserprüfung am Desktop und bei 390 Pixeln Breite. | Dashboard über die tatsächliche Pi-Adresse von einem zweiten Gerät öffnen. |
| 3. Protect und manuelle Kamera | Lokaler Benutzer oder API-Schlüssel, Zertifikatprüfung, Kameraliste, Standbild, Bildqualität und Stream-Freigabe. TLS-Testkonsole, API- und Browserprüfungen mit Testdaten. | Mit dem echten NVR verbinden; Standbild, Berechtigungen und flüssiges Livebild am TV prüfen. |
| 4. TV-Ansicht und Fernbedienung | Große Schaltflächen, sichtbare Auswahl, Pfeile/OK/Zurück und Ausschaltbestätigung. Browser-Tastaturprüfung sowie Tests für Navigation und CEC-Zustellung. | Echte IR-/CEC-Fernbedienung, Tasten halten/loslassen und Rückkehr aus dem Player am konkreten Fernseher prüfen. |
| 5. GPIO und Abschaltzeit | Tastersteuerung und einstellbare Abschaltung; simulierte Hardwaretests. | Verdrahteten Taster mehrmals betätigen; Einschalten, zweiter Druck Standby und automatische Abschaltung beobachten. |
| 6. Ausfälle und veraltete Werte | Wiedergabefortschritt, begrenzte Wiederverbindungsversuche und Aktualitätskennzeichnung. Streamlabor mit echtem RTSP/RTSPS und erzeugtem Testvideo; Quellprüfsummen von Agent, CEC und Player stimmen mit dem vorhandenen Nachweis überein. | Tatsächlichen Kamera-/Netzausfall, Rückkehr und sichtbar aktuelles Bild am TV prüfen. |
| 7. Browser-Updates und Datenerhalt | Bestätigter Updateauftrag, Sicherung, gemeinsame Container-/Pi-Laufzeit und Rückkehr. Isoliertes Docker-Labor prüft Browserbedienung, fehlerhaftes Image, Unterbrechung und datenerhaltende Neuinstallation. | Mindestens ein veröffentlichtes Update auf dem echten Pi aus der Oberfläche durchführen und anschließend Kamera, Taster und TV erneut prüfen. |
| 8. Privater Fernzugriff | Passwortschutz, getrennte TV-Berechtigung und kein Docker-Socket im Dashboard. Konkreter VPN-Einrichtungs- und Prüfweg in [FERNZUGRIFF.md](FERNZUGRIFF.md). | VPN am Pi und Wartungsgerät einrichten und Dashboard/SSH aus einem fremden Netz nach Pi-Neustart testen. |
| 9. Repository und Dokumentation | Versionierte Installationswege, aktuelle Abbildungen, veröffentlichte Images und reproduzierbare Prüfprogramme. Private Konfiguration und erzeugte Berichte liegen außerhalb des Repositories. | Dokumentation nach dem tatsächlichen Gerätestand gegenprüfen; private Abnahmeergebnisse aufbewahren. |

Die Prüfprogramme liegen unter [tests/](../tests/). GitHub führt [Projektprüfungen](https://github.com/loserat/kamerablick/actions/workflows/checks.yml) und vor jeder Image-Veröffentlichung erneut Tests aus. Container-/Browserprüfungen bestätigen keine GPIO-, HDMI-, WLAN- oder Gerätefunktion. Systemd und GitHub-Transport im Update-Labor sind Testgegenstellen; die Containerwechsel und Datenwiederherstellung erfolgen tatsächlich.

## Geräteprüfung in dieser Reihenfolge

1. Pi einschalten, HDMI zum TV verbinden und als bisheriger Installationsbenutzer anmelden. Im Projektordner `python3 pi/doctor.py` ausführen. Dienstfehler zuerst klären. Die Diagnose liest nur; sie startet weder Wiedergabe noch Update.
2. Dashboard von einem zweiten Gerät über `http://PI-IP:8088` öffnen. Anmeldung und unter Wartung angezeigte Version notieren. Bei abweichendem Port diesen verwenden.
3. Protect verbinden, erreichbare Kamera wählen, Standbild prüfen und übernehmen. Am TV das Livebild öffnen und durch eine sichtbare Bewegung kontrollieren, dass es aktuell ist.
4. Verdrahtung bei ausgeschaltetem Pi prüfen. Danach fünf vollständige Tasterzyklen testen: erster Druck Kamera, zweiter Druck Standby. Keine Fremdspannung an GPIO anlegen.
5. Abschaltzeit auf eine Minute setzen und vom Start der Kamera bis zur Abschaltung messen. Danach den gewünschten Alltagswert wiederherstellen.
6. Mit TV-Fernbedienung oder zunächst Tastatur Pfeile, OK und Zurück prüfen. Hilfe schließen, Ausschalten abbrechen und aus dem Kameraplayer zur Übersicht zurückkehren. Erst nach echten CEC-Tasten als fernbedienbar markieren.
7. Für einen Ausfalltest vor Ort eine Kamera-/Netzverbindung kontrolliert unterbrechen. Veraltete Werte müssen erkennbar werden; nach Rückkehr muss die Wiedergabe selbstständig fortsetzen. Der Abschaltzeitpunkt darf dadurch nicht verlängert werden. Eine WLAN-Unterbrechung nicht über den einzigen Fernzugang auslösen.
8. Pi regulär neu starten, wenn kein Update läuft. WLAN, Dashboard, Pi-Dienst, Wartungsdienst und sichtbare TV-Ansicht ohne manuelle Desktop-Anmeldung prüfen. Auch den Start mit zunächst ausgeschaltetem TV prüfen.
9. Unter Wartung eine neuere veröffentlichte Version prüfen, Versionswechsel bestätigen und bis zum Abschluss warten. Version nach erneuter Anmeldung kontrollieren. Bestehendes Passwort, Kamera, Qualität, Abschaltzeit und TV-Zugang müssen erhalten bleiben. Taster und Livebild nochmals prüfen. Fehler-/Unterbrechungstests zunächst im isolierten Labor durchführen.
10. Fernzugriff nach [FERNZUGRIFF.md](FERNZUGRIFF.md) aus einem fremden Netz abnehmen. Abschließend die alltägliche Bedienung gemeinsam mit der Oma ausprobieren.

## Ergebnisse privat festhalten

Für jeden Schritt Datum, Pi-/OS-Version, App-Version, Ergebnis und einen konkreten Nachweis notieren. Sinnvolle Nachweise sind ein redigierter Diagnosebericht, beobachtete Tasterzyklen, gemessene Abschaltzeit, tatsächlich empfangene CEC-Tasten und der Versionswechsel im Dashboard. Passwörter, API-Schlüssel, VPN-Anmeldelinks und ungekürzte private Konfigurationen nicht veröffentlichen.

Das Goal bleibt aktiv, bis Installation, Kamera, Taster, TV-Bedienung und ein Browser-Update am echten Pi erfolgreich geprüft sind und der private Fernzugriff funktioniert. Unbestätigte Punkte bleiben offen.
