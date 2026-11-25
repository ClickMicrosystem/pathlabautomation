"""Send a synthetic ASTM result to the application's TCP analyzer listener."""
from __future__ import annotations

import argparse
import socket
import sys
from datetime import datetime

ENQ = b"\x05"
ACK = b"\x06"
EOT = b"\x04"


def build_frame(frame_number: int, record: str) -> bytes:
    """Build one checksum-valid ASTM frame."""
    payload = (
        str(frame_number % 8).encode("ascii")
        + record.encode("latin-1", errors="replace")
        + b"\r\x03"
    )
    checksum = sum(payload) % 256
    return b"\x02" + payload + f"{checksum:02X}".encode("ascii") + b"\r\n"


def receive_ack(connection: socket.socket, label: str) -> None:
    response = connection.recv(1)
    if response != ACK:
        raise RuntimeError(f"Expected ACK for {label}, received {response!r}")
    print(f"ACK received: {label}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate an analyzer sending a small ASTM result to the LIS listener."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="LIS server IP or hostname (default: 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=5000, help="LIS listener TCP port")
    parser.add_argument("--timeout", type=float, default=5.0, help="Connection/ACK timeout in seconds")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    sample_id = "SIM-SAMPLE-001"
    records = [
        f"H|\\^&|||SIMULATED^HORIBA|||||LIS||P|1|{timestamp}",
        "P|1||SIM-PAT-001||Test^Patient||19800101|F",
        f"O|1|{sample_id}||^^^WBC|R|{timestamp}",
        f"R|1|^^^WBC|6.42|10^3/uL|4.00-10.00|N||F|||{timestamp}",
        "L|1|N",
    ]

    print(f"Connecting to LIS listener at {args.host}:{args.port}...")
    try:
        with socket.create_connection(
            (args.host, args.port), timeout=args.timeout
        ) as connection:
            connection.settimeout(args.timeout)
            connection.sendall(ENQ)
            receive_ack(connection, "ENQ")

            for frame_number, record in enumerate(records, start=1):
                connection.sendall(build_frame(frame_number, record))
                receive_ack(connection, f"frame {frame_number}")

            connection.sendall(EOT)
    except (OSError, RuntimeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"Transmission sent (sample ID: {sample_id}); EOT sent.")
    print("ACKs confirm the listener received the transmission. Check the LIS log/results to confirm decoding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
