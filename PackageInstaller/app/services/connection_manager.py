"""Owns one analyzer listener per configured `analyzer_connections` row, keeping
them in sync with the database and restarting any that have died."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.database import list_connections
from app.services.serial_listener import SerialAnalyzerListener
from app.services.socket_listener import AnalyzerListener, _BaseAnalyzerLink
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _build_listener(row: Dict[str, Any]) -> Optional[_BaseAnalyzerLink]:
    if row["connection_type"] == "network":
        return AnalyzerListener(host="0.0.0.0", port=int(row["tcp_port"]))
    if row["connection_type"] == "serial":
        if not row.get("com_port"):
            logger.warning("Serial connection id=%s has no com_port configured; skipping", row["id"])
            return None
        return SerialAnalyzerListener(com_port=row["com_port"], baud_rate=int(row["baud_rate"] or 9600))
    logger.error("Unknown connection_type=%r for connection id=%s", row["connection_type"], row["id"])
    return None


class ConnectionManager:
    def __init__(self):
        self.listeners: Dict[int, _BaseAnalyzerLink] = {}

    def sync_from_db(self) -> None:
        """(Re)build listeners to match the current DB rows: start enabled ones, stop/drop
        disabled or deleted ones, and restart any whose config changed."""
        rows = {row["id"]: row for row in list_connections()}

        for connection_id in list(self.listeners.keys()):
            row = rows.get(connection_id)
            if row is None or not row["enabled"]:
                self.listeners.pop(connection_id).stop()

        for connection_id, row in rows.items():
            if not row["enabled"]:
                continue
            if connection_id in self.listeners:
                continue
            listener = _build_listener(row)
            if listener is None:
                continue
            listener.start()
            self.listeners[connection_id] = listener

    def stop_all(self) -> None:
        for listener in self.listeners.values():
            listener.stop()
        self.listeners.clear()

    def ensure_all_running(self) -> None:
        for listener in self.listeners.values():
            try:
                listener.ensure_running()
            except Exception:
                logger.exception("Failed to restart a dead analyzer listener")

    def get(self, connection_id: int) -> Optional[_BaseAnalyzerLink]:
        return self.listeners.get(connection_id)

    def first_running(self) -> Optional[_BaseAnalyzerLink]:
        """Fallback target for callers that don't let the user pick a connection."""
        for listener in self.listeners.values():
            if listener.is_running():
                return listener
        return None

    def status(self) -> list[Dict[str, Any]]:
        return [
            {"id": connection_id, "running": listener.is_running()}
            for connection_id, listener in self.listeners.items()
        ]
