"""
dataverse_client.py -- Microsoft Dataverse Web API Client fuer KIRA
Session: session-hhh (2026-04-01)

Auth:  Azure Entra ID App (Client Credentials Flow)
API:   Microsoft Dataverse Web API v9.2

Konfiguration in config.json["lexware"]:
  dataverse_tenant_id:     Azure Tenant-/Verzeichnis-ID
  dataverse_client_id:     App-/Client-ID der Entra ID App
  dataverse_client_secret: Client-Secret
  dataverse_org_url:       z.B. https://orgXXXX.crm16.dynamics.com
  dataverse_table_name:    Logischer Plural-Name (z.B. a_btb_arbeiten_vorlagen)
  dataverse_dedup_field:   Spalte fuer Duplikatpruefung (z.B. vorl_arb_BEZEICHNUNG)
"""

import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

logger = logging.getLogger("dataverse_client")


class DataverseAuthError(Exception):
    """Fehler bei der Authentifizierung (Token, Credentials)."""
    pass


class DataverseAPIError(Exception):
    """Allgemeiner Dataverse API-Fehler."""
    def __init__(self, status_code: int, message: str, body: str = ""):
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(f"HTTP {status_code}: {message}")


class DataverseClient:
    """
    Thin Client fuer die Microsoft Dataverse Web API.

    Verwendung:
        from dataverse_client import DataverseClient, get_client
        client = get_client(config)

        # Duplikat-sicherer Import:
        result = client.upsert_record(
            dedup_field="vorl_arb_BEZEICHNUNG",
            dedup_value="Ankerkonen - Grobkosmetik",
            data={"vorl_arb_BEZEICHNUNG": "Ankerkonen - Grobkosmetik", ...}
        )
        # result: {"action": "created"|"updated"|"skipped", "id": "..."}
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 org_url: str, table_name: str = "", dedup_field: str = ""):
        if not all([tenant_id, client_id, client_secret, org_url]):
            raise DataverseAuthError(
                "Dataverse-Credentials unvollstaendig "
                "(tenant_id, client_id, client_secret, org_url benoetigt)."
            )
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.org_url = org_url.rstrip("/")
        self.table_name = table_name
        self.dedup_field = dedup_field
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Holt Access-Token (mit Cache, erneuert 60s vor Ablauf)."""
        now = time.time()
        if self._token and self._token_expires_at - now > 60:
            return self._token

        token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}"
            f"/oauth2/v2.0/token"
        )
        scope = f"{self.org_url}/.default"
        data = urllib.parse.urlencode({
            "grant_type":    "client_credentials",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "scope":         scope,
        }).encode("utf-8")
        req = urllib.request.Request(
            token_url, data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            raise DataverseAuthError(
                f"Token-Anfrage fehlgeschlagen (HTTP {e.code}): {body[:400]}"
            )

        token = result.get("access_token", "")
        if not token:
            err = result.get("error_description") or result.get("error") or str(result)[:200]
            raise DataverseAuthError(f"Kein Token erhalten: {err}")

        expires_in = int(result.get("expires_in", 3600))
        self._token = token
        self._token_expires_at = now + expires_in
        logger.debug("Dataverse Token erneuert, gueltig fuer %ds", expires_in)
        return token

    def _headers(self) -> dict:
        return {
            "Authorization":  f"Bearer {self._get_token()}",
            "Accept":         "application/json",
            "Content-Type":   "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version":    "4.0",
        }

    def _api_url(self, path: str) -> str:
        return f"{self.org_url}/api/data/v9.2/{path.lstrip('/')}"

    # ------------------------------------------------------------------
    # Verbindungstest
    # ------------------------------------------------------------------

    def who_am_i(self) -> dict:
        """WhoAmI -- Verbindungstest."""
        req = urllib.request.Request(self._api_url("WhoAmI"), headers=self._headers())
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_connection(self) -> dict:
        """
        Vollstaendiger Verbindungstest:
        1. Token holen
        2. WhoAmI aufrufen
        3. Optional Tabellen-Zugriff pruefen

        Returns: {"ok": True, "info": {...}} oder {"ok": False, "error": "..."}
        """
        try:
            result = self.who_am_i()
            user_id = str(result.get("UserId", ""))
            info: dict = {"user_id": user_id}

            # Tabellen-Zugriff testen
            if self.table_name:
                try:
                    sel = self.dedup_field or "createdon"
                    url = self._api_url(
                        f"{self.table_name}?$top=1&$select={sel}"
                    )
                    req = urllib.request.Request(url, headers=self._headers())
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        tab = json.loads(resp.read().decode("utf-8"))
                    info["table_ok"] = True
                    info["table_sample_rows"] = len(tab.get("value", []))
                except urllib.error.HTTPError as e:
                    info["table_ok"] = False
                    info["table_error"] = f"HTTP {e.code}"

            return {"ok": True, "info": info}

        except DataverseAuthError as e:
            return {"ok": False, "error": str(e), "code": 401}
        except DataverseAPIError as e:
            return {"ok": False, "error": str(e), "code": e.status_code}
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            return {"ok": False, "error": f"HTTP {e.code}: {body[:300] or e.reason}"}
        except Exception as e:
            return {"ok": False, "error": str(e), "code": 0}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def record_exists(self, field: str, value: str) -> Optional[str]:
        """
        Prueft ob Datensatz mit field=value existiert.
        Gibt GUID zurueck wenn gefunden, None wenn nicht.

        Verhindert Duplikate bei nachfolgendem create_record().
        """
        if not self.table_name or not field:
            return None

        # OData single-quote escaping: ' -> ''
        safe_val = str(value).replace("'", "''")
        url = self._api_url(
            f"{self.table_name}"
            f"?$filter={field} eq '{safe_val}'"
            f"&$top=1&$select={field}"
        )
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise DataverseAPIError(e.code, e.reason or "Fehler bei Duplikatpruefung")

        rows = result.get("value", [])
        if not rows:
            return None

        # GUID aus OData-Metadaten oder Feld-Namen extrahieren
        row = rows[0]
        for k, v in row.items():
            if not k.startswith("@") and isinstance(v, str) and len(v) == 36 and v.count("-") == 4:
                return v
        return "__exists__"

    def create_record(self, data: dict) -> str:
        """
        Erstellt neuen Datensatz.
        Gibt GUID des neuen Datensatzes zurueck.
        """
        url = self._api_url(self.table_name)
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                location = resp.headers.get("OData-EntityId", "")
                # Location: .../Entity(guid)
                if "(" in location and location.endswith(")"):
                    return location.split("(")[-1].rstrip(")")
                return location
        except urllib.error.HTTPError as e:
            body_raw = ""
            try:
                body_raw = e.read().decode("utf-8")
            except Exception:
                pass
            raise DataverseAPIError(e.code, e.reason or "Fehler beim Erstellen", body_raw)

    def update_record(self, record_id: str, data: dict) -> None:
        """
        Aktualisiert einen bestehenden Datensatz (PATCH).
        record_id: GUID des Datensatzes.
        """
        url = self._api_url(f"{self.table_name}({record_id})")
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = dict(self._headers())
        headers["If-Match"] = "*"
        req = urllib.request.Request(
            url, data=body, headers=headers, method="PATCH"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                pass
        except urllib.error.HTTPError as e:
            body_raw = ""
            try:
                body_raw = e.read().decode("utf-8")
            except Exception:
                pass
            raise DataverseAPIError(e.code, e.reason or "Fehler beim Update", body_raw)

    def upsert_record(self, dedup_value: str, data: dict,
                      dedup_field: str = "") -> dict:
        """
        Insert-or-Update mit Duplikatpruefung.

        Ablauf:
          1. Pruefe ob Datensatz mit dedup_field=dedup_value existiert
          2. Wenn JA  --> PATCH (update)
          3. Wenn NEIN --> POST (create)

        Args:
            dedup_value:  Wert des Prueffeldes (z.B. "Ankerkonen - Grobkosmetik")
            data:         Felder des Datensatzes (dict)
            dedup_field:  Spaltenname -- Fallback auf self.dedup_field

        Returns:
            {"action": "created"|"updated"|"skipped", "id": "..."}
        """
        field = dedup_field or self.dedup_field
        if not field:
            # Kein Prueffeld konfiguriert -> direkt erstellen
            new_id = self.create_record(data)
            return {"action": "created", "id": new_id}

        existing_id = self.record_exists(field, dedup_value)

        if existing_id and existing_id != "__exists__":
            self.update_record(existing_id, data)
            return {"action": "updated", "id": existing_id}
        elif existing_id == "__exists__":
            # Gefunden aber keine GUID extrahierbar -> sicherheitshalber ueberspringen
            return {"action": "skipped", "id": "__exists__"}
        else:
            new_id = self.create_record(data)
            return {"action": "created", "id": new_id}


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def get_client(config: dict) -> DataverseClient:
    """
    Erstellt DataverseClient aus config.json["lexware"].

    Raises DataverseAuthError wenn Credentials fehlen.
    """
    lex = config.get("lexware", {})
    return DataverseClient(
        tenant_id=lex.get("dataverse_tenant_id", "").strip(),
        client_id=lex.get("dataverse_client_id", "").strip(),
        client_secret=lex.get("dataverse_client_secret", "").strip(),
        org_url=lex.get("dataverse_org_url", "").strip(),
        table_name=lex.get("dataverse_table_name", "").strip(),
        dedup_field=lex.get("dataverse_dedup_field", "").strip(),
    )


def is_configured(config: dict) -> bool:
    """Prueft ob Dataverse vollstaendig konfiguriert ist."""
    lex = config.get("lexware", {})
    required = ["dataverse_tenant_id", "dataverse_client_id",
                "dataverse_client_secret", "dataverse_org_url"]
    return all(lex.get(k, "").strip() for k in required)
