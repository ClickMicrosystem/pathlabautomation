"""Piysan LIS Integration Service.

Manages integration settings, cached bookings, submission logs, and HTTP communication
with the Piysan LIS production API endpoints.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
import httpx

from app.services.database import _connect, _lock, MAPPING_DB_PATH, DECODED_DB_PATH

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PIYSAN_BASE_URL = "https://www.piysan.com/"

DEFAULT_CBC_MACHINE_TO_LAB_MAP: Dict[str, str] = {
    # Short names
    "HGB": "1",
    "RBC": "2",
    "PLT": "3",
    "WBC": "4",
    "NEU%": "5",
    "NEU#": "5",
    "LYM%": "6",
    "LYM#": "6",
    "MON%": "7",
    "MON#": "7",
    "EOS%": "8",
    "EOS#": "8",
    "BAS%": "9",
    "BAS#": "9",
    "HCT": "15",
    "RDW-CV": "19",
    "RDW-SD": "20",
    "MPV": "21",
    "P-LCR": "24",
    "P-LCC": "25",
    "PDW": "431",
    "PCT": "534",
    # LOINC codes
    "718-7": "1",
    "789-8": "2",
    "777-3": "3",
    "6690-2": "4",
    "770-8": "5",
    "751-8": "5",
    "736-9": "6",
    "731-0": "6",
    "5905-5": "7",
    "742-7": "7",
    "713-8": "8",
    "711-2": "8",
    "706-2": "9",
    "704-7": "9",
    "4544-3": "15",
    "788-0": "19",
    "21000-5": "20",
    "32623-1": "21",
    "48386-7": "24",
    "96354-6": "25",
    "51631-0": "431",
    "51637-7": "534",
}


def _resolve_result_test_id(code: str, result_entry: Dict[str, Any], booking: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Resolve a raw analyzer/test code to a valid numeric Piysan test_id string."""
    # 1. If code is already a numeric string (e.g. "1", "4", "15")
    if str(code).isdigit():
        return str(code)

    # 2. Check lab_test_code in result_entry if set during report generation
    lab_code = result_entry.get("lab_test_code")
    if lab_code and str(lab_code).isdigit():
        return str(lab_code)

    dev_code = result_entry.get("device_test_code")

    # 3. Check active database mapping lookup
    try:
        from app.services.database import load_latest_installation_mapping_lookup
        mapping_lookup = load_latest_installation_mapping_lookup()
        for c in (code, dev_code):
            if c:
                db_tid = mapping_lookup.get(c)
                if db_tid and str(db_tid).isdigit():
                    return str(db_tid)
    except Exception:
        pass

    # 4. Standard HORIBA CBC code fallback map
    for c in (code, dev_code):
        if c:
            fallback = DEFAULT_CBC_MACHINE_TO_LAB_MAP.get(str(c).upper())
            if fallback:
                return str(fallback)

    # 5. Check test_name against booking machine tests
    if booking:
        t_name = (result_entry.get("test_name") or "").lower().strip()
        if t_name:
            for m in booking.get("machines", []):
                for t in m.get("tests", []):
                    bt_name = (t.get("test_name") or "").lower().strip()
                    bt_id = str(t.get("test_id") or "")
                    if bt_id.isdigit() and (t_name == bt_name or t_name in bt_name or bt_name in t_name):
                        return bt_id

    return None


def get_piysan_base_url() -> str:
    """Return the Piysan LIS base URL, sourced from the PIYSAN_BASE_URL env var.

    The base URL is intentionally NOT stored/read from the database anymore -
    it is controlled via environment configuration (.env / OS env var) so it
    can be switched between staging/production without touching the DB.
    """
    return os.getenv("PIYSAN_BASE_URL", DEFAULT_PIYSAN_BASE_URL).strip()


class PiysanClient:
    """HTTP client wrapper for the Piysan LIS APIs."""

    def __init__(self, base_url: str, mobile: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.mobile = mobile
        self.password = password

    def login(self) -> str:
        """Authenticate with the Piysan LIS server and return a JWT access token."""
        url = f"{self.base_url}/api/lis/login"
        payload = {
            "mobile": self.mobile,
            "password": self.password,
        }
        logger.info("Sending login request to Piysan LIS at %s", url)
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.error("Piysan LIS login failed (%s): %s", resp.status_code, resp.text)
                    resp.raise_for_status()
                data = resp.json()
                self.last_lab_info = data.get("lab") or {}
                
                # Robust extraction check for the token
                token = (
                    data.get("token")
                    or data.get("access_token")
                    or data.get("jwt")
                    or data.get("data", {}).get("token")
                )
                if not token:
                    raise ValueError(f"Could not locate JWT token in API response: {data}")
                return str(token)
        except Exception as e:
            logger.exception("Piysan LIS login API request failed")
            raise

    def get_bookings(self, token: str, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieve booking assignments assigned to this laboratory from Piysan.
        Paginates until all available bookings are retrieved."""
        url = f"{self.base_url}/api/lis/get_bookings"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        all_bookings: List[Dict[str, Any]] = []
        current_offset = offset
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            while True:
                params = {
                    "limit": limit,
                    "offset": current_offset,
                }
                logger.info("Fetching bookings from Piysan LIS at %s (limit=%s, offset=%s)", url, limit, current_offset)
                resp = client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

                batch = []
                total = 0
                page_limit = limit
                if isinstance(data, list):
                    batch = data
                elif isinstance(data, dict):
                    total = int(data.get("total") or 0)
                    page_limit = int(data.get("limit") or limit)
                    batch = data.get("bookings") or data.get("data") or data.get("results") or []
                    if not isinstance(batch, list):
                        batch = [data]

                if not batch:
                    break

                all_bookings.extend(batch)

                if total > 0:
                    # Piysan's SQL pagination applies LIMIT/OFFSET to raw test rows before
                    # grouping them into booking objects, so len(batch) is smaller than limit.
                    # Advance by the server's page_limit until we pass total.
                    step = page_limit if page_limit > 0 else limit
                    if step <= 0:
                        break
                    current_offset += step
                    if current_offset >= total:
                        break
                else:
                    current_offset += len(batch)
                    if len(batch) < limit:
                        break

        return all_bookings

    def submit_report(self, token: str, reference_no: str, results: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Transmit laboratory test numeric results to Piysan LIS."""
        url = f"{self.base_url}/api/lis/submit_report"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # Piysan /api/lis/submit_report expects results to be a dictionary mapping {test_id: value}
        if isinstance(results, dict):
            formatted_results = results
        elif isinstance(results, list):
            formatted_results = {}
            for item in results:
                if isinstance(item, dict):
                    t_id = item.get("test_id")
                    val = item.get("value")
                    if t_id is not None and val is not None:
                        formatted_results[str(t_id)] = val
        else:
            formatted_results = {}

        payload = {
            "reference_no": reference_no,
            "results": formatted_results,
        }
        logger.info("Submitting report to Piysan LIS at %s for reference_no=%s: %s", url, reference_no, payload)
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                error_msg = f"HTTP {resp.status_code}"
                try:
                    err_json = resp.json()
                    if isinstance(err_json, dict) and err_json.get("message"):
                        error_msg = err_json.get("message")
                        if err_json.get("invalid_test_ids"):
                            error_msg += f" (invalid test IDs: {err_json.get('invalid_test_ids')})"
                    elif isinstance(err_json, dict) and err_json.get("error"):
                        error_msg = str(err_json.get("error"))
                except Exception:
                    error_msg = f"HTTP {resp.status_code}: {resp.text}"
                logger.error("Piysan submit_report failed (%s): %s", resp.status_code, error_msg)
                raise ValueError(f"Piysan LIS error: {error_msg}")
            return resp.json()


def init_piysan_db() -> None:
    """Initialize Piysan LIS configuration, booking, and submission tables."""
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS piysan_settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                base_url TEXT NOT NULL DEFAULT 'https://www.piysan.com/',
                mobile TEXT,
                password TEXT,
                jwt_token TEXT,
                token_expires_at TEXT,
                auto_submit INTEGER DEFAULT 1,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS piysan_bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_no TEXT UNIQUE,
                patient_name TEXT,
                patient_id TEXT,
                raw_data TEXT,
                is_skipped INTEGER DEFAULT 0,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            conn.execute("ALTER TABLE piysan_bookings ADD COLUMN is_skipped INTEGER DEFAULT 0")
        except Exception:
            pass
        for col in ["lab_name TEXT", "brand_name TEXT", "lab_email TEXT"]:
            try:
                conn.execute(f"ALTER TABLE piysan_settings ADD COLUMN {col}")
            except Exception:
                pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS piysan_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_no TEXT,
                raw_capture_id INTEGER,
                payload TEXT,
                response TEXT,
                status TEXT,
                error_message TEXT,
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Seed initial setting row
        conn.execute(
            """
            INSERT OR IGNORE INTO piysan_settings (id, base_url, mobile, password, jwt_token, token_expires_at, auto_submit)
            VALUES (1, 'https://www.piysan.com/', '', '', NULL, NULL, 1)
            """
        )
        conn.commit()


def get_piysan_settings() -> Dict[str, Any]:
    """Retrieve settings for Piysan integration."""
    init_piysan_db()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        row = conn.execute("SELECT * FROM piysan_settings WHERE id = 1").fetchone()
        return dict(row) if row else {}


def update_piysan_settings(mobile: str, password: str, auto_submit: int) -> None:
    """Save credential/auto-submit settings. base_url is env-controlled (PIYSAN_BASE_URL),
    not editable here - the DB column is kept in sync purely for display/history purposes."""
    init_piysan_db()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE piysan_settings
            SET base_url = ?, mobile = ?, password = ?, auto_submit = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (get_piysan_base_url(), mobile, password, auto_submit),
        )
        conn.commit()


def update_piysan_token(token: str, expires_at: str, lab_info: Optional[Dict[str, Any]] = None) -> None:
    """Cache the authenticated JWT access token and laboratory profile."""
    init_piysan_db()
    lab_name = (lab_info or {}).get("lab_name") if lab_info else None
    brand_name = (lab_info or {}).get("brand_name") if lab_info else None
    lab_email = (lab_info or {}).get("email") if lab_info else None
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE piysan_settings
            SET jwt_token = ?, token_expires_at = ?,
                lab_name = COALESCE(?, lab_name),
                brand_name = COALESCE(?, brand_name),
                lab_email = COALESCE(?, lab_email),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (token, expires_at, lab_name, brand_name, lab_email),
        )
        effective_name = brand_name or lab_name
        if effective_name:
            try:
                conn.execute(
                    """
                    UPDATE users SET user_name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1
                    """,
                    (effective_name,),
                )
            except Exception:
                pass
        conn.commit()


def get_current_lab_name() -> str:
    """Return the display name of the current laboratory."""
    try:
        settings = get_piysan_settings()
        brand = (settings.get("brand_name") or "").strip()
        lab = (settings.get("lab_name") or "").strip()
        if brand and lab and brand != lab:
            return f"{brand} ({lab})"
        if brand:
            return brand
        if lab:
            return lab
    except Exception:
        pass

    env_name = os.getenv("LAB_NAME", "").strip()
    if env_name:
        return env_name

    try:
        from app.services.database import load_users
        users = load_users()
        if users and users[0].get("user_name"):
            name = users[0]["user_name"].strip()
            if name and name.lower() not in ("sk lab", "sk_lab", "acme diagnostics"):
                return name
    except Exception:
        pass

    return "Clinical Pathology Laboratory"


def execute_piysan_request(func_name: str, *args, **kwargs) -> Any:
    """Safely executes a Piysan client command, handling token loading, renewal, and HTTP 401 retries."""
    settings = get_piysan_settings()
    if not settings or not settings.get("mobile") or not settings.get("password"):
        raise ValueError("Piysan integration is not configured. Please fill in mobile and password credentials.")

    base_url = get_piysan_base_url()
    client = PiysanClient(base_url, settings["mobile"], settings["password"])

    if func_name == "login":
        # Force a live login call (e.g. for "Test Connection") - bypass token cache entirely.
        token = client.login()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).replace(tzinfo=None).isoformat()
        update_piysan_token(token, expires_at, getattr(client, "last_lab_info", None))
        return token

    # Resolve token cache validation
    token = settings.get("jwt_token")
    expires_at_str = settings.get("token_expires_at")
    token_needs_refresh = True

    if token and expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            # Require at least 5 minutes of valid lifetime remaining
            if expires_at > datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5):
                token_needs_refresh = False
        except Exception:
            pass

    if token_needs_refresh:
        logger.info("Piysan token is expired or missing. Fetching new token...")
        token = client.login()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).replace(tzinfo=None).isoformat()
        update_piysan_token(token, expires_at, getattr(client, "last_lab_info", None))

    api_func = getattr(client, func_name)
    try:
        return api_func(token, *args, **kwargs)
    except httpx.HTTPStatusError as e:
        # Self-healing on 401 Unauthorized token expirations
        if e.response.status_code == 401:
            logger.warning("Piysan request failed with 401. Retrying with a fresh token...")
            token = client.login()
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).replace(tzinfo=None).isoformat()
            update_piysan_token(token, expires_at, getattr(client, "last_lab_info", None))
            return api_func(token, *args, **kwargs)
        raise


def _merge_booking_data(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge machine and test lists across multiple booking records for the same reference_no."""
    merged = dict(existing)
    if not merged.get("patient") and incoming.get("patient"):
        merged["patient"] = incoming["patient"]
    if incoming.get("created_on"):
        merged["created_on"] = incoming["created_on"]

    existing_machines = list(merged.get("machines") or [])
    incoming_machines = incoming.get("machines") or []

    machines_by_id = {m.get("machine_id"): m for m in existing_machines if isinstance(m, dict)}
    for im in incoming_machines:
        if not isinstance(im, dict):
            continue
        mid = im.get("machine_id")
        if mid in machines_by_id:
            em = machines_by_id[mid]
            existing_tests = list(em.get("tests") or [])
            incoming_tests = im.get("tests") or []
            existing_tids = {str(t.get("test_id")) for t in existing_tests if isinstance(t, dict)}
            for it in incoming_tests:
                if isinstance(it, dict) and str(it.get("test_id")) not in existing_tids:
                    existing_tests.append(it)
                    existing_tids.add(str(it.get("test_id")))
            em["tests"] = existing_tests
        else:
            existing_machines.append(im)
            machines_by_id[mid] = im

    merged["machines"] = existing_machines
    return merged


def save_piysan_bookings(bookings: List[Dict[str, Any]]) -> None:
    """Persist fetched bookings and auto-import master tests into the lab catalog."""
    init_piysan_db()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        for b in bookings:
            ref_no = b.get("reference_no")
            if not ref_no:
                continue

            patient_name = ""
            patient_id = ""

            patient_info = b.get("patient")
            if isinstance(patient_info, dict):
                full_name = " ".join(
                    part for part in [patient_info.get("first_name"), patient_info.get("last_name")] if part
                ).strip()
                patient_name = full_name or patient_info.get("name") or patient_info.get("patient_name") or ""
                patient_id = (
                    patient_info.get("id")
                    or patient_info.get("patient_id")
                    or patient_info.get("mobile")
                    or ""
                )
            elif isinstance(patient_info, str):
                patient_name = patient_info

            # Check if this booking already exists in DB so we can merge machines/tests
            existing_row = conn.execute(
                "SELECT raw_data FROM piysan_bookings WHERE reference_no = ?", (ref_no,)
            ).fetchone()
            if existing_row and existing_row["raw_data"]:
                try:
                    existing_data = json.loads(existing_row["raw_data"])
                    b_to_save = _merge_booking_data(existing_data, b)
                except Exception:
                    b_to_save = b
            else:
                b_to_save = b

            conn.execute(
                """
                INSERT INTO piysan_bookings (reference_no, patient_name, patient_id, raw_data, fetched_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(reference_no)
                DO UPDATE SET patient_name = excluded.patient_name, patient_id = excluded.patient_id,
                              raw_data = excluded.raw_data, fetched_at = CURRENT_TIMESTAMP
                """,
                (ref_no, patient_name, patient_id, json.dumps(b_to_save, ensure_ascii=False)),
            )

            # Auto-import tests to lab_test_master so they populate the mappings list suggestions
            machines = b_to_save.get("machines") or []
            for m in machines:
                tests = m.get("tests") or []
                for t in tests:
                    t_id = t.get("test_id")
                    t_name = t.get("test_name") or ""
                    t_cat = t.get("test_category_name") or ""
                    if t_id:
                        conn.execute(
                            """
                            INSERT INTO lab_test_master (test_id, test_name, category, test_type)
                            VALUES (?, ?, ?, 'numeric')
                            ON CONFLICT(test_id) DO UPDATE SET
                                test_name = CASE WHEN excluded.test_name != '' THEN excluded.test_name ELSE lab_test_master.test_name END,
                                category = CASE WHEN excluded.category != '' THEN excluded.category ELSE lab_test_master.category END
                            """,
                            (str(t_id), t_name, t_cat),
                        )
        conn.commit()


def load_piysan_bookings() -> List[Dict[str, Any]]:
    """Load all locally cached bookings, sorted with the newest bookings at the top."""
    init_piysan_db()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        rows = conn.execute("SELECT * FROM piysan_bookings ORDER BY id DESC").fetchall()
        bookings = []
        for r in rows:
            b_dict = dict(r)
            try:
                b_dict["raw_data_parsed"] = json.loads(b_dict["raw_data"])
            except Exception:
                b_dict["raw_data_parsed"] = {}
            bookings.append(b_dict)

        # Sort so that the latest created bookings (e.g. 2026-09-03) appear at the top
        def _sort_key(item):
            parsed = item.get("raw_data_parsed", {})
            created = parsed.get("created_on") or item.get("fetched_at") or ""
            ref = item.get("reference_no") or ""
            return (created, ref)

        bookings.sort(key=_sort_key, reverse=True)
        return bookings


def save_submission_log(
    reference_no: str,
    raw_capture_id: Optional[int],
    payload: Dict[str, Any],
    response: Optional[Dict[str, Any]],
    status: str,
    error_message: str = "",
) -> None:
    """Record an entry in the submission history log."""
    init_piysan_db()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO piysan_submissions (reference_no, raw_capture_id, payload, response, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                reference_no,
                raw_capture_id,
                json.dumps(payload, ensure_ascii=False) if payload else None,
                json.dumps(response, ensure_ascii=False) if response else None,
                status,
                error_message,
            ),
        )
        conn.commit()


def load_submission_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Load the history logs."""
    init_piysan_db()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, reference_no, raw_capture_id, payload, response, status, error_message,
                   datetime(submitted_at, 'localtime') as submitted_at
            FROM piysan_submissions
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def toggle_skip_booking(reference_no: str, is_skipped: Optional[bool] = None) -> bool:
    """Toggle or explicitly set the skip status of a booking."""
    init_piysan_db()
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        row = conn.execute("SELECT is_skipped FROM piysan_bookings WHERE reference_no = ?", (reference_no,)).fetchone()
        if not row:
            return False
        current = bool(row["is_skipped"])
        new_val = (not current) if is_skipped is None else bool(is_skipped)
        conn.execute("UPDATE piysan_bookings SET is_skipped = ? WHERE reference_no = ?", (1 if new_val else 0, reference_no))
        conn.commit()
        return new_val


def find_latest_decoded_capture(sample_id: str) -> Optional[Dict[str, Any]]:
    """Search decoded_captures SQLite table to find the latest parsed report matching sample_id."""
    init_piysan_db()
    with _lock, _connect(DECODED_DB_PATH) as conn:
        rows = conn.execute("SELECT raw_capture_id, payload, decoded_at FROM decoded_captures ORDER BY id DESC").fetchall()
        for r in rows:
            try:
                payload = json.loads(r["payload"])
                order_id = payload.get("order", {}).get("sample_id")
                if order_id == sample_id:
                    return {
                        "raw_capture_id": r["raw_capture_id"],
                        "report": payload,
                        "decoded_at": r["decoded_at"] if "decoded_at" in r.keys() else "",
                    }
            except Exception:
                continue
    return None


def load_enriched_bookings() -> List[Dict[str, Any]]:
    """Retrieve cached bookings enriched with ASTM match results and submission logs."""
    bookings = load_piysan_bookings()
    enriched = []
    for b in bookings:
        ref_no = b["reference_no"]
        capture_data = find_latest_decoded_capture(ref_no)

        has_match = False
        match_capture_id = None
        match_results: List[Dict[str, Any]] = []

        if capture_data:
            has_match = True
            match_capture_id = capture_data["raw_capture_id"]
            report = capture_data["report"]
            booking_raw = b.get("raw_data_parsed")

            # The Piysan get_bookings API does not return a test_id per test (only
            # test_name), so we can't cross-check decoded results against the
            # booking's own tests by ID. Order-level match (same reference_no /
            # sample_id) is the check that matters - show every decoded numeric
            # result for this order.
            for test_key, result_entry in report.get("results", {}).items():
                try:
                    val = result_entry.get("value")
                    if val is not None:
                        val_float = float(val)
                        resolved_id = _resolve_result_test_id(str(test_key), result_entry, booking_raw)
                        display_id = int(resolved_id) if (resolved_id and resolved_id.isdigit()) else test_key
                        t_name = result_entry.get("test_name") or str(test_key)
                        match_results.append({
                            "test_id": display_id,
                            "test_name": t_name,
                            "value": val_float,
                            "unit": result_entry.get("unit") or "",
                            "flags": result_entry.get("flags") or [],
                            "reference_range": result_entry.get("reference_range") or {},
                        })
                except (ValueError, TypeError):
                    continue

        last_status = "Not Submitted"
        last_error = ""
        with _lock, _connect(MAPPING_DB_PATH) as conn:
            log_row = conn.execute(
                """
                SELECT status, error_message FROM piysan_submissions
                WHERE reference_no = ? ORDER BY id DESC LIMIT 1
                """,
                (ref_no,),
            ).fetchone()
            if log_row:
                last_status = log_row["status"]
                last_error = log_row["error_message"]

        # Collect patient parameters for pre-filling the push-command page
        booking_data = b.get("raw_data_parsed", {})
        test_ids_list = []
        for m in booking_data.get("machines", []):
            for t in m.get("tests", []):
                tid = t.get("test_id")
                if tid:
                    test_ids_list.append(str(tid))
        
        b_test_ids_str = ",".join(test_ids_list)
        b_dob = booking_data.get("patient", {}).get("dob") or ""
        b_gender = booking_data.get("patient", {}).get("gender") or ""

        decoded_at_val = capture_data.get("decoded_at", "") if capture_data else ""
        b_created_on = booking_data.get("created_on") or b.get("fetched_at") or ""

        enriched.append({
            **b,
            "created_on": b_created_on,
            "is_skipped": bool(b.get("is_skipped", 0)),
            "has_match": has_match,
            "match_capture_id": match_capture_id,
            "match_results": match_results,
            "decoded_at": decoded_at_val,
            "last_status": last_status,
            "last_error": last_error,
            "test_ids_str": b_test_ids_str,
            "dob_str": b_dob,
            "gender_str": b_gender,
        })
    enriched.sort(
        key=lambda x: (x.get("created_on") or "", x.get("reference_no") or ""),
        reverse=True,
    )
    return enriched


def trigger_auto_submit(raw_capture_id: int, report: Dict[str, Any]) -> None:
    """Evaluates settings and initiates result submission automatically if mapped."""
    settings = get_piysan_settings()
    if not settings or not settings.get("mobile") or not settings.get("password"):
        logger.info("Piysan integration is not configured. Skipping auto-submit.")
        return

    if not settings.get("auto_submit"):
        logger.info("Piysan auto-submit is disabled. Skipping auto-submit.")
        return

    reference_no = report.get("order", {}).get("sample_id")
    if not reference_no:
        logger.info("No sample ID in report. Skipping auto-submit.")
        return

    results_dict = report.get("results", {})
    if not results_dict:
        logger.info("No results found in report. Skipping auto-submit.")
        return

    # Check for cached booking or refresh
    booking = None
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        row = conn.execute("SELECT raw_data FROM piysan_bookings WHERE reference_no = ?", (reference_no,)).fetchone()
        if row:
            try:
                booking = json.loads(row["raw_data"])
            except Exception:
                pass

    if not booking:
        try:
            logger.info("Booking %s not found in cache. Synchronizing bookings...", reference_no)
            bookings = execute_piysan_request("get_bookings")
            save_piysan_bookings(bookings)

            with _lock, _connect(MAPPING_DB_PATH) as conn:
                row = conn.execute("SELECT raw_data FROM piysan_bookings WHERE reference_no = ?", (reference_no,)).fetchone()
                if row:
                    try:
                        booking = json.loads(row["raw_data"])
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Failed to sync bookings during auto-submit: %s", e)

    if not booking:
        logger.info("Booking %s could not be confirmed with Piysan. Skipping auto-submit.", reference_no)
        return

    # Resolve each test code to a verified numeric Piysan test_id before submitting.
    results_to_submit = {}
    for test_key, result_entry in results_dict.items():
        val = result_entry.get("value")
        if val is None:
            continue
        try:
            num_val = float(val)
        except (ValueError, TypeError):
            continue
        tid = _resolve_result_test_id(str(test_key), result_entry, booking)
        if tid and str(tid).isdigit():
            results_to_submit[str(tid)] = num_val
        else:
            logger.warning("Auto-submit: could not map test code '%s' to a numeric Piysan test_id for booking %s", test_key, reference_no)

    if not results_to_submit:
        logger.info("No valid mapped numeric results found for reference_no=%s. Skipping submit.", reference_no)
        return

    try:
        response = execute_piysan_request("submit_report", reference_no, results_to_submit)
        save_submission_log(
            reference_no,
            raw_capture_id,
            {"reference_no": reference_no, "results": results_to_submit},
            response,
            "success",
        )
        logger.info("Successfully auto-submitted results to Piysan for booking %s", reference_no)
    except Exception as e:
        error_msg = str(e)
        response_data = None
        if hasattr(e, "response") and e.response:
            try:
                response_data = e.response.json()
                error_msg = f"{e.response.status_code} - {e.response.text}"
            except Exception:
                error_msg = f"{e.response.status_code} - {e.response.text}"
        save_submission_log(
            reference_no,
            raw_capture_id,
            {"reference_no": reference_no, "results": results_to_submit},
            response_data,
            "failed",
            error_msg,
        )
        logger.exception("Failed to auto-submit results to Piysan LIS")


def manual_submit_to_piysan(reference_no: str) -> Dict[str, Any]:
    """Manually submit the latest decoded results matching reference_no."""
    capture_data = find_latest_decoded_capture(reference_no)
    if not capture_data:
        raise ValueError(f"No decoded results found in local database for order number: {reference_no}")

    raw_capture_id = capture_data["raw_capture_id"]
    report = capture_data["report"]

    # Confirm this order_no is a real booking received from Piysan for this lab.
    booking = None
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        row = conn.execute("SELECT raw_data FROM piysan_bookings WHERE reference_no = ?", (reference_no,)).fetchone()
        if row:
            try:
                booking = json.loads(row["raw_data"])
            except Exception:
                pass

    if not booking:
        raise ValueError(f"Order {reference_no} was not found among bookings received from Piysan. Fetch latest bookings and try again.")

    # Resolve each decoded test code to a verified numeric Piysan test_id before submitting.
    results_to_submit = {}
    unmapped_codes = []
    for test_key, result_entry in report.get("results", {}).items():
        val = result_entry.get("value")
        if val is None:
            continue
        try:
            num_val = float(val)
        except (ValueError, TypeError):
            continue
        tid = _resolve_result_test_id(str(test_key), result_entry, booking)
        if tid and str(tid).isdigit():
            results_to_submit[str(tid)] = num_val
        else:
            unmapped_codes.append(str(test_key))

    if not results_to_submit:
        detail = f" (unmapped codes: {', '.join(unmapped_codes)})" if unmapped_codes else ""
        raise ValueError(f"No mapped numeric test results found for reference_no: {reference_no}{detail}")

    try:
        response = execute_piysan_request("submit_report", reference_no, results_to_submit)
        save_submission_log(
            reference_no,
            raw_capture_id,
            {"reference_no": reference_no, "results": results_to_submit},
            response,
            "success",
        )
        return response
    except Exception as e:
        error_msg = str(e)
        response_data = None
        if hasattr(e, "response") and e.response:
            try:
                response_data = e.response.json()
                error_msg = f"{e.response.status_code} - {e.response.text}"
            except Exception:
                error_msg = f"{e.response.status_code} - {e.response.text}"
        save_submission_log(
            reference_no,
            raw_capture_id,
            {"reference_no": reference_no, "results": results_to_submit},
            response_data,
            "failed",
            error_msg,
        )
        raise
