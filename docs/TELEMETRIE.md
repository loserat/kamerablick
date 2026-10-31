# Kamerastatus und empfangene Ereignisse

Implementiert und lokal getestet, noch nicht am UNVR Instant verifiziert. Es wird ausschließlich die eingerichtete Protect-Kamera überwacht. Manuelle Stream-Adressen und Beispielkameras liefern keine vorgetäuschten Ereigniswerte.

## Anzeigen

Im Dashboard unter „Kamera & Ereignisse“:

- Kameraverbindung: Online, Verbindet, Offline oder Status nicht aktuell.
- Ereignisverbindung: Verbunden, Unterbrochen, Nicht unterstützt oder ein Hinweis auf Schlüssel/Zertifikat.
- Letzte empfangene Bewegung, Person und Fahrzeug mit relativem und absolutem Zeitpunkt.
- Aktueller Bewegungszustand nur, solange dafür ausreichend aktuelle Informationen vorliegen.

Die TV-Ansicht zeigt bei einer Protect-Kamera eine kurze Zeile zur letzten Bewegung. Die technische Einrichtung bleibt im Dashboard. Vorhandene historische Zeitpunkte bleiben bei einer Unterbrechung sichtbar; die Ereignisverbindung wird dabei ausdrücklich als nicht aktuell dargestellt.

## Woher kommen die Werte?

Der lokale Protect-Integration-API-Endpunkt `cameras/{id}` wird alle 15 Sekunden gelesen. Der Ereigniskanal `subscribe/events` bleibt über eine TLS-geschützte WebSocket-Verbindung offen. Beide verwenden denselben zuvor eingerichteten Protect-API-Schlüssel. Personen- und Fahrzeugereignisse werden nur aus ausdrücklich gemeldeten Smart-Detection-Typen übernommen.

Die HTTPS-/WebSocket-Verbindung prüft das Konsolenzertifikat, bevor der Schlüssel gesendet wird. Ein bestätigter eigener Zertifikat-Fingerabdruck gilt für beide Zugänge. Weiterleitungen des Ereigniszugangs werden nicht verfolgt.

Die Interpretation des öffentlichen Ereignisformats orientiert sich an der [Protect-API](https://developer.ui.com/protect) und dem [Ereigniszugang der von Home Assistant verwendeten uiprotect-Bibliothek](https://uiprotect.readthedocs.io/en/latest/usage/#subscribing-to-events). Neue Ereignistypen außerhalb von Bewegung und den unterstützten Smart-Detection-Typen werden nicht als bekannte Erkennung ausgegeben.

## Ausfälle und Aktualität

- Ein fehlgeschlagener Statusabruf macht den Kamerastatus sofort nicht aktuell.
- Spätestens nach 45 Sekunden ohne gültige Aktualisierung werden Verbindungswerte als veraltet betrachtet.
- Der Ereigniskanal prüft die Gegenstelle alle 15 Sekunden mit Ping/Pong. Ohne Antwort innerhalb von 10 Sekunden wird neu verbunden.
- Fehler und reguläre Verbindungsenden lösen einen erneuten Versuch mit begrenztem Abstand aus. Änderungen an Kamera oder Zugang unterbrechen die Wartezeit.
- Nach Neustart oder Wiederverbindung ist ein aktueller Bewegungszustand zunächst unbekannt; gespeicherte „verbunden“- oder „keine Bewegung“-Zustände werden nicht übernommen.
- Ohne neue Bewegungsinformation wird nach spätestens 120 Sekunden kein aktueller Bewegungszustand mehr behauptet. Der gespeicherte letzte Ereigniszeitpunkt bleibt davon unberührt.

Ein Online-Kamerastatus beweist keine flüssige Videowiedergabe am TV. Umgekehrt kann bei einem manuellen Videostream das Bild funktionieren, ohne dass Kamerastatus oder Bewegungserfassung verfügbar sind.

## Empfangene Zeitpunkte statt vollständiger Historie

Die Anzeige bedeutet **„zuletzt von Kamerablick empfangen“**. Es erfolgt keine rückwirkende Abfrage der kompletten Protect-Aufzeichnungshistorie. Bei Neustarts und Netzwerkausfällen können Ereignisse fehlen. Deshalb steht eine Unterbrechung nicht für „keine Bewegung“.

`occurred_at` stammt aus dem gemeldeten Ereignisbeginn, `received_at` ist die Empfangszeit auf Kamerablick. Beide werden in UTC gespeichert; die Oberfläche zeigt die Uhrzeit für Europa/Berlin. Offensichtlich ungültige Zeitstempel werden verworfen. Falsche Uhren auf Pi oder Konsole müssen am Gerät korrigiert werden.

## Lokale Speicherung

Die letzten drei Zeitpunkte werden in `telemetry.json` im vorhandenen Datenvolume mit privaten Dateirechten gespeichert. Kamera und Konsole bilden eine getrennte, gehashte Zuordnung; ein Kamerwechsel vermischt die Werte nicht. Maximal 32 Kamerazuordnungen bleiben gespeichert. Es werden keine Clips, Bilder, Gesichter, Kennzeichen oder API-Schlüssel in dieser Datei abgelegt.

Die vorhandene Updatesicherung erfasst diese JSON-Datei automatisch mit. Eine beschädigte Ereignisdatei wird gemeldet und zur Wiederherstellung erhalten, nicht stillschweigend mit einer leeren Datei überschrieben.

## Tests und Grenzen

Die Tests verwenden eine lokale HTTPS-/WebSocket-Testkonsole mit eigenem Zertifikat. Geprüft sind tatsächliche Handshakes, empfangene Ereignisse, stille Verbindungen, fehlende Pong-Antworten, reguläres Verbindungsende, Wiederverbindung, Zertifikatwechsel, Schlüsselablehnung und Weiterleitungsschutz. Weitere Tests prüfen Speicherung, Neustart, Kamerwechsel, doppelte/vertauschte Ereignisse und die API-Ausgabe an Dashboard und eingeschränkte TV-Ansicht.

Am echten Instant sind noch zu prüfen: verfügbare API-Version, Kameramodell, Smart-Detection-Fähigkeiten, tatsächliches Ereignisformat, Konsolen-/Pi-Uhren und Verhalten bei Netzwerk- und Protect-Neustarts.
