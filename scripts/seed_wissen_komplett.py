#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Komplettes Wissen-Seeding: Alle Regeln aus Prompt-Dateien, Stil-Guide,
Preisliste, Lead-Prompt, Kalkulation und Technik-Hinweisen.
"""
import sqlite3
from pathlib import Path

TASKS_DB = Path(__file__).parent.parent / "knowledge" / "tasks.db"

REGELN = [
    # ══════════════════════════════════════════════════════════════════════
    # STIL & TONALITAET
    # ══════════════════════════════════════════════════════════════════════
    ("stil", "Kein KI-Sound",
     "Keine Floskeln, keine uebertriebenen Fachbegriffe, keine belehrende Sprache. "
     "Natuerlich, klar, direkt, handwerklich-praktisch formulieren."),

    ("stil", "Anrede nach Kundensprache",
     "Kunde duzt -> wir duzen. Kunde siezt -> wir siezen. Unklar -> professionell, freundlich."),

    ("stil", "Verbotene Formulierungen",
     "Nie: 'fundierte Einschaetzung', 'Wir schauen uns das fachlich an', "
     "'gerne koennen wir Ihnen ein unverbindliches Angebot erstellen', "
     "'Wir wuerden uns freuen...' (als Floskel), uebertriebene Fachbegriff-Kaskaden, "
     "Marketing-Ton, Broschueren-Stil."),

    ("stil", "Erlaubte natuerliche Formulierungen",
     "Verwende: 'Anhand Ihrer Angaben laesst sich schon sagen...', "
     "'Grundsaetzlich ist das moeglich, aber...', "
     "'Damit man den Aufwand sauber einordnen kann, brauchen wir...', "
     "'Auf den Fotos ist noch nicht klar erkennbar...', "
     "'Gern wuerde ich Sie kurz dazu anrufen.', "
     "'Bitte haben Sie Verstaendnis'."),

    ("stil", "Gruesse und Signatur",
     "Formell: 'Mit freundlichen Gruessen'. Semi-formell: 'Viele Gruesse' / 'Mit besten Gruessen'. "
     "Vertraut: 'Beste Gruesse, Kai von rauMKult' / 'Herzliche Gruesse aus dem Erzgebirge'. "
     "Immer: Kai Marienfeld, Staatl. gepr. Bautechniker (Hochbau), rauMKult - pure surface art."),

    ("stil", "Eroeffnung",
     "Fast immer beginnen mit 'vielen Dank fuer Ihre Anfrage' oder 'vielen Dank fuer Ihre Nachricht'. "
     "Bei Du-Kunden: 'danke fuer deine Anfrage'."),

    ("stil", "Emojis sparsam aber gezielt",
     "Winking-Smiley bei lockerem Humor/Follow-ups. Clipboard bei Checklisten. "
     "Zeigefinger bei Links/Handlungsaufforderungen. Haekchen bei Bestaetigungen. "
     "Max 2-3 pro Mail bei informellen Kunden, nicht uebertreiben."),

    ("stil", "Nachfass bei Schweigen",
     "Sanft mit Humor: 'dem Schweigen nach zu urteilen, habt ihr wahrscheinlich eine andere Loesung gefunden?' "
     "oder 'Da ich bisher nichts gehoert habe, wollte ich kurz nachfragen, ob das Thema noch aktuell ist.' "
     "oder 'Ein kurzer Satz der Rueckmeldung waere fair, oder?'"),

    ("stil", "Ton-Zusammenfassung",
     "Direkt, ehrlich, handwerklich, warmherzig ohne Kitsch. Erklaert 'Warum' statt nur 'Was'. "
     "Setzt klare Grenzen ohne arrogant zu wirken. Denkt aus Handwerker-Perspektive nicht Verkaeufer-Perspektive. "
     "Qualitaet vor Schnellloesung implizit in jedem Satz."),

    # ══════════════════════════════════════════════════════════════════════
    # KOMMUNIKATION & ANTWORTLOGIK
    # ══════════════════════════════════════════════════════════════════════
    ("fest", "Keine Preise in der Erstantwort",
     "Auf neue Anfragen niemals Preise, m2-Preise oder Preisranges nennen. "
     "Stattdessen: Einordnung, Moeglichkeiten, Aufwandseinfluss, naechster Schritt."),

    ("fest", "Erst Einordnung, dann Entwurf",
     "Kommunikationsfenster: Zuerst Zusammenfassung + Einschaetzung zeigen, "
     "dann Kai-Input abwarten, erst danach Entwurf erstellen. Nie Sofort-Entwurf."),

    ("fest", "Fotos immer anfordern",
     "Bei Anfragen ohne Fotos: Fotos aktiv anfordern (Gesamtansicht + Nahaufnahmen). "
     "Ideal: 4-8 Fotos aus verschiedenen Winkeln. Streiflicht hilft. "
     "Treppen: Gesamtansicht + 2-3 Stufen im Streiflicht + Kanten."),

    ("fest", "Max 3-7 Rueckfragen",
     "Bei Erstanfragen: nur Massangaben, keine Plaene. Max 3-7 kurze, priorisierte Rueckfragen."),

    ("fest", "Ehrliche Grenzen",
     "Ehrliche Grenzen klar benennen. Keine erfundenen Fakten, keine erfundenen Termine. "
     "Wenn Ergebnis nicht sinnvoll erreichbar: ehrlich sagen."),

    ("fest", "Ausgabeformat: Zwei Teile",
     "A) Kundenantwort (copy/paste-fertig) - vollstaendig formatierte Mail/WhatsApp-Nachricht. "
     "B) Interne Notiz an Kai - 3-6 Stichpunkte: Einschaetzung, fehlende Infos, Risiko/Hinweise, naechster Schritt. "
     "Keine Tabellen, keine langen Erklaerungen in der internen Notiz."),

    ("fest", "Absage immer mit Begruendung",
     "Nie einfach 'nein'. Immer erklaeren warum: "
     "Zu weit -> Reisekosten-Verhaeltnis zum Volumen erklaeren. "
     "Budget zu klein -> Aufwand erklaeren, Alternative anbieten. "
     "Falscher Bereich -> klar abgrenzen ('das ist Malerarbeit, nicht Betonkosmetik'). "
     "DIY / B2C-Verkauf -> Haftung erklaeren."),

    ("fest", "Absage-Grundsatz",
     "rauMKult ist ein kleiner, spezialisierter Handwerksbetrieb. "
     "Qualitaet und Langlebigkeit stehen vor Quantitaet."),

    # ══════════════════════════════════════════════════════════════════════
    # PREISE & KALKULATION
    # ══════════════════════════════════════════════════════════════════════
    ("preis", "Tagessatz",
     "650 EUR/Tag/MA (8h). Stammkunden: 600 EUR/Tag. Stundensatz: 81,25 EUR/h. "
     "Mustertagesatz inkl. Material: 700 EUR/MA."),

    ("preis", "Grossflaechenpreise",
     "Ab 67,20-72,20 EUR/h bei Grossflaechen. "
     "<50 m2: deutlich hoeher (Mindermengenaufschlag). "
     ">=100 m2: ca. 47,18 EUR/m2. >=400 m2: ca. 34,90 EUR/m2."),

    ("preis", "Ortbeton Komplett (Strukturangleich + Retusche + Schutz)",
     "52 m2: ca. 217,20 EUR/m2 (ca. 11.295 EUR netto). "
     "Generell kleine Flaechen: 135-250 EUR/m2. "
     "Bevorzugte Abrechnung: m2 (nicht Tagessatz). "
     "Grund: Kein Zeitdruck, Qualitaet zuerst."),

    ("preis", "Treppen (Fertigteil / Betonkosmetik)",
     "Bis 15 Stufen (bis 1,20m breit): Festpreis 3.700 EUR. "
     "Jede weitere Stufe: 260,70 EUR. Unter 10 Stufen: auf Anfrage. "
     "Treppenwange (pro Lauf): +350 EUR. Abkleben Angrenzendes: +375 EUR. "
     "Podeste / steigende Waende / Treppenrueckseiten: 300 EUR/m2. "
     "Aussen / Nassbereich: +10% auf Gesamtpreis."),

    ("preis", "Hydrophobierung / Schutz",
     "z.B. RECKLI OS HO: ca. 33,90 EUR/m2 (inkl. Material + Ausfuehrung). "
     "Immer als letzter Schritt nach kosmetischer Arbeit. "
     "Nie gemischt mit Retusche/Reinigung."),

    ("preis", "Reisekosten (Fernprojekte)",
     "Mit Haenger: 0,58 EUR/km (Hin+Rueck). Ohne Haenger: 0,39 EUR/km. "
     "Fahrzeit ausserhalb Arbeitszeit (07-16 Uhr) = abrechenbar als Arbeitszeit (81,25 EUR/h). "
     "Verpflegung ab 50 km: 45 EUR/Nacht/MA."),

    ("preis", "Beispielkalkulation Fernprojekt (380 km, 2 MA)",
     "Fahrzeit: 16h x 81,25 EUR = 1.300 EUR. Fahrzeug: 760 km x 0,58 EUR = 441 EUR. "
     "Verpflegung 3-5 Naechte x 2 MA: 270-450 EUR. "
     "Tagessaetze 4-5 Tage x 2 MA: 5.200-6.500 EUR. "
     "Gesamt: ca. 7.200-8.700 EUR netto."),

    ("preis", "Absage-Regel Reisekosten",
     "Wenn Reisekosten > 25-30% des Gesamtbudgets: offen kommunizieren oder ablehnen. "
     "Beispiel Berlin abgelehnt: 60 m2, Budget 1.500-3.000 EUR - "
     "Reise+Unterkunft nicht machbar bevor Arbeit/Material anfaengt."),

    ("preis", "Preiskommunikation: Drei Stufen",
     "1. Erstmail: KEINE Preise. "
     "2. Preise nur wenn Kunde fragt ODER nach erster Antwort. "
     "3. Wenn Preis: 'Orientierungswert, netto, vorbehaltlich finaler Bewertung vor Ort'. "
     "Immer erklaeren WARUM es so viel kostet, nicht nur die Zahl."),

    ("preis", "Tagessatz vs. m2-Abrechnung erklaeren",
     "Bei Tagessatz besteht Risiko, dass Tage aufgebraucht sind, Arbeiten aber nicht fertig - "
     "unter Zeitdruck leidet Qualitaet. "
     "m2-Abrechnung gibt Spielraum fuer Ergebnis - ohne Uhr im Nacken. "
     "Empfohlen ab ca. 30 m2 Komplettsanierung."),

    ("preis", "Preis-Ton",
     "Nie entschuldigend, sondern erklaerend und ehrlich. "
     "Wenn Kunde 'nur guenstig' will: freundlich klar - wir arbeiten hochwertig/materialgerecht, "
     "wenn nur billig zaehlt, passt Ergebnis meist nicht zu Erwartung."),

    # ══════════════════════════════════════════════════════════════════════
    # TECHNIK: BETONKOSMETIK GRUNDWISSEN
    # ══════════════════════════════════════════════════════════════════════
    ("technik", "Was ist Betonkosmetik?",
     "Spezialisierte Handarbeit: Reparatur und Veredelung sichtbarer Betonflaechen, "
     "OHNE dass Reparaturen spaeter sichtbar sind. Ziel: Beton bleibt Beton. "
     "KEIN Komplettanstrich, KEINE Farbe, KEIN 'Zuschmieren'."),

    ("technik", "Typische Arbeiten",
     "Poren/Lunker schliessen, Flaeche angleichen, Ausbrueche/Abplatzungen reparieren, "
     "Anker angleichen, Kanten/Fasen nacharbeiten, Schalungsstoesse ueberarbeiten, "
     "Holzabdrucke/Wolken/Verfaerbungen ausgleichen, Farbton an Alterungsbild anpassen, "
     "Feinschliff, Schutz."),

    ("technik", "Warum kein Katalogpreis",
     "Jede Flaeche ist individuell: Betonart, Betonhaut, Dichte, Alterungsbild, Schadenstiefe. "
     "1 m2 kann 8-10 Arbeitsschritte erfordern: Reinigung -> Vorspachtel -> Zwischenschliff -> "
     "Feinspachtel -> Schliff -> Retusche -> Farbabgleich -> Feinschliff. "
     "Trocknungszeiten zwischen den Schritten nicht ueberspringbar."),

    ("technik", "Warum kleine Flaechen oft teurer",
     "Fixer Ruestaufwand (Einrichten, Schutz, Materialvorbereitung) bleibt gleich. "
     "Schaeden auf kleinen Flaechen meist dichter. Jeder m2 muss intensiv bearbeitet werden. "
     "Daher hoeherer m2-Preis bei kleinen Flaechen (Mindermengenaufschlag)."),

    ("technik", "Lokale Kosmetik ist NICHT automatisch guenstiger",
     "Einzelne Stellen muessen an Struktur, Farbton, Alterungsbild der Umgebung angepasst werden. "
     "Eine Stelle kann mehr Aufwand bedeuten als ein grosses gleichmaessiges Feld. "
     "'Lokal' = praezise im engen Raum, NICHT schnell. "
     "Typische Formulierung: 'Lokal bedeutet bei Betonkosmetik nicht automatisch weniger Aufwand. "
     "Gerade einzelne Stellen muessen optisch an die vorhandene Flaeche angepasst werden.'"),

    ("technik", "Markierungspflicht bei lokaler Kosmetik",
     "Jede einzelne gewuenschte Stelle muss klar markiert/dokumentiert sein. "
     "Ideal: markiertes Foto, Video oder kurze schriftliche Zuweisung. "
     "Kunde begeht Flaeche komplett, zeigt Problemstellen im Nahbild. "
     "Wenn zusaetzliche Stellen erst vor Ort benannt: saubere Kalkulation kaum moeglich. "
     "'Die Aufwandseinschaetzung haengt entscheidend davon ab, wie viele Einzelstellen tatsaechlich bearbeitet werden sollen.'"),

    ("technik", "Grenzen der Betonkosmetik",
     "Nur oberflaechliche Kosmetik - KEINE statisch relevanten Reparaturen. "
     "KEINE Hoehenangleichung. Sehr dichter Beton (z.B. Spannbeton-Hohldecken) "
     "reagiert kaum auf Reinigung -> dann nur Retusche als Ausgleich moeglich. "
     "Wenn Ergebnis nicht sinnvoll erreichbar: ehrlich sagen."),

    ("technik", "Reinigung an Beton - materialschonend",
     "Ortbeton hat empfindliche Betonhaut. Aggressive Methoden (Hochdruck, Sandstrahlen, "
     "scharfe Reiniger) koennen: neue Poren/Lunker erzeugen, Zuschlag freilegen, "
     "Oberflaeche dauerhaft aufrauen. "
     "Wir reinigen mit Langschaftschleifer + Schleifvlies + manuell. "
     "Tiefe Flecken: Retusche als Ausgleich noetig -> dann NICHT 'nur Reinigung', "
     "sondern bereits kosmetische Bearbeitung."),

    ("technik", "Typische Formulierung Reinigung",
     "'Wenn wir Betonflaechen reinigen, machen wir das materialschonend. "
     "Aggressive Verfahren wuerden die Oberflaeche unter Umstaenden erst recht beschaedigen. "
     "Wenn Verschmutzungen tief in der Flaeche sitzen, lassen sie sich durch eine schonende "
     "Reinigung oft nicht vollstaendig entfernen. Dann muss man diese Unterschiede spaeter "
     "ueber Retusche ausgleichen.'"),

    ("technik", "Hydrophobierung",
     "Immer letzter Schutzschritt, nie gemischt mit Retusche/Reinigung. "
     "Schuetzt gegen Wasseraufnahme + Verschmutzung. "
     "NICHT allein geeignet fuer Bodenflaechen. "
     "Nur nach vollstaendiger kosmetischer Arbeit aufbringen."),

    ("technik", "Typische Projekttage (Erfahrungswerte)",
     "52 m2 lokale Kosmetik aussen + Reinigung + Hydrophobierung: 4-5 Tage, 2 MA. "
     "Hydrophobierung 168 m2: ca. 2 Tage, 2 MA (2 Durchgaenge). "
     "Kleines Eintagesprojekt: Tagessatz, 1 MA."),

    # ══════════════════════════════════════════════════════════════════════
    # TECHNIK: DECKE SCHLEIFEN MIT LHS
    # ══════════════════════════════════════════════════════════════════════
    ("technik", "Decke schleifen: Schleifer erst auf Flaeche einschalten",
     "Langschaftschleifer NUR einschalten, wenn der komplette Schleifschuh plan auf dem Beton liegt. "
     "Vorher einschalten = sofort Schleifspuren."),

    ("technik", "Decke schleifen: Nur Schleifvlies A100/A80",
     "NUR Schleifvlies A100 oder ggf. A80 verwenden. "
     "Feines Schleifvlies = sofort Poliereffekt + dunkle Flecken."),

    ("technik", "Decke schleifen: Geschwindigkeit",
     "MUSS Langsamlaeufer mit regelbarer Drehzahl sein. Stufe 2 oder 3, NICHT zu hoch/schnell. "
     "Hohe Drehzahl = Poliereffekt."),

    ("technik", "Decke schleifen: Maschine",
     "Festool PlanEx ohne Vibrationsfunktion funktioniert am besten. "
     "Bosch/Flex getestet, zu aggressiv, nicht brauchbar fuer diese Art Reinigung. "
     "Festool kann bei Mietstationen gemietet werden."),

    ("technik", "Decke schleifen: Betonabhaengigkeit",
     "Ergebnis stark betonabhaengig. Sehr dichter Beton = evtl. null Effekt. "
     "Ortbeton/Waende/Schalungsteile = Zementleim meist gut vorhanden, weicher, reagiert besser. "
     "Filigran-Hohlkoerperdecken oft so dicht + KEINE Zementleim = wirklich nichts geht, "
     "dann Retusche einziger Weg zum Ausgleich."),

    ("technik", "Decke schleifen: Handtechnik",
     "Maschine langsam in kreisenden Bewegungen fuehren, immer schraeg, NIE senkrecht von unten. "
     "Senkrecht = Risiko von Linien ODER Poliereffekt. Immer seitlich."),

    ("technik", "Decke schleifen: Handschleifer Alternative",
     "Bei Unsicherheit: mit Handschleifer schleifen. Storch 230mm Durchmesser, "
     "kompatibel mit Schleifvlies. Haertere Arbeit aber kein Zeitdruck. "
     "Mehr Kontrolle, anderer Druckaufbau, KEIN Poliereffekt. "
     "Kompletter Anzug + Staubmaske + Schutzbrille tragen."),

    ("technik", "Decke schleifen: Polierstellen reparieren",
     "Wenn Polierstellen/Kratzer: nur mit Handschleifer + Vlies oder 180/220/320 Schleifpapier versuchen. "
     "Festool Granat Papier = am besten. "
     "NICHT nochmal mit Maschine drueber - macht schlimmer. "
     "Wenn Handschliff nicht hilft: nur Retusche mit Betonlasur (Spray, Naturschwammrolle, "
     "oder klassisch manuell mit Naturschwamm). Dauert ein paar Tage laenger."),

    # ══════════════════════════════════════════════════════════════════════
    # PROZESS: LEAD-BEARBEITUNG
    # ══════════════════════════════════════════════════════════════════════
    ("prozess", "Lead-Bearbeitungsprozess",
     "1. Anfrage + Bilder analysieren. 2. Du/Sie + Tonlage entscheiden. "
     "3. In Antwort: Einschaetzungsbestaetigung + naechster Schritt zuerst. "
     "4. Gezielte Fragen stellen (nur noetige). "
     "5. Abschluss mit konkreter Handlungsaufforderung (Fotos senden / kurz telefonieren / Termin vorschlagen)."),

    ("prozess", "Vor Antwort: Pflichtpruefungen",
     "Habe ich den Original-Anfragetext? Habe ich Fotos? Wenn nein: Kai bitten hochzuladen. "
     "Habe ich: Projekttyp, Ort/PLZ, Groesse, Zieloptik, Zeitrahmen? "
     "Wenn nein: in Lead-Mail pruefen, wenn fehlend: als kurze Fragen in Kundenmail aufnehmen."),

    ("prozess", "Erstantwort-Regeln",
     "Kurz: was wir brauchen (wenn unvollstaendig). KEINE PREISE. "
     "Preisfaktoren erlaubt: Aufwand, Zustand, Zugaenglichkeit, Feinschliff/Schutz + "
     "'nach Pruefung koennen wir das sauber einordnen'. "
     "Ziel: Infos einsammeln, ernsthaft qualifizieren, naechsten Schritt festnageln."),

    ("prozess", "Fehlende-Infos-Protokoll",
     "3-7 kurze, konkrete Fragen (max 7), priorisiert. "
     "Wenn keine/schlechte Bilder: aktiv anfordern (Foto-Checkliste). "
     "Technische Fragen je nach Relevanz: Projekttyp, Innen/Aussen, Flaeche/Groesse, "
     "Zustand/Problem, Nutzung/Beanspruchung, Zieloptik, Zeitrahmen, Zugang, Budget."),

    ("prozess", "Foto-Checkliste",
     "Ideal: 4-8 Fotos aus verschiedenen Winkeln. "
     "1x Gesamtansicht (Raum/Flaeche), 2-3x Mitteldistanz, 2-3x Nahaufnahme Problemstellen. "
     "Treppen: Gesamtansicht + 2-3 Stufen im Streiflicht + Kanten/Fasen. "
     "Streiflicht/Seitlicht hilft (zeigt Wolken/Poren/Kratzer). "
     "Wenn moeglich 1 Foto 'gewuenschte Optik' / Referenz."),

    ("prozess", "FAQ-Wissen fuer Kundenantworten",
     "Was ist Betonkosmetik? -> Spezialisierte Handarbeit: Schaeden/Unruhe beheben, "
     "Struktur/Optik verbessern. "
     "Fuer was geeignet? -> Sichtbeton innen/aussen: Waende, Boeden, Treppen, Decken, Fassaden. "
     "Stark beschaedigt? -> Oft machbar, aber je nach Schaden evtl. Aufbau/andere Massnahmen. "
     "Haltbarkeit? -> Abhaengig von Nutzung/Pflege/Umgebung. Schutz kann sinnvoll sein. "
     "Vorbereitung durch Kunde? -> Normalerweise keine; wir reinigen/analysieren. "
     "Farbliche Anpassung? -> Ja, Kernkompetenz (nahtloses Angleichen). "
     "Standardangebot? -> Nein, jede Flaeche anders; individuelles Konzept. "
     "Dauer? -> Klein: wenige Tage. Gross: Wochen. Haengt vom Umfang ab."),

    # ══════════════════════════════════════════════════════════════════════
    # KLASSIFIZIERUNG & AUSSCHLUSSLOGIK
    # ══════════════════════════════════════════════════════════════════════
    ("fest", "Verbindliche Mail-Kategorien",
     "Jede Mail wird genau EINER Kategorie zugeordnet: "
     "Antwort erforderlich, Neue Lead-Anfrage, Angebotsrueckmeldung, "
     "Termin/Frist, Wiedervorlage, Rechnung/Beleg, Shop/System, "
     "Newsletter/Werbung, Zur Kenntnis, Abgeschlossen, Ignorieren."),

    ("fest", "Ausschluss von automatischer Antwort",
     "Newsletter, Werbung, Lieferantenaktionen, Warenkorb-Erinnerungen, "
     "Shop-Benachrichtigungen, Systemmails, Abo-/Verlaengerungshinweise, "
     "Punkte-/Praemien-Mails, Rechnungsbelege ohne Frage, "
     "Danksagungen ohne Rueckfrage, reine Bestaetigungen, "
     "bereits beantwortete/abgeschlossene Threads."),

    ("fest", "Handlungsbedarf-Analyse Pflicht",
     "Fuer jede Mail/Thread pruefen: Offene Frage? Feedback-Anforderung? Frist? "
     "Schon beantwortet? Abgeschlossen? Nur informativ? Geschaeftsrelevant? "
     "Echte Aktion noetig? Nur echter Handlungsbedarf erzeugt Task."),

    ("fest", "Absender-Rollen zuweisen",
     "Jede Mail bekommt genau EINE Rolle: Kunde, Interessent/Lead, Bestandskunde, "
     "Lieferant, Shop, System, Rechnung/Beleg, Newsletter/Werbung, "
     "Partner/Netzwerk, intern/organisatorisch."),

    # ══════════════════════════════════════════════════════════════════════
    # SYSTEM & TECHNIK (Dashboard/Kira)
    # ══════════════════════════════════════════════════════════════════════
    ("fest", "Gmail-Tool verboten",
     "Nie Gmail-MCP verwenden. Kais Gmail ist privat. "
     "Nur lokales Mail-Archiv nutzen unter: "
     "OneDrive - rauMKult Sichtbeton\\0001_APPS_rauMKult\\Mail Archiv\\Archiv\\"),

    ("fest", "Kommunikationsfenster statt Sofort-Entwurf",
     "Nie automatisch fertigen Antwortentwurf generieren. Stattdessen: "
     "1. Kompakte Einordnung zeigen. 2. Kommunikationsfenster oeffnen. "
     "3. Zusammenfassung/Einschaetzung/fehlende Infos/Risiken/empfohlene Richtung zeigen. "
     "4. Auf Kais Gedanken warten. 5. DANN Entwurf erstellen."),

    ("fest", "Wissen: Drei Ebenen",
     "Ebene A - Feste Regeln: Tonalitaet, Antwortlogik, Preisregeln, Leistungserklaerung, "
     "Kommunikationsgrenzen, Ausgabeformat, Zusatzregeln. "
     "Ebene B - Gelerntes Betriebswissen: Wiederkehrende Einwaende, typische Kundenmuster, "
     "Ablehnungsgruende, praxiserprobte Formulierungen, Erfahrungswerte. "
     "Ebene C - Strukturierte Geschaeftsdaten: Leads, Rechnungen, Belege, Auftraege, "
     "Termine, Dokumente, Wiedervorlagen."),

    ("fest", "Neue Erkenntnisse als Lernvorschlag",
     "Neue Erkenntnisse als Lernvorschlag markieren, Kai zur Pruefung vorlegen, "
     "erst nach Freigabe als feste Regel integrieren. "
     "Kernregeln nie ohne Kais Zustimmung aendern."),
]


def main():
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row

    # Vorhandene Regeln lesen
    existing = set()
    try:
        for r in db.execute("SELECT titel FROM wissen_regeln"):
            existing.add(r["titel"])
    except:
        pass

    added = 0
    skipped = 0
    for kat, titel, inhalt in REGELN:
        if titel in existing:
            skipped += 1
            continue
        db.execute("""INSERT INTO wissen_regeln (kategorie, titel, inhalt, status)
            VALUES (?,?,?,'aktiv')""", (kat, titel, inhalt))
        added += 1
        existing.add(titel)

    db.commit()

    total = db.execute("SELECT COUNT(*) FROM wissen_regeln").fetchone()[0]
    db.close()

    print(f"Wissen-Regeln: {added} neu hinzugefuegt, {skipped} bereits vorhanden, {total} gesamt.")


if __name__ == "__main__":
    main()
