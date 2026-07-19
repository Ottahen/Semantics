#!/usr/bin/env python3
"""DEV-ONLY: generate an RSA keypair and sign license keys.

    python tools/generate_license.py init-keys
    python tools/generate_license.py issue --to "acme-corp" --plan pro --days 365

The private key never leaves this machine / your CI secret store. Only
`src/pro/license_public_key.pem` is meant to be bundled into the shipped
binary (see `src/pro/license.py`).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_KEY_PATH = ROOT / "tools" / "license_private_key.pem"  # keep OUT of version control
PUBLIC_KEY_PATH = ROOT / "src" / "pro" / "license_public_key.pem"


def init_keys() -> None:
    if PRIVATE_KEY_PATH.exists():
        print(f"Private key already exists at {PRIVATE_KEY_PATH}, refusing to overwrite.", file=sys.stderr)
        sys.exit(1)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    PRIVATE_KEY_PATH.chmod(0o600)

    PUBLIC_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_KEY_PATH.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Wrote private key -> {PRIVATE_KEY_PATH} (keep secret, do not commit)")
    print(f"Wrote public key  -> {PUBLIC_KEY_PATH} (safe to bundle/ship)")


def issue(to: str, plan: str, days: int, seats: int) -> None:
    if not PRIVATE_KEY_PATH.exists():
        print("No private key found. Run `generate_license.py init-keys` first.", file=sys.stderr)
        sys.exit(1)

    private_key = PRIVATE_KEY_PATH.read_text()
    expiry = datetime.now(timezone.utc) + timedelta(days=days)
    claims = {
        "sub": to,
        "plan": plan,
        "seats": seats,
        "expiry": expiry.isoformat(),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    print(token)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-keys", help="Generate a new RSA keypair (run once).")

    issue_p = sub.add_parser("issue", help="Sign a new license key.")
    issue_p.add_argument("--to", required=True, help="Licensee name/org, embedded in the token.")
    issue_p.add_argument("--plan", default="pro", choices=["pro", "enterprise"])
    issue_p.add_argument("--days", type=int, default=365)
    issue_p.add_argument("--seats", type=int, default=1)

    args = parser.parse_args()
    if args.cmd == "init-keys":
        init_keys()
    elif args.cmd == "issue":
        issue(args.to, args.plan, args.days, args.seats)


if __name__ == "__main__":
    main()
