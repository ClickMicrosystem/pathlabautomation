"""Vendor-side license issuer. Keep the signing private key secret."""
from __future__ import annotations

import argparse
import base64
import json
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BASE_DIR = Path(__file__).resolve().parents[1]
PRIVATE_KEY_PATH = BASE_DIR / "vendor_private_key.pem"


def cmd_genkeypair(_args: argparse.Namespace) -> None:
    if PRIVATE_KEY_PATH.exists():
        raise SystemExit(
            f"{PRIVATE_KEY_PATH} already exists - refusing to overwrite an "
            "existing signing key (that would invalidate every license "
            "issued so far). Delete it manually first if you really mean to."
        )

    private_key = Ed25519PrivateKey.generate()
    PRIVATE_KEY_PATH.write_bytes(private_key.private_bytes_raw())
    public_b64 = base64.b64encode(
        private_key.public_key().public_bytes_raw()
    ).decode("ascii")

    print(f"Private key written to {PRIVATE_KEY_PATH} - back it up securely and keep it secret.")
    print()
    print("Paste this into VENDOR_PUBLIC_KEY_B64 in app/services/license.py:")
    print()
    print(f'VENDOR_PUBLIC_KEY_B64 = "{public_b64}"')


def _load_private_key() -> Ed25519PrivateKey:
    if not PRIVATE_KEY_PATH.exists():
        raise SystemExit(
            f"No signing key at {PRIVATE_KEY_PATH} - run "
            "'LicencingUtility\\license_tool.py genkeypair' first."
        )
    return Ed25519PrivateKey.from_private_bytes(PRIVATE_KEY_PATH.read_bytes())


def cmd_issue(args: argparse.Namespace) -> None:
    private_key = _load_private_key()
    payload = {
        "licensed_to": args.licensed_to,
        "machine_id": args.machine_id,
        "issued_at": date.today().isoformat(),
        "expires_at": args.expires,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["signature"] = base64.b64encode(private_key.sign(canonical)).decode("ascii")

    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"License written to {out_path}")
    print(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(required=True)

    genkeypair_parser = subparsers.add_parser(
        "genkeypair", help="Generate the vendor signing keypair (one-time)."
    )
    genkeypair_parser.set_defaults(func=cmd_genkeypair)

    issue_parser = subparsers.add_parser(
        "issue", help="Issue a license.lic for a client machine."
    )
    issue_parser.add_argument(
        "--machine-id",
        required=True,
        help="The machine ID printed by app.services.license on the client's machine.",
    )
    issue_parser.add_argument(
        "--licensed-to", required=True, help="Client/lab name for the license record."
    )
    issue_parser.add_argument(
        "--expires",
        default=None,
        help="Optional expiry date (YYYY-MM-DD). Omit for a license with no expiry.",
    )
    issue_parser.add_argument(
        "--out", default="license.lic", help="Output file path (default: ./license.lic)."
    )
    issue_parser.set_defaults(func=cmd_issue)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
