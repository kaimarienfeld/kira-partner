## KIRA App — Offene Todos & Entwicklungs-Backlog
*Stand: 2026-03-30 | Letzte Aktualisierung: session-hh/ii*

---

### 🔴 BUGS (bekannt, offen)

- **Löschen einzeln + Multi**: Kira fragt nach dem Grund, aber nach Bestätigung passiert nichts — Eingabefenster schließt sich, kein Löschvorgang, Einträge bleiben. Betrifft Tasks.

---

### 🟡 GEPLANT / VORGEMERKT

**Postfach:**
- **Mails verschieben** (IMAP) testen mit echten Mails — POST /api/mail/verschieben implementiert, noch nicht live getestet
- **"Zu Kira hinzufügen"-Button** im Postfach: Ordner direkt aus dem Postfach zu sync_ordner (Kira-Kernordner) hinzufügen
- **Gesendete-Zählung** im Sidebar-Badge (zeigt aktuell nur Posteingang-Unread)
- **Direkte E-Mail-Antwort** aus dem Postfach heraus — geplant, noch nicht gebaut

**Mail-Konten:**
- **Google OAuth** verdrahten (Microsoft fertig, Google fehlt noch)
- **SMTP-Passwort-Auth im Volltest** (Volltest nutzt aktuell nur XOAUTH2)
- **Provider-Persistierung** nach OAuth-Login (Typ/Provider wird nicht in config gespeichert)
- **Einstellungen-UI**: bereinigung_frist_tage + geloeschte_bereinigung_aktiv ✅ (session-hh erledigt)

**Kira LLM:**
- **kira_verwendet Auto-Markierung** ✅ (session-ii erledigt): Kira markiert Mails die sie für Kontext/Auswertung nutzt automatisch mit lila Badge im Postfach
- **Wissen-Datenbank automatisch pflegen**: Kira soll Preise, Erkenntnisse, Muster aus Mails/Angeboten/Rechnungen automatisch erkennen und in wissen_regeln eintragen. Timestamps für alle Einträge (wann erstellt, wann geändert). Duplikate prüfen + anpassen statt neu anlegen.
- **Eingangsrechnungen Auto-Scan**: Mails mit Rechnungsmerkmalen erkennen, Rechnungsdaten extrahieren, Offene-Posten-DB anlegen, Kira pflegt Status bis bezahlt/erledigt

**Dashboard:**
- **Stats-Zeile klickbar mit Filter**: Klick auf "N Leads" → Kommunikation-Tab öffnet sich direkt mit "Neue Lead-Anfrage" Filter
- **Tagesstart-Briefing**: Backend vorhanden (generate_daily_briefing()), Morgen-Anzeige im Dashboard fehlt noch

**Sonstiges:**
- **Kunden-360-Ansicht** — geplant, noch nicht gebaut
- **Falsch benannte Archiv-Ordner löschen**: anfrage/, info/, invoice/, kaimrf/, shop/ im Mail-Archiv (entstanden durch Bug in session-cc, können manuell gelöscht werden)
- **Neue Archiv-Ordner**: Gelöschte Elemente/Entwürfe entstehen erst nach nächstem mail_monitor-Lauf (automatisch)

---

### ✅ ZULETZT ERLEDIGT

- **session-hh (2026-03-30)**: IMAP-Postfach + Ordner-System: Live-IMAP Ordnerliste (UTF-7 Fix), config-basierte Sync-Ordner, Mail verschieben, Gelöschte-Protokoll-System, archiv_cleanup.py, Kira LLM sieht bereinigte Mails
- **session-hh Nachtrag**: Einstellungen-UI Archiv-Bereinigung (Frist + Toggle)
- **session-ii (2026-03-30)**: Lese-Markierung Standard auf "manuell" + mehr Zeitoptionen (1s–5min), kira_verwendet Auto-Markierung in _build_data_context() + mail_vollinhalt_lesen()
- **session-gg**: Dashboard Typ-Labels fix (sonstiger_vorgang→Vorgang), überfällig-Badge
- **session-ff**: Mail-Nachklassifizierung recheck_mails() + UI-Button
- **session-ee**: Postfach Hover-Aktionen, Bulk-Bar, SVG-Toolbar, kira_verwendet Badge
- **session-dd**: Postfach Favoriten-Sterne, Kombiniertes Postfach, folder_type-Filter

---











\### Stats-Zeile in dashboard (n offen / n Leads / n Angebote) klickbar → springt zum richtigen Tab (ist schon drinn) soll aber auch gleich den filter dazu anzeigen, sonst keine gute Funktion, also klick n leads --> filter bei kommunikation direkt neue leads und



\--   wissen: alle Bibliotheken regelsteuerungen mit zeitstempel verseheh wann erstellt wann geändert, nicht vorhanden.. keine zeit kein Datum, bei nächster Änderung dann setzen.  --- wird hiese Datenbank durch kira tasächlich erweitert und gepflegt? das soll automatisch geschehen durch ihr gelerntes.. nicht nur die starren sachen die wir am anfang eingtragen haben. auch soll sie nachschauen ob ähnliche bestehen und anpassen wenn es Änderungen gibt. ansonsten wiedersprechen sich irgendwann die Ereignisse. kira llm soll diese Datenbanken und das log immer mit nutzen und aktualisieren und muster erkennen. smart haltmir nützt das nichts wenn sich preise ändern, und die werden nie automatisch gepflegt, deshalb sollte jede abfrage, jedes Angebot, jede Rechnung , jede antwort etc. zusammenarbeiten und auf muster suchen die zusammengehören , analysieren, auswerten, und anpassen, dass dann dokumentieren, vorher nachher ist, etc..





&#x20;Was noch NICHT mit der neuen UI umgebaut wurde (alte Komponenten oder fehlend):



\### Mail-Lese-Ansicht (Mail-Vollansicht/Thread) — besteht, aber kein UI-Rebuild

\### Direkte E-Mail-Antwort — geplant, noch nicht gebaut

\### Kunden-360-Ansicht — geplant, noch nicht gebaut

\### Kira Tagesstart-Briefing im Dashboard — Backend vorhanden (generate\_daily\_briefing()), Morgen-Anzeige im Dashboard fehlt noch

\### Organisation-Tab (Termine/Fristen/Rückrufe) — im Überblick beschrieben, aber kein eigenständiger UI-Rebuild dokumentiert







\###  Funktion Eingangsrechnungen: Eingangsrechnungen die über beliebiges Postfach kommen (Einstellbar), und die atribute (in einstellungen neue karte zum anpassen erstellen im aussehen der ) entweder und oder haben,

&#x20;(neues Einstellungsmenü oder an vorhandenes sinvoll hinzufügen)



* 'hasTheWord' value='Rechnung OR  Beleg OR adobe\_transaction OR invoice OR Beitragsrechnung OR Mobilfunk-Rechnung OR transaktion OR Deine Rechnung von Apple'/> im Betreff oder Body

&#x09;	<apps:property name='hasAttachment' value='true'/>



* 'forwardTo' value='raumkult@inbox.lexware.email'/> über account invoice@sichtbeton-cire.de ---



* Wenn kein Anhang, wie z.b. bei apple, dann body scannen und aus body eine rechnung erstellen/ extrahieren, wenn der body auch rechnungsdaten enthält, und per pdf als anhang weiterleiten
* diese eingangsrechnungen/Mails nicht in die aufgaben aufnehmen.
* zusätzlich diese eingangsrechnungen  scannen, alle rechnungsdaten in eine datenbank ablegen und als eingangrechnungen in geschäft mit aufnehmen.
* Kira KI LLM soll bei allen anderen mails und in der mail und im anhang selbst nach auffälligkeiten suchen was die Rechnungselbst betrifft, ob diese offen ist, schon bezahlt, zahlungserinnerung besteht (dann aber ständig diese mit anderen prüfen ob dann irgendwann bezahlt durch bestätigungsmails) etc. Quasi offene posten db anlegen die ständig abzuarbeiten ist von kira llm bis diese auf einen qualifizierten status gesetzt wurde von llm oder mir. llm soll bei erkennen automatisch zuordnen und in die geschäftszahlen sinnvoll zuordnen - wichtig hier, das ist mein wunsch, bitte optimierungen vorschlagen und dann einbauen
* Einstellungsmenü dazu bei mails und konten mit allen möglichen einstellungen und verbesserungen dieser funktion!
* alles was dafür benötigt wird das es funktioniert in die einstellungen aufnehmen und einrichtungsassitent dafür bauen und zu verfügung stellen. mit test und allen schnick schnack.. zusätzlich dokumentation, einrichtung und wo bekomme ich was her im aktuellen stand (internet recherche verwenden) optional mit llm chatten, problem direkt reinkopieren und lösung über chat finden.





##### \### DATVERSE Tabellen per API einbinden  (neues Einstellungsmenü oder an vorhandenes sinvoll hinzufügen)

* Rechnungstabellen in Kira einbinden
* Kira sendet an zwei verschiedenen Tabellen nach DATEVERSE jeweils die .json Datei die über eine Mail eingegangen ist.

&#x09;und oder - im Betreff steht: Neue Bestellung!!  (anpassbar)1

&#x09;und oder - im Body der Mail steht ausschlieslich der .json inhalt. dieser kommt nicht per anhang (ist aber im Menü einstellbar)

&#x09;und oder - Nachricht kommt von noreply@billbee.io (in den Einstellungen anpassbar)

* Optional, manuell per Mail einen json inhalt an eine mailadresse oder API senden
* alles was dafür benötigt wird das es funktioniert in die einstellungen aufnehmen und einrichtungsassitent dafür bauen und zu verfügung stellen. mit test und allen schnick schnack.. zusätzlich dokumentation, einrichtung und wo bekomme ich was her im aktuellen stand (internet recherche verwenden) optional mit llm chatten, problem direkt reinkopieren und lösung über chat finden.



* alternativ abrufbar, manueller abruf oder automatischer Abruf über (ehem.Admin Panel) Funktion abrufen der neuen rechnungen aus Lexoffice wie in folgenden Dateien voll funktionsfähig. Funktion wie sie ist, vollständig in die App intigrieren/übernehmen, auch mit Daten, aber alles dann optional durch eintellungsmenü einstellbar. api, mail, schutz, mailvorlage (anpassen einzelner Einstellungen, die aber die grundfunktion nicht zerschießen)
* darauf achten, dass die funktion und formate so bleiben wie jetzt orginal in den dateien, ohne diese festgesetzten vorganen von lexoffice und Billbee funktioniert am ende der export oder import sonst nicht. kritsche einstellunegn die das zerstören können nicht zulassen.



der derzeitige start wird über den btn <button onclick="startProcess()">🔄 Prozess Starten</button> in der datei "C:\\Users\\kaimr\\OneDrive - rauMKult Sichtbeton\\07\_Webseiten\\VS\\sonstige Webseiten\\Sichtbeton-cire.de\\admin\_lex\_billb.php"

&#x20;ausgelöst.

"C:\\Users\\kaimr\\OneDrive - rauMKult Sichtbeton\\07\_Webseiten\\VS\\sonstige Webseiten\\Sichtbeton-cire.de\\02\_lex\_billb\_fetch\_invoice\_details.php"

"C:\\Users\\kaimr\\OneDrive - rauMKult Sichtbeton\\07\_Webseiten\\VS\\sonstige Webseiten\\Sichtbeton-cire.de\\03\_lex\_billb\_fetch\_contact.php"

"C:\\Users\\kaimr\\OneDrive - rauMKult Sichtbeton\\07\_Webseiten\\VS\\sonstige Webseiten\\Sichtbeton-cire.de\\04\_lex\_billb\_convert\_to\_billbee.php"

"C:\\Users\\kaimr\\OneDrive - rauMKult Sichtbeton\\07\_Webseiten\\VS\\sonstige Webseiten\\Sichtbeton-cire.de\\admin\_lex\_billb.php"

"C:\\Users\\kaimr\\OneDrive - rauMKult Sichtbeton\\07\_Webseiten\\VS\\sonstige Webseiten\\Sichtbeton-cire.de\\00\_lex\_billb\_master.php"

"C:\\Users\\kaimr\\OneDrive - rauMKult Sichtbeton\\07\_Webseiten\\VS\\sonstige Webseiten\\Sichtbeton-cire.de\\01\_lex\_billb\_fetch\_invoices.php"



Bitte alle codes prüfen und ggfls. reparieren. die funktionen 00 -04 funktionieren auf jedenfall, diese nicht verändern in der struktur wenn es nicht nötig ist. Die Dataverse funktion darin habe ich nie zum laufen bekommen, ist aber im prinzip nicht nötig wenn die funktion DATVERSE Tabellen per API einbinden dann funktioniert. Logs und fehlermeldung sowie status etc und job einstellungen zeit intervall etc mit übernehmen oder in den einstellunegn ergänzen.





##### **### Lexware Office Anbindung.**



* In diesem zuge die Lexware Anbindung einrichten. API steht in einer der oben genannten Dateien lex\_billb.
* Dokumentation dazu https://developers.lexware.io/docs/#lexware-api-documentation bitte browser öffnen und nötige informationen holen.
* Ziel ist es, Alle möglichen Daten für KIRA bereitzustellen in vorhandenen oder neu angelegten Datenbanken, dass dann auch Module wie Kunden / Aufträge / Kalkulationen / Preispositionen / Cashflow etc. aktiviert werden könenn und insgesamt das Modul Geschäft besser und realistischer läuft. KIRA llm soll auch hier dann voll zugriff erhalten.
* Vorschläge für extra Module und Funktionen was Lexoffice mit zusammenarbneit mit dieserapp deutlich verbessert vorschlagen.



\################## als extra Regel anlegen: immer wenn neue funktionen oder module gebaut werden, ganze app durchschauen, ob diese neuen funktionen oder module in vorhandene eingebunden werden können oder müssen wie auch z.b. bei einstellungen, sei es llm, backup, sync, abfragen, kommunikation, marketing... etc. immer alles schlau und vorbereitend vorbereiten und in eine vorhandene arbeitsliste - bestandsliste - checkliste - feature liste packen und stetig aktualisieren. bitte bestätige mir in worten so, dass ich sehe, wie du es verstanden hast ################



\#### Wie sieht es mit den datenbank größen aus? haben diese einfluss auf die performens der app, also schnelligkeit? sollte die ab und an domprimiert werden, und wenn ja automatisch-manuell- hat kira dann trotzdem zugriff- was gibt es für möglichkeiten und technik?



\### nach update, werden einige einstellungen immer zurückgersetzt. sollte alles bleiben, schutz einbauen. später dann auch wichtig, wenn als app verkauft wird und updates eingespielt werden, dass einstellungen bleiben



\### Logo upload ist da, aber keine sinnvollen einstellungen dazu. z.b logo größe. ich habe jetzt eins hinzugefügt, der blaue hintergrund vom K symbohl ist noch zu sehen. das nur anzeigen wenn kein logo gesetzt. bzw. nicht das blaue k logo, sondern eine version von kira launcher.

### bitte als bild von der kira verknüfung auch ein bild von kiralauncher in grösst möglicher form als bild setzen



\### Wie sieht es mit dem derzeitigen Schutz aus der app, ist diese durch angriffe von aussen wenn das programm auf meinem windows Rechner installiert ist geschützt? Was gibt es für optionen (beste) um meine sensiblen Daten zu schützen? Kann das LLM modell damit unfug machen? oder teilt das llm meine informationen zum lernen der eigenen ki bei verwendung von api? wenn ja oder nein, kann man das als menüpunkt hinzufügen und einstellen? aber nicht nur optisch, sondern tatsächlich mit der gewünschten





\###  Einstellungen Toast-Position ist noch bei Design, kann aber zum menü Benachrichtigungen.

sinnvolle  einstellungsmöglichleiten hinzufügen, z.b. anzeigedauer - größe - aussehen





\## wenn ich eine karte verlasse, z.b. Design, habe dort aber noch ungespeicherte einstellungen, meldung-speichern-verwerfen? oder autospeichern und info -



\### alle einstellungen auf werkseinstellungen - optionen design - kira - datenbanken (alle möglichkeiten durch checkboxen) und alles, mit 3fach absicherung.hier auch für zukunft , immer nachfolgemodule automatisch mit einbeziehen



\### Urlaubsmodus Auto-Aktivierung (Backend-Check getestet, läuft zumindest in UI alles) - prüfe aktiv ob dann tatsächlich keine meldungen mehr kommen. Kira soll aber trotzdem im urlaubsmodus weiter arbeiten wenn programm offen, damit die sortierung dann nicht nach urlaub chaos erzeugt. es sollte dann nur schlau markiert werden was in der urlaubszeit gekommen ist, automatisch an Kunden, die eine antwort erwarten, oder wenn neuer lead, nicht newsletter systemmails etc. schlau halt eine abwesenheit angepasst an den inhalt der mail senden, (persönlichkeit) durch llm. das dann dokumentieren, z.b. durch breif nach urlaub was passiert ist, oder und komplette liste. was kira llm gemacht hat, was für mails an welche kunden gesendet wurden, welche rechnungen eingegangen sind und so sachen --- hier weitere vorschläge passend zum thema suchen und in planung aufnehmen!Was jetzt schon durch aktuelle app aktivierbar ist, aktivieren!







\####### Backup in cloud dienste (verschiedene -und funktion direkt aktivieren) verschiedener Optionen - optionen design - kira - datenbanken - etc. was sinnvoll ist (alle möglichkeiten durch checkboxen) hier auch für zukunft , immer nachfolgemodule automatisch mit einbeziehen



\###### PHP Skripte für Verbindungen, z.b. cronjobs auf Server .json abfragen/aktualisieren mit log und fehler (detailiert) Beispiel, es kommen auf meinem hosteeuroe server json Dateien in unregelmäßigen abständen, z.b. rechnungen und dazugehörige positionen. es muss also über die app einstellbar sein als verbindung un anlegen, das die bestimmte seite per php abgerufen wird und prüft ob neue datei mit shema x vorhanden ist und diese importiert. Das anlegen so einer verbindung sollte für den benutzer ohne code möglich sein, nur mit angabe der wichtigen dinge die es benätigt. der code wird dann automatisch im hintergrund durch ki llm erstellt u gespeichert im Programm. intervall , pausieren,  und so weiter alles einstellbar. cors Geschichten dabei immer mit beachten und code und ux schlau dafür bereitstellen





\###### sprach modul, dass ich diktieren kann wie bei chatgpt, diktieren, durch bestätigen transskript durch kira llm und einfügen in Chat, aber noch nicht absenden. absenden aktiv durch klick



\###### wenn ich in kira Chat mir ihr sachen ausarbeite, und dann analysedaten oder sonstige Auswertungen in eine Datei möchte, pdf, docx, md txt oder was auch immer, kann mir die llm das direkt über den eingebauten Chat zu verfügung stellen, die erstellten auch in meiner Datenbank speicher für erneuten abruf, exportiere o. drucken, und kann ich mir das dokument egal was für ein inline anzeigen lassen, also im Programm selbst, mit Aktionen, dass es nicht zum anzeigen ausgelagert wird auf ein Programm von Windows?







====================================================================================================================







\### Urlaubsmodus Auto-Aktivierung (Backend-Check getestet, läuft zumindest in UI alles) - prüfe aktiv ob dann tatsächlich keine meldungen mehr kommen. Kira soll aber trotzdem im urlaubsmodus weiter arbeiten wenn programm offen, damit die sortierung dann nicht nach urlaub chaos erzeugt. es sollte dann nur schlau markiert werden was in der urlaubszeit gekommen ist, automatisch an Kunden, die eine antwort erwarten, oder wenn neuer lead, nicht newsletter systemmails etc. schlau halt eine abwesenheit angepasst an den inhalt der mail senden, (persönlichkeit) durch llm. das dann dokumentieren, z.b. durch breif nach urlaub was passiert ist, oder und komplette liste. was kira llm gemacht hat, was für mails an welche kunden gesendet wurden, welche rechnungen eingegangen sind und so sachen --- hier weitere vorschläge passend zum thema suchen und in planung aufnehmen!Was jetzt schon durch aktuelle app aktivierbar ist, aktivieren!



\###  Benachrichtigungsmöglichkeit Benachrichtigung via

Wie wird der Nachfass gemeldet -  ist Aufgabe erstellen.. KIRA LLM tatsächlich aktiv?



\### Mail-Klassifizierung (Budget-Modell) sehr gut! aber, je nachdem welches model gerade aktiv ist, sollte man sehen wie es gerade dort eingestellt ist. option --> Kira wählt -- Admin wählt (generell krittische einstellungen (Admin vorbereiten) noch nicht aktivieren bis wir die rollen und login haben (todo)







### sichtbar in der App Dashboard( kurz)- kommunikation (detailiert) eigene kachel, heute gesendete mails an.. von warum, llm-von user x , fehlgeschlagen, erfolg, datum uhrzeit, bei fehler zu konto oder erneut senden und weiters sinnvolle







\-- Wenn ich mails ignoriere, dann lernende frage von kira ki aktive, warum? damit sie weiss warum und bei neuen mails besser zuordnen kann.



\-- bei später klick auf mail bearbeiten -- hier auch lernede frage von kira ki aktive, warum? damit sie weiss warum und bei Zuordnung und Wiedervorlagen anderer ähnlicher mail, aufgaben, etc muster erkennt und die Benachrichtigung oder todos beser einordnen kann. ausserdem wäre hier die angabe von Datum und Uhrzeit gut, wann soll ich dich erneut erinnern oder die mail vorlegen? Das dann aber auch machen und in einen Kalender eintragen. wichtig, nicht das sie dann weg ist, weil die funkt noch nicht da ist und ich dann nicht mehr erinnert werde





\-- mail duplikatserkennung erforderlich durch kira aktive ki bei Import mail. Szene habe 14 gleiche Nachrichten erhalten, wo nur der anhang anders war erkennen, evtl gruppieren und nachfrage (vorhanden?)
Richte in diesem zug das senden an leni marlenabraham@gmail.com über das konto info@raumkult ein. Gib dir beim erstellen der Mail etwas mehr mühe ;) in html formatiert und etwas schicker, passend zum kira brand. (für beide mails, erste einladung , dann zweite passwort , und dritte als dauerhafte vorlage für benachrichtigungen.







###### **Tagesbriefing** immer mit Zeitangabe von wann das Briefing ist --- hinzufügen

Wenn hinter kira Launcher ein element zum klicken ist, dann soll das programm das erkennen und der launcher rutscht beiseite wenn die maus dort hingeht und versucht an das element zu kommen.. wenn möglich, dass schlau lösen



**Mail-Monitor Polling-Intervall (Sekunden)** - auf stunden/minuten umstellen - bessere eingabe machen



###### **Entwickler-/Admin-Bereich** oder  separates internes Diagnose-Dashboard für Kira App

Belegablage für eingescannte oder hochgeladene oder per mail im bestimmten Format kommende - Briefe aller art, mit der auch KIRA zusammenarbeitet und automatisch diese ablage nach neuen inhalten durchsucht Und bearbeitet je nach Bearbeitungsstand Wobei der verarbeitet erinnert Komma wieder erinnert Komma und wieder erinnert Und auch erkennt Bezahlung oder Mahnungen Zahlungsänderungen oder sonstigen Aufforderungen aus dem Briefen Weitere Schritte einleitet die wichtig sind Punkt vollautomatisch über das Llm.







###### **Bei partner view...** 

Wenn Leni in der aktuellen html version ein feedback gibt, dann kommt zwar die speichern seite- erfolg, wird aber nur temporär in der html gespeichert. Das was sie eingegebn hat, wird nicht commitet. wie kann das geändert werden? bei jeder feadback eingabe durch speicher btn auto commit oder beim speichern dann sagen wenn du mit allen fertig bist , dann musst du auf dem hauptbildschirm dort.. oder dort noch deine gesammelten einträge abschicken... --- dann wäre es auch gut, wenn oben bei den karten - wo man die karten filtern kann, noch ein filter hat, meine feadbacks, oder so.. ###
Wie ist  der ablauf wenn Leni auf der html seite kommentiert? wie werde ich benachrichtigt? was war der plan und wie wird es aktuell umgesetzt? welche listen werden automatisch aktualisiert?





 bitte schau dich im projekt um und bring dich auf den neuesten stand. führe dann die nächste aufgabe immer mit den regeln aus der agent.md aus:



###### **Kira und KIRA LLM**

\-Komplette Struktur und Architektur verbessern





&#x20;### Die Anzahl der Ungelesene Nachrichten im Batch Symbol Der Haupt Sidebar Vom Postfach Stimmt nicht. bitte Alle Posteingänge Von allen Postfächern Einbeziehen "D:\\OneDrive - rauMKult Sichtbeton\\01\_BILDER\\Screenshots\\Screenshot 2026-03-30 050052.png"



&#x20;- Dann Frage Komma das Verschieben der vertikalen Fenster Komma ist das Nach Neustart dann so gespeichert Wenn nicht bitte nachholen

&#x20;

\### Wenn möglich In der Checkliste aufnehmen Zur abarbeiten für diese App Aufnehmen das vielleicht markiert ist welche E Mail Tatsächlich Kira markiert Hat Das sie benutzt für den Kontext oder für Auswertungen oder sonstiges Dass man das im Vorfeld schon sieht diese Funktion entweder direkt einbauen oder Vormerken, zusammengefasst Kira soll die E-Mails Direkt markieren Die sie verwendet Und Durchgerast rastert hat Um diese vielleicht auch später Noch benutzen zu können oder müssen.
"D:\\OneDrive - rauMKult Sichtbeton\\01\_BILDER\\Screenshots\\Screenshot 2026-03-29 185040.png"
"D:\\OneDrive - rauMKult Sichtbeton\\01\_BILDER\\Screenshots\\Screenshot 2026-03-29 184328.png"
"D:\\OneDrive - rauMKult Sichtbeton\\01\_BILDER\\Screenshots\\Screenshot 2026-03-29 184216.png"

Ach so Noch eine wichtige Sache, Bei Der Funktion Von ungelesen zu gelesen Das bitte einstellbar machen im Menü Bei Konten, entweder nach Zeit Zeit einstellbar Wann es ungelesen sein soll Komma oder auch die Option Bis ich es Als gelesen markiere. diese Funktion brauche ich dringend























───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

❯ welche Konten werden von kira gescannt? Die klassifizierung oder das was kira machen sollte, stimmt nicht. z.b im invoice ordner sind benachrichtigung vom system das

&#x20; ausstehende Rechnungen von Kunde x bezahlt sind, dann z.b. ein shema das wichtig ist wenn solche mails in der art kommen Mitteilung zur Verlängerung für Ihren

&#x20; Ecwid-Shop, dass das systematisch von llm prüfen und schauen wo kann ich es ablegen und kai informieren.. kira llm sollte so mitdenken, also die aktive llm, dass sie

&#x20; wenn sie so etwas sieht und keine datenbank findet, dass sie kai benachrichtigt, später dann den admin (nur Admin) und sagt, ich habe das gefunden und denke es könnte wichtig sein, habe

&#x20; das ganze system gecheckt datenbanken und so weiter und weiss nicht wo ich das einordnen soll, ich habe eine idee dazu das du in dein system integrieren solltest. Kiro sollte dabei zugriff auf die Plan dateien vom Sytem checklisten was ist geplanzt , was wurde erstellt bekommen, sodass sie dann auch weiss was sie mir vorschlagen kann. Damit meine ich aber nicht nur die mails, sondern alle informationen egal von welchen kanal eine nachricht reinkommt. Kira LLM sollte auch eine übersicht erhalten und zugriff haben von den bestehenden Datenbanken oder bereichen wo sie ablegen kann die ständig aktuell gehalten wird, damit sie überhaupt suchen und einordnen kann. Ich möchte das die llm also das model mit dem programm aktiv im hintergrund aktiv arbeitet. Ich habe das gefühl kira arbeitet nur nach den angelegten festen regeln und kann das das nicht richtig tun, da es dann nicht richtig programiert ist. 



Weitere beispiele: 



* Nächste termine und fristen bereich ist nie aktuell, das steht seit anfang märz so, es gibt unzählige elemente die termine und fristen enthalten in den kanälen, tauchen aber nicht auf

&#x20;



* Geschäft aktuell

Letzte Bewegungen  wird überhaupt nicht aktualisiert, das hat sie einmal gemacht und dann nie wieder





* Wenn man jetzt mal im Bereich Der Kommunikation Schaut Siehe Screenshots, Dann kann man deutlich sehen Paß Sie nur Einen Kommentar an jeder E-Mail Anheftet, aber diese nicht wirklich bearbeitet oder weiterverarbeitet. Die Struktur passt überhaupt nicht. z.b. Rechnung RE20260006 von Marcus Hantke -- zur Kentniss??? bitte was? wiso wird das nicht zugeordent und bei eingangsrechnungen abgelegt ---- Ihre Kreditkarte wurde abgelehnt. - zur kenntniss?? Das ist eine so wichtige Information, Kira LMM soll dem ja hier in einem Fenster sofort mitteilen dass ich hier mal nachschauen soll ob alles ok ist um mir Vorschläge machen --- Rechnung für Microsoft 365 Business Standard einsehen  -  Diese Nachricht Kam 2 mal, Kira Hat Sie zweimal unterschiedlich eingestuft Komma weil sie mit den Regeln nicht klar kam, deshalb aktiv LLM - Solche Nachrichten Das sind aber Hat die Zukunft trotzdem wichtig dass man sie irgendwo schon vorbereitend hinlegt für die Buchhaltung Komma dass man Belege sammelt Und schon vorbereitet zum Bitte versenden einen lexoffice oder schaut, Ob es dann bei Anbindung Der Lex Office Totschan Einträge gibt Komma oder ob es Nachrichten gibt die schon an lexoffice oder invoicefetcher gesendet wurden, aber ohne sich nur auf die beiden zu beschränken.  --- 



* Aw: AW: Aw: AW: Neue Betonkosmetik Anfrage (Landing) – Anna Berres kein Handlungsbedarf??? bedanken für die Information an frau Berres könnte man hier vorschlagen, gleich mit einem text, Und einer benachrichtigung, Hallo Kai Komma oder , der gerade angemeldet ist , hier ist eine Antwort von dein Angebot oder Der preisaufstellung von.. (hier halt auch wieder die verknüfung zur kompletten korospontens) von Anna Berres, 
* Nachfass 1/3: A-SB260092 — Elwira und David Wendel

&#x09;Angebot A-SB260092 ist 41 Tage offen (5,965.71 EUR). Nachfass 1 ist fällig.

&#x09;➜ Höfliche Nachfass-Mail senden (Vorlage nutzen)   ----- der auftrag ist bereits fertig und bezahlt.. das macht hier kein sinn.. wieder nur stumpf diese mail betrachtet, keinen bezug zu anderen hergestellt, es gibt unzählige weitere Nachrichten und verläufe.. 



* Nachfass 1/3: A-SB260093 — etna GmbH

Angebot A-SB260093 ist 41 Tage offen (36,928.31 EUR). Nachfass 1 ist fällig.

➜ Höfliche Nachfass-Mail senden (Vorlage nutzen)   ---- hier steht z.b. im text dass sie das Angebot gelesen haben und erstmal bis sommer zurückstellen, aufgrund der höhe, hier sinnvolle sachen machen, Termin erstellen, und automatisch dem user im sommer sagen, frag doch noch einmal nach, jetzt wäre ein guter Zeitpunkt, gleich mit erstellten vorschlag zum senden --- und wenn diese Nachricht kommt, dann auch gleich antwort vorschlagen, hier user, das Kam gerade rein Komma ist aber noch nicht vom Tisch Leo bedanken uns erst mal hier hast du gleich eine Vorlage Und ich erinnere dich dann im Sondern noch einmal daran Punkt den Termin habe ich Mehr gemerkt und Werde dich aktiv erinnern





\#####  Kira und kira llm Schaut nicht Aktiv bei Eingang einer Nachricht in allen anderen Nachrichten Ob es da Verbindungen gibt, es wird stumpf nur Die eine Nachricht genommen Und dann einfach Kommentare hingeschrieben und nix weiter gemacht, das ist nicht mein ziel.. ich finde so habe ich viel mehr arbeit als hätte ich nur mein Postfach bei Outlook. Kira sollte ja meine Assistenz sein, Ach so habe ich tatsächlich viel mehr Arbeit als vorher Das ist nicht der Sinn dahinter





Ich hoffe Dass meine Beispiele dir zeigen , was ich meine, Es gibt natürlich noch unheimlich viele weitere Beispiele aber die können ja schon mal verdreuchten wie ich das gerne hätte und was sie jetzt nicht tut.



Cool wäre es Wenn es tatsächlich wieso ein aktiv Fenster gibt, Dass das Modell Wenn das im hintergrund arbeitet Und ich vor dem PC sitze( gibt ja heute sensoren in den PCs oder man kann einen anbinden) das das merkt, Und dann direkt mit mir kommuniziert, trotzdem die Übersichten bedient und alles einschreibt wo es hin muss Und alles ausfüllt und alles vorbereitet und die Diagnosen erstellt Komma soll alles weitere Hintergrund geschehen, Aber Schön wäre es Wenn das einmal aktiv Fenster Gibt Wo sie dann Ja schreibt Ja schau mal Das das oder das ist eingetroffen was wollen wir machen damit. dann schon vorschläge..  Ja habe ich das schaut ihr das mal an hab schon vorbereitet …. Und wenn man dann Aktiv mit ihr arbeitet und Punkte Bearbeitet, werden die dann aktiv im Hintergrund In die Datenbanken geschrieben oder irgendwo zu dokumentiert Dass man immer wieder damit Arbeiten kann Wie das hier auch vorgesehen ist. Wenn es irgendetwas gibt Was man Bei mir einbauen kann Unter Umsätzen Komma ich bin für Vorschläge offen.



Ansonsten Erst mal zur Ersten Aufgabe oben, Bräuchte ich ein Konzept Auf mein System angepasst das ist ja schon gibt Was das wirklich verbessert Die Agentenstruktur Aufbereitet. Bitte recherchiere dafür wie man das In meinem Fall umsetzen kann. sei es Mehrere Agentur gleichzeitig einsetzen Oder Strukturen entsetzen oder Verknüpfungen setzen Komma ich habe keine Ahnung du bist da Experte Bitte helf mir die richtige Lösung zu finden das Das Unternehmen wirklich Aktiv unterstützt wird. 



























