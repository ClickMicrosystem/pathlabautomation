"""USB/serial analyzer listener - same ASTM handshake as AnalyzerListener, but
framed over a COM port instead of a TCP socket. See socket_listener.py for the
shared protocol/decode logic (_BaseAnalyzerLink)."""
from __future__ import annotations

from typing import Optional

import serial
from serial.tools import list_ports

from app.services.socket_listener import ConnectionClosedError, _BaseAnalyzerLink
from app.utils.logger import get_logger

logger = get_logger(__name__)


class _SerialTransport:
    def __init__(self, ser: "serial.Serial"):
        self.ser = ser

    def read(self, timeout: float) -> bytes:
        self.ser.timeout = timeout
        try:
            return self.ser.read(4096)
        except serial.SerialException as exc:
            raise ConnectionClosedError(str(exc)) from exc

    def write(self, data: bytes) -> None:
        try:
            self.ser.write(data)
            self.ser.flush()
        except serial.SerialException as exc:
            raise ConnectionClosedError(str(exc)) from exc


class _SerialTransportContext:
    def __init__(self, com_port: str, baud_rate: int):
        self.com_port = com_port
        self.baud_rate = baud_rate
        self._ser: Optional["serial.Serial"] = None

    def __enter__(self) -> _SerialTransport:
        self._ser = serial.Serial(
            port=self.com_port,
            baudrate=self.baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.5,
        )
        logger.info("Serial analyzer listener active on %s @ %s baud", self.com_port, self.baud_rate)
        return _SerialTransport(self._ser)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass


class SerialAnalyzerListener(_BaseAnalyzerLink):
    capture_source = "serial"

    def __init__(self, com_port: str, baud_rate: int = 9600):
        super().__init__()
        self.com_port = com_port
        self.baud_rate = baud_rate

    def _open(self):
        return _SerialTransportContext(self.com_port, self.baud_rate)


def list_available_ports() -> list[dict]:
    """Enumerate COM ports currently visible to the OS, for the connection-setup dropdown."""
    return [
        {"device": p.device, "description": p.description}
        for p in list_ports.comports()
    ]
