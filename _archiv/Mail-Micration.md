Bitte beginne jetzt mit dem Mail-Modul für Kira und nimm dafür zuerst die bestehende App im Ordner

C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv

vollständig als technische Basis in den Blick.

Wichtig:
Nicht sofort irgendetwas neu bauen.
Nicht zuerst an allgemeiner UI oder an anderen Modulen weitermachen.
Nicht wieder nur am Bereich Einstellungen hängen bleiben.

Dein erster Schritt ist ab jetzt:
die bestehende Mail-Archiv-App technisch analysieren, ihren aktuellen Funktionsumfang erfassen und daraus die saubere Integration in Kira beginnen.

Das Ziel ist klar:
Der bestehende Mail Archivierer soll nicht ersetzt, sondern als funktionierende Mail-Basis in Kira übernommen werden.

Fachliche Zielvorgabe:

1. Kira soll künftig primär über echten Mail-Abruf arbeiten.
   Das ist der Hauptweg.

2. Der bestehende Mail Archivierer bleibt zusätzlich erhalten, aber als Fallback.
   Also:
   Wenn der normale Abruf ausfällt oder eine Verbindung scheitert, soll Kira auf den bereits funktionierenden Archiv-/Abrufpfad des Mail Archivierers zurückgreifen können.

3. Beim ersten Einbau muss Kira erkennen, welche Mails bereits durch den Mail Archivierer vorhanden, archiviert oder schon zugeordnet sind.
   Es darf nach der Integration nicht passieren, dass vorhandene Mails doppelt oder dreifach in Kira auftauchen.

4. Die im Mail Archivierer bereits vorhandenen Konten sollen vollständig übernommen werden.
   Nicht nur optisch.
   Sondern technisch.
   Wenn dort funktionierende Azure-/OAuth-/Token-/Kontologik vorhanden ist, soll diese nach Möglichkeit direkt in Kira eingebunden oder übernommen werden, damit die Konten nicht neu angelegt werden müssen.

5. Zusätzlich muss Kira danach trotzdem offen bleiben für neue Konten.
   Also nicht nur bestehende Microsoft-/Azure-Konten übernehmen, sondern die Architektur so anlegen, dass später weitere Konten ergänzt werden können, z. B. über:
   - Microsoft / OAuth
   - Google
   - GMX
   - IMAP / SMTP
   - andere gängige Mailanbieter

6. Das Mail-Modul in Kira soll wie ein echter Postfacharbeitsplatz funktionieren.
   Also nicht bloß Archivansicht, sondern mit echter Maillogik:
   - Posteingang
   - Gesendet
   - Entwürfe
   - Archiv
   - Threadansicht
   - Lesen
   - Antworten
   - Weiterleiten
   - Entwürfe
   - Versand
   - Anhänge
   - Kira-Kontext
   - Freigabe-Logik, wo nötig

7. Die Technik des Mail Archivierers darf nicht sinnlos verworfen werden, wenn sie bereits zuverlässig funktioniert.
   Übernehmen ist wichtiger als neu erfinden.

Wichtig:
Die bestehende Kira-Architektur bleibt erhalten.
Auch der aktuelle UX-Rebuild bleibt grundsätzlich bestehen.
Aber beim Thema Mail hat jetzt die fachliche Integrationslogik Vorrang.

Das bedeutet ausdrücklich:
Nicht nur “Mail & Konten” in den Einstellungen hübsch machen.
Sondern die echte technische Mail-Basis analysieren und in Kira integrieren.

Bitte arbeite jetzt in dieser Reihenfolge:

1. Die App im Ordner
   C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv
   vollständig prüfen

2. Dokumentieren:
   - welche Funktionen dort bereits real funktionieren
   - wie Abruf, Archivierung, Konten, Tokens, Azure/OAuth, IMAP/SMTP, Versand, Ordnerlogik und UI aktuell gelöst sind
   - welche Teile direkt in Kira übernommen werden können
   - welche Teile angepasst werden müssen
   - welche Teile nur als Fallback genutzt werden sollten

3. Danach entscheiden und dokumentieren:
   - wie der Primärpfad in Kira aussehen soll
   - wie der Fallback auf den Mail Archivierer greift
   - wie Dubletten beim Erstimport und bei laufendem Betrieb verhindert werden
   - wie vorhandene archivierte Mails sauber erkannt und übernommen werden
   - wie bestehende Konten übernommen werden können, ohne sie neu anzulegen

4. Dann mit der Integration beginnen.
   Fokus zuerst auf Funktion, Datenfluss und saubere Übernahme.
   Die UI soll sich an Kira anpassen, aber nicht zuerst als Deko gebaut werden.

5. Bestehende neue Kira-UI-Standards beibehalten, aber nicht zulassen, dass die Mailtechnik darunter wieder halb vergessen wird.

Wichtige zusätzliche Vorgaben:

- Wenn die bestehende App bereits funktionierende Azure-/OAuth-Registrierungen und Token-Logik hat, dann diese nach Möglichkeit direkt weiterverwenden oder migrieren.
- Wenn eine direkte Übernahme technisch nicht 1:1 möglich ist, dann bitte nicht stillschweigend neu bauen, sondern sauber dokumentieren, was übernommen wird und was migriert werden muss.
- Der erste Sync bzw. erste Abruf in Kira muss bestandsbewusst sein.
  Keine blinde Neuimport-Logik. NACHFOLGENDEN PROMPT Erstimport, Bestandsabgleich und Dublettenvermeidung.
- Bereits vorhandene Archivdaten, IDs, Threadbezüge, Hashes, UID-Stände oder andere eindeutige Marker sollen genutzt werden, um Dubletten zu verhindern.
- Mail-Archiv bleibt nicht Hauptweg, sondern Fallback.
- Primär ist echter Mail-Abruf in Kira.
- Konten aus dem Mail Archivierer sollen vollständig übernommen werden, soweit technisch sauber möglich.
- Architektur offen halten für neue Konten und weitere Provider.

Was ich ausdrücklich nicht will:

- keine reine UI-Arbeit ohne funktionale Mailintegration
- kein zweites paralleles Mailsystem ohne Verbindung
- keine manuelle Neu-Anlage aller Konten, wenn die vorhandenen Daten nutzbar sind
- keine Dublettenlawine nach dem ersten Import
- keine halbfertige Mailanzeige ohne echten Abrufpfad
- keine Rückkehr zu nur archivbasierter Hauptlogik, wenn Primärabruf möglich ist

Was ich stattdessen will:

- bestehende Mail-App technisch verstehen
- funktionierende Teile intelligent übernehmen
- primären Abrufpfad in Kira aufbauen
- Archiv als Fallback anbinden
- vorhandene Konten übernehmen
- Dubletten sauber verhindern
- echtes Mail-Modul in Kira beginnen

Bitte am Ende deines ersten Arbeitsblocks konkret dokumentieren:

- welche Dateien / Komponenten des Mail Archivierers du geprüft hast
- welche technischen Bausteine bereits brauchbar sind
- welche Konten-/Auth-Teile übernommen werden können
- wie du Primärabruf und Fallback aufteilen willst
- wie du Dublettenvermeidung lösen willst
- womit du als erstes in der Integration begonnen hast

Danach bitte direkt weitermachen und nicht bei einer bloßen Analyse stehen bleiben.

Bitte arbeite jetzt gezielt am Bereich Erstimport, Bestandsabgleich und Dublettenvermeidung für die Integration des Mail Archivierers in Kira.

Wichtig:
Dieser Schritt ist fachlich kritisch.
Wenn er unsauber gelöst wird, laufen wir in doppelte Mails, doppelte Threads, doppelte Zuordnungen und kaputte Historien.
Darum jetzt nicht an schöner Oberfläche hängen bleiben, sondern die Datenlogik sauber lösen.

Ausgangslage:
Kira soll künftig primär über echten Mail-Abruf arbeiten.
Der bestehende Mail Archivierer bleibt zusätzlich als Fallback erhalten.

Gleichzeitig gibt es im bestehenden Mail Archivierer bereits archivierte Mails, vorhandene Konten, bestehende Ordnerstrukturen, UID-Stände, Archivdaten und vermutlich weitere eindeutige Marker.
Diese Bestände müssen beim Einbau in Kira sauber erkannt und berücksichtigt werden.

Ziel:
Beim ersten Einbau und beim späteren laufenden Betrieb darf es nicht passieren, dass bereits vorhandene oder bereits zugeordnete Mails doppelt oder dreifach in Kira auftauchen.

Bitte arbeite jetzt in dieser Reihenfolge:

1. Bestehende Archivstruktur des Mail Archivierers vollständig prüfen
   Prüfe insbesondere:
   - wie archivierte Mails gespeichert sind
   - welche IDs oder eindeutigen Marker vorhanden sind
   - ob Message-ID, Thread-/Conversation-Bezug, IMAP-UID, Ordner, Zeitstempel, Hashes oder andere stabile Erkennungsmerkmale bereits gespeichert werden
   - wie der aktuelle UID-Stand je Ordner/Konto gespeichert wird
   - ob es bereits Mechanismen gegen Mehrfacharchivierung gibt

2. Bestehende Mailstruktur in Kira prüfen
   - wie Mails aktuell gespeichert werden
   - welche Felder / IDs / Status / Zuordnungen bereits in Kira existieren
   - ob dort bereits Threadlogik, Kontextlogik, Kategorien, Status oder Zuordnungen auf Geschäfts-/Aufgaben-/Kira-Kontexte existieren
   - welche Felder als Vergleichsbasis geeignet sind

3. Danach eine saubere Abgleichsstrategie definieren
   Ziel:
   Kira muss beim ersten Start nach Integration erkennen:
   - was schon im Archiv vorhanden ist
   - was bereits in Kira vorhanden ist
   - was nur im Archiv liegt
   - was nur im Primärabruf neu reinkommt
   - was identisch ist
   - was ein potenzielles Duplikat ist
   - was derselbe Thread, aber neuer Inhalt ist
   - was nur eine alte Mail in neuem Thread-Kontext ist

4. Verbindliche Dublettenlogik entwickeln
   Diese Logik darf nicht stumpf nur auf Betreff oder Datum gehen.

   Bitte eine Prioritätslogik für eindeutige und unscharfe Matches definieren, z. B. nach diesem Prinzip:

   Stufe A – harte Identität
   - Internet Message-ID
   - Provider-spezifische eindeutige Mail-ID
   - IMAP UID in Verbindung mit Konto + Ordner + UIDVALIDITY
   - stabile Archiv-ID, falls vorhanden

   Stufe B – sehr starke Ähnlichkeit
   - gleicher Absender
   - gleicher Empfänger oder Empfängergruppe
   - gleicher Zeitstempel oder sehr kleines Zeitfenster
   - gleicher Betreff
   - gleicher Body-Hash oder normalisierter Content-Hash
   - gleiche Anhangsstruktur / gleiche Attachment-Hashes

   Stufe C – Thread-/Kontextabgleich
   - gleicher Thread / Conversation-Verlauf
   - gleiche References / In-Reply-To
   - gleiche Konversationsgruppe, aber neue Nachricht
   - alte Nachricht hängt erneut in neuem Kontext an

5. Erstimport-Strategie sauber festlegen
   Der erste Einbau in Kira darf kein blinder Vollimport sein.

   Bitte definieren und möglichst umsetzen:
   - welche Archivbestände beim ersten Start eingelesen werden
   - wie bestehende Mails markiert werden
   - wie Kira erkennt, dass diese bereits historisch vorhanden sind
   - wie verhindert wird, dass derselbe Datensatz später beim echten Abruf nochmal als neu erscheint
   - wie Bestandsmails und künftige Live-Mails zusammengeführt werden, ohne die Historie zu zerlegen

6. Laufende Synchronisation sauber trennen
   Nach dem Erstimport muss es zwei logisch saubere Wege geben:

   Primärpfad:
   echter Mail-Abruf in Kira

   Fallback:
   Zugriff auf bestehende Archiv-/Abruflogik aus dem Mail Archivierer

   Wichtig:
   Auch wenn beide Wege dieselbe Mail sehen können, darf daraus kein doppelter Datensatz entstehen.

   Bitte dafür eine eindeutige Merge- oder Upsert-Logik bauen oder dokumentiert festlegen.

7. Status- und Herkunftslogik einbauen
   Für jede Mail bzw. jeden Datensatz soll nachvollziehbar sein:
   - aus welchem Konto sie kommt
   - über welchen Pfad sie zuerst in Kira bekannt wurde
     z. B. live_abruf / archiv_import / fallback_sync
   - ob sie bereits historisch vorhanden war
   - ob sie nur gespiegelt wurde
   - ob ein potenzieller Konflikt oder Dublettenverdacht bestand
   - welche Version als führend gilt

8. Konfliktfälle ausdrücklich mitdenken
   Bitte nicht nur Idealfälle behandeln.

   Beispiele, die sauber behandelt werden müssen:
   - dieselbe Mail liegt schon archiviert vor und kommt beim ersten Primärabruf erneut
   - dieselbe Mail liegt in Inbox und Sent oder in mehreren Ordnern
   - weitergeleitete oder neu angehängte alte Mail erscheint in neuem Thread
   - archivierte Mail hat unvollständige Metadaten
   - live abgerufene Mail enthält mehr Informationen als Archivversion
   - Archivversion hat Anhänge, Live-Version aber noch nicht oder umgekehrt
   - alte Mail wurde bereits manuell in Kira kategorisiert oder mit Geschäftsfall/Aufgabe verknüpft

   In solchen Fällen bitte definieren:
   - was zusammengeführt wird
   - was führend bleibt
   - was nur ergänzt wird
   - wann ein Konfliktflag gesetzt wird
   - wann manuelle Prüfung nötig ist

9. Keine Datenzerstörung
   Bestehende Historie, Kategorien, Kira-Kontexte, Status oder Verknüpfungen dürfen durch den Import nicht überschrieben oder kaputtmigriert werden.

   Wenn ein bestehender Kira-Datensatz schon bearbeitet wurde, soll ein später erkannter Archiv- oder Live-Treffer diesen nicht blind ersetzen.

10. Logging
   Dieser ganze Bereich muss sauber geloggt werden:
   - Import gestartet
   - Quelle erkannt
   - Match gefunden
   - Dublette erkannt
   - Merge ausgeführt
   - Konflikt erkannt
   - manuelle Prüfung markiert
   - Live-Mail auf Archivbestand gemappt
   - Archivdatensatz auf Kira-Datensatz gemappt

   Wichtig:
   Diese Import-/Merge-/Dublettenlogik muss später nachvollziehbar sein.

Verbindliche fachliche Anforderungen:

- Keine Dublettenlawine
- Keine Betreff-Bastellogik
- Keine blinde Neu-Anlage vorhandener Mails
- Keine Zerstörung vorhandener Verknüpfungen
- Primärabruf bleibt Hauptweg
- Archiv bleibt Fallback
- Erstimport ist bestandsbewusst
- laufender Betrieb ist mergefähig
- Konflikte werden sichtbar statt verschwiegen

Wenn du technisch einen besseren Weg findest als hier beschrieben, darfst du ihn verwenden.
Aber das Ziel bleibt bindend:
Kira muss bestehende Archivbestände und neue Live-Mails sauber zusammenführen, ohne doppelte Datensätze und ohne Verlust von Historie.

Bitte am Ende konkret dokumentieren:

- welche eindeutigen Marker du im Mail Archivierer gefunden hast
- welche Felder du für den Abgleich verwendest
- wie deine Match-Priorität aussieht
- wie der Erstimport funktioniert
- wie laufende Dubletten verhindert werden
- wie Konflikte behandelt werden
- welche Tabellen / Dateien / Strukturen du dafür geändert oder ergänzt hast
- was bereits umgesetzt ist
- was noch offen ist