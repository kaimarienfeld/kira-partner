**06 - Einstellungen - Mail und Konten Plan für UI**



Arbeitsanweisung für Claude – Mail \& Konten



Bitte den Unterpunkt „Mail \& Konten“ jetzt bereits in der UI als vollwertigen Einstellungsbereich anlegen, auch wenn die komplette Backend-Logik für mehrere Konten, Signaturen und Sync/Fallback noch nicht vollständig fertig ist.



Wichtig:

Die UI soll bereits so vorbereitet werden, dass später ohne größeren Umbau folgende Funktionen angeschlossen werden können:



1\. Mehrere Mailkonten verwalten



\* pro Konto Anzeigename

\* E-Mail-Adresse

\* Kontostatus

\* Standardkonto

\* Aktiv für Abruf ja/nein

\* Aktiv für Versand ja/nein



2\. Versandlogik



\* Antworten möglichst vom ursprünglichen Konto

\* Standard-Absender pro Vorgangstyp

\* Versandkonto für allgemeine Kommunikation

\* Versandkonto für Angebote / Rechnungen / Supportfälle



3\. Signaturen



\* eigene Signatur pro Konto

\* Signatur-Vorschau

\* Signatur-Zuweisung nach Konto

\* spätere Erweiterung für kontextabhängige Signaturen vorbereiten



4\. Abruf / Empfang



\* vorbereitete Oberfläche für Abrufstatus

\* sichtbarer Zustand je Konto

\* spätere Polling-/Abruf-Logik anschließbar machen



5\. Sync / Fallback



\* UI-Bereich für Hauptweg und Fallback auf Sync-Tool vorbereiten

\* Status „verbunden / vorbereitet / in Prüfung / in Planung“ sauber abbilden

\* nicht als Fake-Funktion vortäuschen, aber klar als vorbereitete Architektur zeigen



6\. Test \& Diagnose



\* Platz für Testversand

\* Verbindungstest

\* letzter Versandstatus

\* letzter Abruf / letzte Synchronisierung



Wichtig:

Wenn einzelne Funktionen technisch noch nicht vollständig vorhanden sind, dann diese in der UI sauber als vorbereitet, verknüpft oder in Planung kennzeichnen.

Nicht als leere Seite.

Nicht als Fake-Interaktion.

Nicht als harte Attrappe.



UX-Vorgabe:

Die Seite soll wie ein hochwertiger geschäftlicher Mail-Steuerbereich wirken, nicht wie ein technisches SMTP-Formular und nicht wie ein Webmail-Klon. Sie Vorgabe 



