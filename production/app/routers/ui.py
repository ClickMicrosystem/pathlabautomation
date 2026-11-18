from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.services.database import (
    create_connection,
    delete_connection,
    delete_test_mapping,
    get_connection,
    list_connections,
    load_lab_test_master,
    load_machine_test_master,
    load_machines,
    load_test_mappings,
    load_users,
    save_catalog_rows,
    save_test_mapping,
    set_connection_enabled,
    test_mapping_exists,
    upsert_machine,
    upsert_user,
    get_or_create_lab_test,
    seed_default_test_mappings,
)
from app.services.excel_catalog import load_catalog
from app.services.astm_sender import push_astm_order
from app.services.serial_listener import list_available_ports
from app.services.piysan_service import get_current_lab_name

router = APIRouter(tags=["ui"])
BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

DEMO_USER = os.environ.get("ADMIN_USERNAME", "admin")
DEMO_PASS = os.environ.get("ADMIN_PASSWORD", "admin123")


def get_local_ip() -> str:
    """Dynamically determine the host computer's primary LAN IPv4 address."""
    env_ip = os.getenv("COMPUTER_IP", "").strip()
    if env_ip:
        return env_ip
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        import socket
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


DEFAULT_MACHINE_IP = os.getenv("MACHINE_IP", "192.168.1.55")
DEFAULT_MACHINE_PORT = os.getenv("MACHINE_PORT", "5000")
COMPUTER_SUBNET_MASK = os.getenv("SUBNET_MASK", "255.255.255.0")
DEFAULT_MACHINE_SUBNET_MASK = os.getenv("SUBNET_MASK", "255.255.255.0")


def _authed(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def _ensure_catalog() -> None:
    catalog = load_catalog()
    if catalog["sheet2"]:
        machine_rows = []
        for row in catalog["sheet2"]:
            machine_rows.append({
                "machine_id": 1,
                "test_id": row["test_id"],
                "test_type": row["test_type"],
                "category": row["category"],
                "test_name": row["test_name"],
            })
        save_catalog_rows(machine_rows, "machine")
    if catalog["sheet1"]:
        save_catalog_rows(catalog["sheet1"], "lab")


def _as_lab_options(rows):
    return [
        {"value": str(row["id"]), "label": f'{row["test_id"]} - {row.get("test_name", "")}'}
        for row in rows
        if row.get("id")
    ]


def _as_machine_options(rows):
    return [
        {"value": str(row["id"]), "label": f'{row["test_id"]} - {row.get("test_name", "")}'}
        for row in rows
        if row.get("id")
    ]


@router.get("/", include_in_schema=False)
async def root(request: Request):
    if _authed(request):
        return RedirectResponse("/mapping", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": None, "username": DEMO_USER})


@router.post("/login", include_in_schema=False)
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    # 1. Fallback / local admin bypass
    if username == DEMO_USER and password == DEMO_PASS:
        request.session["authenticated"] = True
        request.session["username"] = username
        return JSONResponse({"status": "success", "redirect": "/dashboard"})

    # 2. Try Piysan LIS credentials
    try:
        from app.services.piysan_service import get_piysan_settings, get_piysan_base_url, update_piysan_settings, update_piysan_token, PiysanClient
        from datetime import datetime, timezone, timedelta

        settings = get_piysan_settings()
        base_url = get_piysan_base_url()

        # Authenticate via client
        client_api = PiysanClient(base_url, username, password)
        token = client_api.login()

        # Update saved settings and cache token
        auto_submit = settings.get("auto_submit", 1)
        update_piysan_settings(username, password, auto_submit)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).replace(tzinfo=None).isoformat()
        update_piysan_token(token, expires_at)

        request.session["authenticated"] = True
        request.session["username"] = username
        return JSONResponse({"status": "success", "redirect": "/dashboard"})
    except Exception as e:
        from app.utils.logger import get_logger
        get_logger(__name__).warning("Authentication failed: %s", e)
        return JSONResponse({"status": "error", "message": f"Authentication failed: {e}"}, status_code=401)


@router.get("/logout", include_in_schema=False)
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)
    _ensure_catalog()
    lab_name = get_current_lab_name()
    users = load_users()
    if not users:
        user_id = upsert_user(lab_name)
        users = [{"id": user_id, "user_name": lab_name}]
    user = users[0]
    machines = load_machines(user["id"])
    if not machines:
        upsert_machine(user["id"], "HORIBA Yumizen H500")
        machines = load_machines(user["id"])
    if machines:
        seed_default_test_mappings(user["id"], machines[0]["id"])
    machine_test_count = sum(len(load_test_mappings(user["id"], machine["id"])) for machine in machines)

    from app.services.piysan_service import load_enriched_bookings, get_piysan_settings
    bookings = load_enriched_bookings()
    settings = get_piysan_settings()

    connection_status = {s["id"]: s["running"] for s in request.app.state.connection_manager.status()}
    connections = [
        {**c, "running": connection_status.get(c["id"], False)}
        for c in list_connections()
    ]

    total_orders = len(bookings)
    pending_count = sum(1 for b in bookings if not b.get("has_match") and not b.get("is_skipped"))
    decoded_count = sum(1 for b in bookings if b.get("has_match") and not b.get("is_skipped"))
    submitted_count = sum(1 for b in bookings if b.get("last_status") == "success")
    skipped_count = sum(1 for b in bookings if b.get("is_skipped"))

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "username": request.session.get("username", DEMO_USER),
            "user_name": lab_name,
            "address": os.getenv("LAB_ADDRESS", "Main Laboratory Facility"),
            "contact": os.getenv("LAB_CONTACT", ""),
            "machines": machines,
            "machine_ip": DEFAULT_MACHINE_IP,
            "machine_subnet_mask": DEFAULT_MACHINE_SUBNET_MASK,
            "machine_port": DEFAULT_MACHINE_PORT,
            "computer_ip": get_local_ip(),
            "computer_subnet_mask": COMPUTER_SUBNET_MASK,
            "test_count": machine_test_count,
            "bookings": bookings,
            "settings": settings,
            "connections": connections,
            "total_orders": total_orders,
            "pending_count": pending_count,
            "decoded_count": decoded_count,
            "submitted_count": submitted_count,
            "skipped_count": skipped_count,
        },
    )


@router.post("/connections", include_in_schema=False)
async def add_connection(
    request: Request,
    label: str = Form(...),
    connection_type: str = Form(...),
    tcp_port: int = Form(None),
    com_port: str = Form(None),
    baud_rate: int = Form(None),
):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    if connection_type not in ("network", "serial"):
        return RedirectResponse("/dashboard?error=Invalid+connection+type", status_code=302)

    create_connection(
        label=label.strip() or ("Network Connection" if connection_type == "network" else "USB Connection"),
        connection_type=connection_type,
        tcp_port=tcp_port if connection_type == "network" else None,
        com_port=com_port if connection_type == "serial" else None,
        baud_rate=baud_rate if connection_type == "serial" else None,
    )
    request.app.state.connection_manager.sync_from_db()
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/connections/{connection_id}/toggle", include_in_schema=False)
async def toggle_connection(connection_id: int, request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    row = get_connection(connection_id)
    if row:
        set_connection_enabled(connection_id, not row["enabled"])
        request.app.state.connection_manager.sync_from_db()
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/connections/{connection_id}/delete", include_in_schema=False)
async def remove_connection(connection_id: int, request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    delete_connection(connection_id)
    request.app.state.connection_manager.sync_from_db()
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/connections/available-ports", include_in_schema=False)
async def available_ports(request: Request):
    if not _authed(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return JSONResponse(list_available_ports())


@router.get("/mapping", response_class=HTMLResponse, include_in_schema=False)
async def mapping_page(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)
    _ensure_catalog()
    lab_name = get_current_lab_name()
    users = load_users()
    if not users:
        user_id = upsert_user(lab_name)
        users = [{"id": user_id, "user_name": lab_name}]
    user = users[0]
    machines = load_machines(user["id"])
    if not machines:
        upsert_machine(user["id"], "HORIBA Yumizen H500")
        machines = load_machines(user["id"])
    requested_machine_id = request.query_params.get("machine_id")
    machine = next((m for m in machines if str(m["id"]) == str(requested_machine_id)), machines[0] if machines else None)
    if machine:
        seed_default_test_mappings(user["id"], machine["id"])
    catalog = load_catalog()
    machine_rows = []
    if machine:
        for row in catalog["sheet2"]:
            machine_rows.append({
                "machine_id": machine["id"],
                "test_id": row["test_id"],
                "test_type": row["test_type"],
                "category": row["category"],
                "test_name": row["test_name"],
            })
        if machine_rows:
            save_catalog_rows(machine_rows, "machine")
    if catalog["sheet1"]:
        save_catalog_rows(catalog["sheet1"], "lab")
    lab_tests = load_lab_test_master() or catalog["sheet1"]
    machine_tests = load_machine_test_master(user["id"], machine["id"]) if machine else catalog["sheet2"]
    saved_mappings = load_test_mappings(user["id"], machine["id"]) if machine else []
    mapping_rows = [
        {
            **row,
            "row_no": index + 1,
            "mapping_type": "Analyzer -> Lab",
            "final_json_field": row["lab_test_id"],
        }
        for index, row in enumerate(saved_mappings)
    ]
    return templates.TemplateResponse(
        request=request,
        name="mapping.html",
        context={
            "request": request,
            "username": request.session.get("username", DEMO_USER),
            "customer_name": lab_name,
            "user": user,
            "machines": machines,
            "active_machine": machine,
            "lab_tests": lab_tests,
            "machine_tests": machine_tests,
            "saved_mappings": saved_mappings,
            "mapping_rows": mapping_rows,
            "lab_options": _as_lab_options(lab_tests),
            "device_options": _as_machine_options(machine_tests),
            "saved": request.query_params.get("saved") == "1",
            "duplicate": request.query_params.get("duplicate") == "1",
        },
    )


@router.post("/mapping/select-machine", include_in_schema=False)
async def select_machine(machine_id: int = Form(...)):
    return RedirectResponse(f"/mapping?machine_id={machine_id}", status_code=302)


@router.post("/mapping/map", include_in_schema=False)
async def map_test(request: Request, user_id: int = Form(...), machine_id: int = Form(...), machine_test_master_id: int = Form(...), lab_test_id: str = Form(...)):
    lab_test_master_id = get_or_create_lab_test(lab_test_id)
    if test_mapping_exists(user_id, machine_id, machine_test_master_id):
        return RedirectResponse(f"/mapping?machine_id={machine_id}&duplicate=1", status_code=302)
    save_test_mapping(user_id, machine_id, machine_test_master_id, lab_test_master_id)
    return RedirectResponse(f"/mapping?machine_id={machine_id}&saved=1", status_code=302)


@router.post("/mapping/delete", include_in_schema=False)
async def delete_mapping(request: Request, mapping_id: int = Form(...), machine_id: int = Form(...)):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)
    delete_test_mapping(mapping_id)
    return RedirectResponse(f"/mapping?machine_id={machine_id}&saved=1", status_code=302)


@router.get("/push-command", response_class=HTMLResponse, include_in_schema=False)
async def push_command_page(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    catalog = load_catalog()
    machine_options = [
        {"value": row["test_id"], "label": f'{row["test_id"]} - {row.get("test_name", "")}'}
        for row in catalog.get("sheet1", [])
    ]

    from app.services.piysan_service import load_enriched_bookings
    piysan_bookings = load_enriched_bookings()

    connection_status = {s["id"]: s["running"] for s in request.app.state.connection_manager.status()}
    connections = [
        {**c, "running": connection_status.get(c["id"], False)}
        for c in list_connections()
        if c["enabled"]
    ]

    # Extract query parameters for pre-filling
    sample_id = request.query_params.get("sample_id", "")
    patient_id = request.query_params.get("patient_id", "")
    patient_name = request.query_params.get("patient_name", "")
    dob = request.query_params.get("dob", "")
    gender = request.query_params.get("gender", "")
    
    if dob:
        dob = dob.replace("-", "").replace("/", "").split(" ")[0].strip()
        
    # Map Piysan Test IDs to Machine Test IDs if passed
    preselected_tests = []
    piysan_test_ids_str = request.query_params.get("test_ids", "")
    if piysan_test_ids_str:
        piysan_test_ids = [t.strip() for t in piysan_test_ids_str.split(",") if t.strip()]
        
        # Load reverse mapping lookup
        from app.services.database import load_latest_installation_mapping_lookup
        mapping_lookup = load_latest_installation_mapping_lookup()
        reverse_lookup = {lab_id: mach_id for mach_id, lab_id in mapping_lookup.items() if lab_id and mach_id}
        
        for tid in piysan_test_ids:
            # Map back to machine code or default to tid
            preselected_tests.append(reverse_lookup.get(tid, tid))
            
    return templates.TemplateResponse(
        request=request,
        name="push_command.html",
        context={
            "request": request,
            "username": request.session.get("username", DEMO_USER),
            "user_name": get_current_lab_name(),
            "connections": connections,
            "result_log": None,
            "machine_options": machine_options,
            "piysan_bookings": piysan_bookings,
            "sync": request.query_params.get("sync") == "1",
            "error": request.query_params.get("error"),
            "prefill": {
                "sample_id": sample_id,
                "patient_id": patient_id,
                "patient_name": patient_name,
                "dob": dob,
                "gender": gender.upper() if gender else "",
                "test_ids": preselected_tests
            }
        }
    )

@router.post("/push-command/execute", response_class=HTMLResponse, include_in_schema=False)
async def execute_push_command(
    request: Request,
    connection_id: int = Form(...),
    sample_id: str = Form(...),
    patient_id: str = Form(...),
    patient_name: str = Form(""),
    dob: str = Form(""),
    gender: str = Form(""),
    test_ids: list[str] = Form(...)
):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    # Map selected Lab Test IDs to Machine Test IDs using configured mappings
    from app.services.database import load_latest_installation_mapping_lookup
    mapping_lookup = load_latest_installation_mapping_lookup()
    reverse_lookup = {lab_id: mach_id for mach_id, lab_id in mapping_lookup.items() if lab_id and mach_id}

    mapped_test_ids = [reverse_lookup.get(tid, tid) for tid in test_ids]

    listener = request.app.state.connection_manager.get(connection_id)
    result_log = push_astm_order(listener, sample_id, patient_id, mapped_test_ids, patient_name, dob, gender)

    catalog = load_catalog()
    machine_options = [
        {"value": row["test_id"], "label": f'{row["test_id"]} - {row.get("test_name", "")}'}
        for row in catalog.get("sheet1", [])
    ]

    from app.services.piysan_service import load_enriched_bookings
    piysan_bookings = load_enriched_bookings()

    connection_status = {s["id"]: s["running"] for s in request.app.state.connection_manager.status()}
    connections = [
        {**c, "running": connection_status.get(c["id"], False)}
        for c in list_connections()
        if c["enabled"]
    ]

    return templates.TemplateResponse(
        request=request,
        name="push_command.html",
        context={
            "request": request,
            "username": request.session.get("username", DEMO_USER),
            "connections": connections,
            "selected_connection_id": connection_id,
            "result_log": result_log,
            "machine_options": machine_options,
            "piysan_bookings": piysan_bookings,
            "prefill": {
                "sample_id": sample_id,
                "patient_id": patient_id,
                "patient_name": patient_name,
                "dob": dob,
                "gender": gender.upper() if gender else "",
                "test_ids": test_ids,
            },
        }
    )


@router.post("/push-command/quick-push")
async def quick_push_order(request: Request):
    """AJAX endpoint to quickly push an order to the connected analyzer."""
    if not _authed(request):
        return JSONResponse({"status": "error", "message": "Not authenticated"}, status_code=401)
    try:
        data = await request.json()
    except Exception:
        data = {}

    sample_id = data.get("sample_id", "")
    patient_id = data.get("patient_id", "")
    patient_name = data.get("patient_name", "")
    dob = data.get("dob", "")
    gender = data.get("gender", "")
    test_ids = data.get("test_ids", [])
    if isinstance(test_ids, str):
        test_ids = [t.strip() for t in test_ids.split(",") if t.strip()]

    if dob:
        dob = dob.replace("-", "").replace("/", "").split(" ")[0].strip()

    from app.services.database import load_latest_installation_mapping_lookup
    mapping_lookup = load_latest_installation_mapping_lookup()
    reverse_lookup = {lab_id: mach_id for mach_id, lab_id in mapping_lookup.items() if lab_id and mach_id}
    mapped_test_ids = [reverse_lookup.get(tid, tid) for tid in test_ids]

    listener = request.app.state.connection_manager.first_running()
    result_log = push_astm_order(listener, sample_id, patient_id, mapped_test_ids, patient_name, dob, gender)
    is_error = "Error:" in result_log or "error" in result_log.lower()

    return JSONResponse({
        "status": "error" if is_error else "success",
        "message": result_log,
    })

