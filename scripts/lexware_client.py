"""
lexware_client.py — Lexware Office API Client fuer KIRA
Session: session-eee (2026-04-01)

Lexware Office API Dokumentation:
  https://developers.lexware.io/docs/

Endpunkte (aktuelle API-Version: v1):
  Alt:  https://api.lexoffice.io/v1/   (PHP-Altstrecke, laut Research-Agent tot seit Ende 2025)
  Neu:  https://api.lexware.io/v1/     (neue offizielle Domain nach Rebranding)

  Konfigurierbar via config.json["lexware"]["api_base_url"].
  Default: api.lexoffice.io (da PHP-Altstrecke damit lief — Kai muss ggf. auf api.lexware.io wechseln)

Auth: Bearer Token (API-Key aus Einstellungen)
"""

import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("lexware_client")

# API-Basis — konfigurierbar via config.json["lexware"]["api_base_url"]
# Research-Agent (2026-04-01): api.lexoffice.io koennte tot sein, neue URL: api.lexware.io
# → Kai soll beide testen und config anpassen
LEXWARE_API_BASE_DEFAULT = "https://api.lexoffice.io/v1"
LEXWARE_API_BASE_NEW = "https://api.lexware.io/v1"
LEXWARE_API_BASE = LEXWARE_API_BASE_DEFAULT  # Fallback wenn config nicht gelesen

# Rate-Limit Handling
_RATE_LIMIT_DELAY = 1.0   # Sekunden zwischen Requests
_RATE_LIMIT_429_WAIT = 60  # Sekunden bei 429 Too Many Requests
_MAX_RETRIES = 3


class LexwareAuthError(Exception):
    """API-Key fehlt oder ungueltig."""
    pass


class LexwareAPIError(Exception):
    """Allgemeiner API-Fehler."""
    def __init__(self, status_code, message, body=""):
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(f"HTTP {status_code}: {message}")


class LexwareClient:
    """
    Python-Client fuer die Lexware Office REST API.

    Verwendung:
        from lexware_client import LexwareClient, get_client
        client = get_client(config)  # Empfohlen
        belege = client.get_vouchers("invoice", "open")

    Token wird aus config.json gelesen (Key: lexware.api_key).
    NIEMALS hardcoded oder aus secrets.json.
    """

    def __init__(self, api_key: str, db_path: Path = None, api_base: str = None):
        if not api_key:
            raise LexwareAuthError("Lexware API-Key nicht gesetzt. Bitte in Einstellungen > Lexware Office eintragen.")
        self.api_key = api_key
        self.db_path = db_path
        self._last_request_ts = 0.0
        # Konfigurierbare API-Basis (Kai kann auf api.lexware.io umstellen)
        self._api_base = (api_base or LEXWARE_API_BASE_DEFAULT).rstrip("/")

    # ------------------------------------------------------------------
    # Interner HTTP-Request mit Rate-Limit und Retry
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, data: dict = None,
                 params: dict = None) -> dict:
        """
        Fuehrt einen HTTP-Request gegen die Lexware API durch.

        Args:
            method: GET | POST | PUT | PATCH | DELETE
            path:   z.B. "/voucherlist" oder "/contacts/{id}"
            data:   JSON-Body (fuer POST/PUT)
            params: Query-Parameter (fuer GET)

        Returns:
            dict: JSON-Antwort der API

        Raises:
            LexwareAuthError:  401 / fehlender Key
            LexwareAPIError:   sonstiger HTTP-Fehler
        """
        # Rate-Limit: mind. 1s zwischen Requests
        elapsed = time.time() - self._last_request_ts
        if elapsed < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - elapsed)

        url = self._api_base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        body_bytes = None
        if data is not None:
            body_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")

        for attempt in range(_MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    url, data=body_bytes,
                    headers=headers, method=method
                )
                self._last_request_ts = time.time()
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8")
                    if raw.strip():
                        return json.loads(raw)
                    return {}
            except urllib.error.HTTPError as e:
                status = e.code
                body_raw = ""
                try:
                    body_raw = e.read().decode("utf-8")
                except Exception:
                    pass

                if status == 401:
                    raise LexwareAuthError("Lexware API-Key ungueltig oder abgelaufen.")
                if status == 429:
                    logger.warning(f"Lexware Rate-Limit (429). Warte {_RATE_LIMIT_429_WAIT}s ...")
                    time.sleep(_RATE_LIMIT_429_WAIT)
                    continue  # Retry
                if status == 422:
                    raise LexwareAPIError(status, "Unprocessable Entity — Validierungsfehler", body_raw)
                if status == 404:
                    raise LexwareAPIError(status, "Ressource nicht gefunden", body_raw)
                raise LexwareAPIError(status, e.reason or "API-Fehler", body_raw)
            except urllib.error.URLError as e:
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(2)
                    continue
                raise LexwareAPIError(0, f"Verbindungsfehler: {e.reason}")

        raise LexwareAPIError(429, "Maximale Retry-Anzahl erreicht (Rate-Limit)")

    # ------------------------------------------------------------------
    # Verbindungstest
    # ------------------------------------------------------------------

    def test_connection(self) -> dict:
        """
        Testet die API-Verbindung.
        Returns: {"ok": True, "info": {...}} oder {"ok": False, "error": "..."}
        """
        try:
            result = self._request("GET", "/profile")
            return {"ok": True, "info": result}
        except LexwareAuthError as e:
            return {"ok": False, "error": str(e), "code": 401}
        except LexwareAPIError as e:
            return {"ok": False, "error": str(e), "code": e.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e), "code": 0}

    # ------------------------------------------------------------------
    # Voucher / Belege
    # ------------------------------------------------------------------

    def get_vouchers(self, voucher_type: str = "invoice",
                     voucher_status: str = "open",
                     page: int = 0, size: int = 100) -> dict:
        """
        Listet Belege.

        voucher_type: invoice | creditnote | quotation | deliverynote |
                      orderconfirmation | purchaseinvoice | recurringinvoice
        voucher_status: draft | open | paid | paidoff | voided | overdue |
                        accepted | rejected | transferred | shared

        Returns: {"content": [...], "totalPages": n, "totalElements": n}
        """
        params = {
            "voucherType": voucher_type,
            "voucherStatus": voucher_status,
            "page": page,
            "size": size,
        }
        return self._request("GET", "/voucherlist", params=params)

    def get_all_vouchers(self, voucher_type: str, voucher_status: str = None) -> list:
        """
        Holt ALLE Belege eines Typs (paginiert).
        Gibt eine flache Liste zurueck.
        """
        all_items = []
        page = 0
        while True:
            params = {"voucherType": voucher_type, "page": page, "size": 100}
            if voucher_status:
                params["voucherStatus"] = voucher_status
            result = self._request("GET", "/voucherlist", params=params)
            items = result.get("content", [])
            if not items:
                break
            all_items.extend(items)
            is_last = result.get("last", False)
            if is_last or page >= result.get("totalPages", 1) - 1:
                break
            page += 1
        return all_items

    def get_voucher(self, voucher_id: str) -> dict:
        """Holt Belegdetails (Positionen, Steuern, etc.)."""
        return self._request("GET", f"/invoices/{voucher_id}")

    def get_voucher_document(self, voucher_id: str) -> str:
        """
        Gibt die PDF-Dokument-URL zurueck (falls vorhanden).
        Returns: URL-String oder None
        """
        try:
            result = self._request("GET", f"/voucherlist/{voucher_id}/document")
            return result.get("documentFileId")
        except LexwareAPIError:
            return None

    def create_invoice(self, payload: dict) -> dict:
        """
        Erstellt eine Rechnung.

        Mindest-Payload:
        {
            "voucherDate": "2026-04-01T00:00:00.000+02:00",
            "address": {"contactId": "...", ...},
            "lineItems": [{"type": "custom", "name": "...", "unitPrice": {...}, "quantity": 1}],
            "totalGrossAmount": ...,
            "taxConditions": {"taxType": "gross"},
        }
        """
        return self._request("POST", "/invoices", data=payload)

    def create_quotation(self, payload: dict) -> dict:
        """Erstellt ein Angebot."""
        return self._request("POST", "/quotations", data=payload)

    def create_credit_note(self, payload: dict) -> dict:
        """Erstellt eine Gutschrift."""
        return self._request("POST", "/creditnotes", data=payload)

    def finalize_voucher(self, resource_type: str, voucher_id: str) -> dict:
        """
        Finalisiert (fertigstellt) einen Beleg — z.B. Invoice.
        resource_type: invoices | quotations | creditnotes
        """
        return self._request("PUT", f"/{resource_type}/{voucher_id}/document/pdf")

    # ------------------------------------------------------------------
    # Kontakte
    # ------------------------------------------------------------------

    def get_contacts(self, page: int = 0, size: int = 100,
                     customer: bool = True, vendor: bool = False) -> dict:
        """
        Listet Kontakte.
        Returns: {"content": [...], "totalPages": n}
        """
        params = {
            "page": page,
            "size": size,
            "customer": str(customer).lower(),
            "vendor": str(vendor).lower(),
        }
        return self._request("GET", "/contacts", params=params)

    def get_all_contacts(self) -> list:
        """Holt alle Kontakte (paginiert). Nutzt totalPages + last-Flag als Sicherheitsnetz."""
        all_contacts = []
        page = 0
        while True:
            result = self.get_contacts(page=page, size=100)
            items = result.get("content", [])
            if not items:
                break
            all_contacts.extend(items)
            total_pages = result.get("totalPages", 1)
            is_last = result.get("last", False)
            if is_last or page >= total_pages - 1:
                break
            page += 1
        return all_contacts

    def get_contact(self, contact_id: str) -> dict:
        """Holt einen Kontakt."""
        return self._request("GET", f"/contacts/{contact_id}")

    def create_contact(self, payload: dict) -> dict:
        """
        Erstellt einen Kontakt.

        Mindest-Payload (Unternehmen):
        {
            "roles": {"customer": {"number": 10001}},
            "company": {"name": "Mustermann GmbH"},
            "addresses": {"billing": [{"street": "...", "zip": "...", "city": "...", "countryCode": "DE"}]}
        }
        """
        return self._request("POST", "/contacts", data=payload)

    def update_contact(self, contact_id: str, payload: dict) -> dict:
        """Aktualisiert einen Kontakt."""
        return self._request("PUT", f"/contacts/{contact_id}", data=payload)

    # ------------------------------------------------------------------
    # Artikel
    # ------------------------------------------------------------------

    def get_articles(self, page: int = 0, size: int = 100,
                     article_type: str = None) -> dict:
        """
        Listet Artikel.
        article_type: SERVICE | PRODUCT (optional)
        """
        params = {"page": page, "size": size}
        if article_type:
            params["type"] = article_type
        return self._request("GET", "/articles", params=params)

    def get_all_articles(self) -> list:
        """Holt alle Artikel (paginiert). Nutzt totalPages + last-Flag als Sicherheitsnetz."""
        all_articles = []
        page = 0
        while True:
            result = self.get_articles(page=page, size=100)
            items = result.get("content", [])
            if not items:
                break
            all_articles.extend(items)
            is_last = result.get("last", False)
            if is_last or page >= result.get("totalPages", 1) - 1:
                break
            page += 1
        return all_articles

    def create_article(self, payload: dict) -> dict:
        """
        Erstellt einen Artikel.

        Mindest-Payload:
        {
            "title": "Betonkosmetik Leistung",
            "type": "SERVICE",
            "netPrice": 100.00,
            "unitName": "Stunde",
            "taxRateType": "regular"
        }
        """
        return self._request("POST", "/articles", data=payload)

    # ------------------------------------------------------------------
    # Dateien / Dokumente
    # ------------------------------------------------------------------

    def get_files(self, voucher_id: str) -> dict:
        """Listet Dateien die einem Beleg angehaengt sind."""
        try:
            return self._request("GET", f"/files/{voucher_id}")
        except LexwareAPIError:
            return {}

    def upload_file(self, file_path: Path, file_type: str = "voucher") -> dict:
        """
        Laedt eine Datei hoch (z.B. PDF einer Eingangsrechnung).
        Returns: {"id": "...", "fileName": "...", "fileSize": n}
        """
        import mimetypes
        mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        # Multipart-Upload via urllib
        boundary = "----KIRA_LEXWARE_UPLOAD_" + str(int(time.time()))
        file_bytes = file_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

        url = f"{self._api_base}/files"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------------
    # Zahlungen / Offene Posten
    # ------------------------------------------------------------------

    def get_payment_conditions(self) -> list:
        """Listet verfuegbare Zahlungsbedingungen."""
        try:
            result = self._request("GET", "/payment-conditions")
            return result if isinstance(result, list) else result.get("content", [])
        except LexwareAPIError:
            return []

    # ------------------------------------------------------------------
    # Profil / Account
    # ------------------------------------------------------------------

    def get_profile(self) -> dict:
        """Holt Profil-Informationen (Organisation, Lizenz, etc.)."""
        return self._request("GET", "/profile")

    # ------------------------------------------------------------------
    # Posting Categories (fuer Buchhaltung/Eingangsbelege)
    # ------------------------------------------------------------------

    def get_posting_categories(self) -> list:
        """
        Listet Buchungskategorien (fuer Eingangsbelege / purchase vouchers).
        Gibt [] zurueck wenn Endpunkt nicht verfuegbar (plan-abhaengig).
        """
        try:
            result = self._request("GET", "/posting-categories")
            return result if isinstance(result, list) else result.get("content", [])
        except LexwareAPIError:
            return []

    # ------------------------------------------------------------------
    # Purchase Vouchers (Eingangsbelege)
    # ------------------------------------------------------------------

    def create_purchase_voucher(self, payload: dict) -> dict:
        """
        Erstellt einen Eingangsbeleg (purchase voucher) in Lexware.

        Mindest-Payload:
        {
            "type": "invoice",
            "voucherDate": "2026-04-01",
            "supplierName": "Lieferant GmbH",
            "totalGrossAmount": 119.00,
            "taxAmount": 19.00,
            "voucherItems": [
                {
                    "amount": 119.00,
                    "taxRatePercent": 19,
                    "postingCategoryId": "...",
                    "lineItemAmount": 119.00
                }
            ]
        }
        """
        return self._request("POST", "/vouchers", data=payload)

    # ------------------------------------------------------------------
    # DB-Sync Methoden
    # ------------------------------------------------------------------

    def sync_belege_to_db(self, db, typen=None) -> dict:
        """
        Synchronisiert Belege aus Lexware in die lokale lexware_belege-Tabelle.

        Args:
            db: SQLite-Datenbankverbindung
            typen: Liste von Vouchertypen, Default: alle relevanten

        Returns:
            {"neu": n, "aktualisiert": n, "fehler": n}
        """
        if typen is None:
            typen = ["invoice", "creditnote", "quotation"]

        # Lexware /voucherlist erfordert voucherStatus als Pflicht-Parameter.
        # Pro Typ alle relevanten Statuses abrufen um vollstaendige Daten zu erhalten.
        _TYP_STATUSES = {
            "invoice":    ["draft", "open", "paid", "paidoff", "voided", "overdue"],
            "creditnote": ["draft", "open", "paid", "paidoff", "voided"],
            "quotation":  ["draft", "open", "accepted", "rejected"],
        }

        stats = {"neu": 0, "aktualisiert": 0, "fehler": 0, "fehler_details": []}

        for typ in typen:
            statuses = _TYP_STATUSES.get(typ, ["open"])
            seen_ids = set()
            belege = []
            for vstatus in statuses:
                try:
                    chunk = self.get_all_vouchers(typ, voucher_status=vstatus)
                    for b in chunk:
                        bid = b.get("id")
                        if bid and bid not in seen_ids:
                            seen_ids.add(bid)
                            belege.append(b)
                except Exception as e_inner:
                    logger.warning(f"Sync-Teilfehler {typ}/{vstatus}: {e_inner}")
            try:
                for b in belege:
                    lex_id = b.get("id", "")
                    if not lex_id:
                        continue
                    existing = db.execute(
                        "SELECT id FROM lexware_belege WHERE lexware_id=?", (lex_id,)
                    ).fetchone()
                    row = {
                        "lexware_id":   lex_id,
                        "typ":          typ,
                        "nummer":       b.get("voucherNumber", ""),
                        "status":       b.get("voucherStatus", ""),
                        "kontakt_id":   b.get("contactId", ""),
                        "kontakt_name": (b.get("address") or {}).get("name", "") or b.get("contactId", ""),
                        "netto":        b.get("totalPrice", {}).get("totalNetAmount", 0),
                        "brutto":       b.get("totalPrice", {}).get("totalGrossAmount", 0),
                        "waehrung":     b.get("currency", "EUR"),
                        "datum":        (b.get("voucherDate") or "")[:10],
                        "faellig":      (b.get("dueDate") or "")[:10] if "dueDate" in b else "",
                        "sync_ts":      datetime.now().isoformat(timespec="seconds"),
                        "payload_json": json.dumps(b, ensure_ascii=False),
                    }
                    if existing:
                        db.execute("""
                            UPDATE lexware_belege SET
                                typ=:typ, nummer=:nummer, status=:status,
                                kontakt_id=:kontakt_id, kontakt_name=:kontakt_name,
                                netto=:netto, brutto=:brutto, waehrung=:waehrung,
                                datum=:datum, faellig=:faellig,
                                sync_ts=:sync_ts, payload_json=:payload_json
                            WHERE lexware_id=:lexware_id
                        """, row)
                        stats["aktualisiert"] += 1
                    else:
                        db.execute("""
                            INSERT INTO lexware_belege
                                (lexware_id, typ, nummer, status, kontakt_id, kontakt_name,
                                 netto, brutto, waehrung, datum, faellig, sync_ts, payload_json)
                            VALUES
                                (:lexware_id, :typ, :nummer, :status, :kontakt_id, :kontakt_name,
                                 :netto, :brutto, :waehrung, :datum, :faellig, :sync_ts, :payload_json)
                        """, row)
                        stats["neu"] += 1
                db.commit()
                # Kontakt-Namen aus lexware_kontakte nachschlagen (UUID → Name)
                try:
                    db.execute("""
                        UPDATE lexware_belege SET kontakt_name = (
                            SELECT k.name FROM lexware_kontakte k
                            WHERE k.lexware_id = lexware_belege.kontakt_id
                        ) WHERE kontakt_id != '' AND kontakt_id IS NOT NULL
                          AND EXISTS (SELECT 1 FROM lexware_kontakte k WHERE k.lexware_id = lexware_belege.kontakt_id)
                    """)
                    db.commit()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Sync-Fehler fuer {typ}: {e}")
                stats["fehler"] += 1
                detail = f"[{typ}] {type(e).__name__}: {e}"
                if hasattr(e, "body") and e.body:
                    try:
                        import json as _j
                        bd = _j.loads(e.body)
                        detail += f" | Body: {bd.get('message', e.body[:200])}"
                    except Exception:
                        detail += f" | Body: {str(e.body)[:200]}"
                stats["fehler_details"].append(detail)

        return stats

    def sync_kontakte_to_db(self, db) -> dict:
        """Synchronisiert Kontakte aus Lexware in lexware_kontakte."""
        stats = {"neu": 0, "aktualisiert": 0, "fehler": 0, "fehler_details": []}
        try:
            kontakte = self.get_all_contacts()
            for k in kontakte:
                lex_id = k.get("id", "")
                if not lex_id:
                    continue
                existing = db.execute(
                    "SELECT id FROM lexware_kontakte WHERE lexware_id=?", (lex_id,)
                ).fetchone()
                # Name ermitteln
                name = ""
                if k.get("company"):
                    name = k["company"].get("name", "")
                elif k.get("person"):
                    p = k["person"]
                    name = f"{p.get('firstName','')} {p.get('lastName','')}".strip()
                # E-Mail aus erster Kontaktperson oder Email-Adresse
                phones = k.get("phoneNumbers") or {}
                email = next(iter(k.get("emailAddresses", {}).get("business", [])), "") or \
                        next(iter(k.get("emailAddresses", {}).get("private", [])), "")
                company = k.get("company") or {}
                row = {
                    "lexware_id":   lex_id,
                    "name":         name,
                    "email":        email,
                    "telefon":      next(iter(phones.get("business", [])), ""),
                    "mobil":        next(iter(phones.get("mobile", [])), ""),
                    "kundennummer": str((k.get("roles") or {}).get("customer", {}).get("number", "") or ""),
                    "ustid":        company.get("vatRegistrationId", "") or "",
                    "steuernummer": company.get("taxNumber", "") or "",
                    "notiz":        k.get("note", "") or "",
                    "adresse_json": json.dumps(k.get("addresses", {}), ensure_ascii=False),
                    "last_sync":    datetime.now().isoformat(timespec="seconds"),
                    "payload_json": json.dumps(k, ensure_ascii=False),
                }
                if existing:
                    db.execute("""
                        UPDATE lexware_kontakte SET
                            name=:name, email=:email, telefon=:telefon, mobil=:mobil,
                            kundennummer=:kundennummer, ustid=:ustid, steuernummer=:steuernummer,
                            notiz=:notiz, adresse_json=:adresse_json,
                            last_sync=:last_sync, payload_json=:payload_json
                        WHERE lexware_id=:lexware_id
                    """, row)
                    stats["aktualisiert"] += 1
                else:
                    db.execute("""
                        INSERT INTO lexware_kontakte
                            (lexware_id, name, email, telefon, mobil, kundennummer, ustid,
                             steuernummer, notiz, adresse_json, last_sync, payload_json)
                        VALUES
                            (:lexware_id, :name, :email, :telefon, :mobil, :kundennummer, :ustid,
                             :steuernummer, :notiz, :adresse_json, :last_sync, :payload_json)
                    """, row)
                    stats["neu"] += 1
            db.commit()
        except Exception as e:
            logger.error(f"Kontakt-Sync-Fehler: {e}")
            stats["fehler"] += 1
            detail = f"[kontakte] {type(e).__name__}: {e}"
            if hasattr(e, "body") and e.body:
                try:
                    import json as _j
                    bd = _j.loads(e.body)
                    detail += f" | Body: {bd.get('message', e.body[:200])}"
                except Exception:
                    detail += f" | Body: {str(e.body)[:200]}"
            stats["fehler_details"].append(detail)
        return stats

    def sync_artikel_to_db(self, db) -> dict:
        """Synchronisiert Artikel aus Lexware in lexware_artikel."""
        stats = {"neu": 0, "aktualisiert": 0, "fehler": 0, "fehler_details": []}
        try:
            artikel = self.get_all_articles()
            for a in artikel:
                lex_id = a.get("id", "")
                if not lex_id:
                    continue
                existing = db.execute(
                    "SELECT id FROM lexware_artikel WHERE lexware_id=?", (lex_id,)
                ).fetchone()
                row = {
                    "lexware_id":  lex_id,
                    "name":        a.get("title", ""),
                    "beschreibung": a.get("description", ""),
                    "einheit":     a.get("unitName", ""),
                    "netto_preis": a.get("netPrice", 0),
                    "steuer_satz": a.get("taxRateType", ""),
                    "typ":         a.get("type", ""),
                    "last_sync":   datetime.now().isoformat(timespec="seconds"),
                    "payload_json": json.dumps(a, ensure_ascii=False),
                }
                if existing:
                    db.execute("""
                        UPDATE lexware_artikel SET
                            name=:name, beschreibung=:beschreibung, einheit=:einheit,
                            netto_preis=:netto_preis, steuer_satz=:steuer_satz,
                            typ=:typ, last_sync=:last_sync, payload_json=:payload_json
                        WHERE lexware_id=:lexware_id
                    """, row)
                    stats["aktualisiert"] += 1
                else:
                    db.execute("""
                        INSERT INTO lexware_artikel
                            (lexware_id, name, beschreibung, einheit, netto_preis,
                             steuer_satz, typ, last_sync, payload_json)
                        VALUES
                            (:lexware_id, :name, :beschreibung, :einheit, :netto_preis,
                             :steuer_satz, :typ, :last_sync, :payload_json)
                    """, row)
                    stats["neu"] += 1
            db.commit()
        except Exception as e:
            logger.error(f"Artikel-Sync-Fehler: {e}")
            stats["fehler"] += 1
            detail = f"[artikel] {type(e).__name__}: {e}"
            if hasattr(e, "body") and e.body:
                try:
                    import json as _j
                    bd = _j.loads(e.body)
                    detail += f" | Body: {bd.get('message', e.body[:200])}"
                except Exception:
                    detail += f" | Body: {str(e.body)[:200]}"
            stats["fehler_details"].append(detail)
        return stats


# ------------------------------------------------------------------
# Factory: Client aus config.json laden
# ------------------------------------------------------------------

def get_client(config: dict, db_path: Path = None) -> "LexwareClient":
    """
    Erstellt einen LexwareClient aus der KIRA-Konfiguration.

    Args:
        config: dict aus config.json
        db_path: Optionaler Pfad zur tasks.db

    Returns:
        LexwareClient-Instanz

    Raises:
        LexwareAuthError: wenn kein API-Key konfiguriert
    """
    lex_cfg = config.get("lexware", {})
    api_key = lex_cfg.get("api_key", "").strip()
    if not api_key:
        raise LexwareAuthError(
            "Lexware API-Key nicht konfiguriert. "
            "Bitte in KIRA > Einstellungen > Lexware Office eintragen."
        )
    # API-Basis aus config (Kai kann auf api.lexware.io umstellen falls api.lexoffice.io tot)
    api_base = lex_cfg.get("api_base_url", LEXWARE_API_BASE_DEFAULT).strip() or LEXWARE_API_BASE_DEFAULT
    return LexwareClient(api_key=api_key, db_path=db_path, api_base=api_base)


def is_lexware_configured(config: dict) -> bool:
    """Prueft ob Lexware konfiguriert und freigeschaltet ist."""
    lex_cfg = config.get("lexware", {})
    has_key = bool(lex_cfg.get("api_key", "").strip())
    is_active = lex_cfg.get("status", "nicht_gebucht") == "freigeschaltet"
    return has_key and is_active


def get_lexware_status(config: dict) -> str:
    """
    Gibt den Modul-Status zurueck.
    Returns: 'nicht_gebucht' | 'gesperrt' | 'freigeschaltet'
    """
    return config.get("lexware", {}).get("status", "nicht_gebucht")
