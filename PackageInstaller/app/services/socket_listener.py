"""Background analyzer listeners (TCP and, via serial_listener.py, USB/serial).

`_BaseAnalyzerLink` holds everything transport-agnostic: the ASTM ENQ/ACK/EOT
handshake, transcript capture, decode-and-save, auto machine-registration, and
the outbound order-push protocol. Subclasses only need to implement `_open()`,
returning a context manager that yields a transport object exposing
`.read(timeout) -> bytes` (empty bytes = no data within timeout) and
`.write(data: bytes)`; a closed/broken connection should raise instead of
returning empty bytes forever, so `_run()` can reopen it.
"""
from __future__ import annotations

import queue
import socket
import threading
from typing import Optional

from app.services.astm_parser import ASTMParseError
from app.services.database import save_raw_capture
from app.services.report_generator import generate_report
from app.utils.logger import get_logger

logger = get_logger(__name__)

ENQ = b"\x05"
ACK = b"\x06"
EOT = b"\x04"


class ConnectionClosedError(Exception):
    """Raised by a transport's read()/write() when the link has gone away and needs reopening."""


class _BaseAnalyzerLink:
    #: value passed as `source` to save_raw_capture()/report_generator() - set by subclasses
    capture_source = "unknown"
    #: seconds to wait before retrying after _open()/_serve() fails
    retry_delay = 3.0

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.outbound_queue = queue.Queue()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name=type(self).__name__)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def ensure_running(self) -> bool:
        if self.is_running():
            return False
        self.start()
        return True

    def _open(self):
        """Return a context manager yielding a transport with .read(timeout)/.write(data)."""
        raise NotImplementedError

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._open() as transport:
                    self._serve(transport)
            except ConnectionClosedError:
                # Normal disconnect (peer closed, or waking up to check stop_event) - reopen immediately.
                continue
            except Exception:
                logger.exception("%s link error; retrying in %.0fs", type(self).__name__, self.retry_delay)
                self._stop_event.wait(self.retry_delay)

    def _serve(self, transport) -> None:
        transcript = bytearray()

        def flush_transcript() -> None:
            if not transcript:
                return
            raw_bytes = bytes(transcript)
            raw_text = raw_bytes.decode("latin-1", errors="replace")
            raw_capture_id = save_raw_capture(source=self.capture_source, payload=raw_text)
            logger.info(
                "Received %d bytes from analyzer (raw_capture_id=%s)",
                len(raw_bytes), raw_capture_id,
            )

            try:
                report = generate_report(
                    raw_bytes,
                    source=self.capture_source,
                    raw_capture_id=raw_capture_id,
                )
            except ASTMParseError as exc:
                logger.error(
                    "Could not decode analyzer transmission (raw_capture_id=%s): %s",
                    raw_capture_id, exc,
                )
            except Exception:
                logger.exception(
                    "Unexpected error decoding analyzer transmission (raw_capture_id=%s)",
                    raw_capture_id,
                )
            else:
                order_number = report.get("order", {}).get("sample_id")
                patient_id = report.get("patient", {}).get("patient_id")

                # Auto-detect and register machine
                sender_name = report.get("meta", {}).get("header", {}).get("sender_name")
                if sender_name:
                    clean_name = sender_name.replace('^', ' ').replace('_', ' ').strip()
                    if clean_name:
                        from app.services.database import load_users, upsert_user, upsert_machine
                        from app.services.piysan_service import get_current_lab_name
                        users = load_users()
                        user_id = users[0]["id"] if users else upsert_user(get_current_lab_name())
                        upsert_machine(user_id, clean_name)
                        logger.info("Auto-registered machine from ASTM header: %s", clean_name)

                logger.info(
                    "Decoded result from analyzer: raw_capture_id=%s order=%s patient=%s "
                    "results=%d warnings=%d",
                    raw_capture_id, order_number, patient_id,
                    len(report.get("results", {})), len(report.get("meta", {}).get("warnings", [])),
                )

            transcript.clear()

        while not self._stop_event.is_set():
            data = transport.read(0.5)

            if not data:
                try:
                    outbound_item = self.outbound_queue.get_nowait()
                    records, result_queue = outbound_item
                    self._send_astm_order(transport, records, result_queue)
                except queue.Empty:
                    pass
                continue

            transcript.extend(data)
            logger.debug("Received chunk (%s bytes)", len(data))

            if data == ENQ:
                transport.write(ACK)
                continue
            if data == EOT:
                flush_transcript()
                continue
            transport.write(ACK)

    def _send_astm_order(self, transport, records: list[str], result_queue: queue.Queue) -> None:
        from app.services.astm_sender import _format_frame
        log_messages = []
        try:
            log_messages.append("Attempting to push order over active connection...")

            # Send ENQ
            transport.write(ENQ)
            log_messages.append("Host -> <ENQ>")

            response = transport.read(5.0)
            if response == ACK:
                log_messages.append("Instrument -> <ACK>")
            else:
                log_messages.append(f"Expected <ACK>, got {response}")
                transport.write(EOT)
                result_queue.put("\n".join(log_messages))
                return

            # Send Frames
            frame_num = 1
            for record in records:
                frame_data = _format_frame(frame_num, record)
                transport.write(frame_data)
                log_messages.append(f"Host -> <STX>{frame_num}...{record[:20]}...<CR><ETX>xx<CR><LF>")

                response = transport.read(5.0)
                if response == ACK:
                    log_messages.append("Instrument -> <ACK>")
                else:
                    log_messages.append(f"Expected <ACK> for frame {frame_num}, got {response}")
                    break

                frame_num += 1

            # Send EOT
            transport.write(EOT)
            log_messages.append("Host -> <EOT>")

        except Exception as e:
            log_messages.append(f"Error pushing order: {e}")
            logger.exception("Error pushing order over active connection")

        result_queue.put("\n".join(log_messages))


class _TcpTransport:
    def __init__(self, conn: socket.socket):
        self.conn = conn

    def read(self, timeout: float) -> bytes:
        self.conn.settimeout(timeout)
        try:
            data = self.conn.recv(4096)
        except socket.timeout:
            return b""
        if not data:
            raise ConnectionClosedError("peer closed connection")
        return data

    def write(self, data: bytes) -> None:
        self.conn.sendall(data)


class _TcpTransportContext:
    """Accepts a single TCP connection (honoring stop_event while waiting), yields a _TcpTransport."""

    def __init__(self, host: str, port: int, stop_event: threading.Event):
        self.host = host
        self.port = port
        self._stop_event = stop_event
        self._server: Optional[socket.socket] = None
        self._conn: Optional[socket.socket] = None

    def __enter__(self) -> _TcpTransport:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(1)
        self._server.settimeout(1.0)
        logger.info("Analyzer listener active on %s:%s", self.host, self.port)

        while not self._stop_event.is_set():
            try:
                conn, addr = self._server.accept()
            except socket.timeout:
                continue
            logger.info("Analyzer connected from %s", addr)
            self._conn = conn
            return _TcpTransport(conn)

        raise ConnectionClosedError("stopped while waiting for a connection")

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        if self._server is not None:
            try:
                self._server.close()
            except Exception:
                pass


class AnalyzerListener(_BaseAnalyzerLink):
    capture_source = "socket"

    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        super().__init__()
        self.host = host
        self.port = port

    def _open(self):
        return _TcpTransportContext(self.host, self.port, self._stop_event)
