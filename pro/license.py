"""Offline license validation (Pro/Enterprise gate).

Design goals:
  * Works fully offline — no phone-home required to unlock Pro features,
    since `ctf` needs to run inside sandboxed/air-gapped CI and customer
    environments.
  * The *private* key never ships in the binary. Only `SEMANTICS_PUBLIC_KEY_PEM`
    (or `license_public_key.pem`, see below) is bundled, so a decompiled
    binary cannot mint new licenses — it can only verify them.
  * License keys are signed JWTs (RS256) carrying { sub, plan, seats, expiry }.

Key management lives in `tools/generate_license.py` (dev-only, not shipped).
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import jwt
from jwt.exceptions import InvalidTokenError

DEFAULT_PUBLIC_KEY_PATH = Path(__file__).parent / "license_public_key.pem"


class LicenseError(RuntimeError):
    pass


@dataclass
class License:
    licensed_to: str
    plan: str  # "pro" | "enterprise"
    seats: int
    expires_at: datetime
    raw_claims: dict

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def summary(self) -> str:
        return f"{self.plan.upper()} · licensed to {self.licensed_to} · expires {self.expires_at:%Y-%m-%d}"


def _load_public_key(public_key_pem: Optional[str] = None) -> str:
    if public_key_pem:
        return public_key_pem
    env_key = os.getenv("SEMANTICS_PUBLIC_KEY_PEM")
    if env_key:
        return env_key
    if DEFAULT_PUBLIC_KEY_PATH.exists():
        return DEFAULT_PUBLIC_KEY_PATH.read_text()
    raise LicenseError(
        "No license public key available (checked SEMANTICS_PUBLIC_KEY_PEM env var and "
        f"{DEFAULT_PUBLIC_KEY_PATH}). Pro features cannot be validated in this build."
    )


def validate_license(license_key: str, public_key_pem: Optional[str] = None) -> tuple[bool, str | License]:
    """Validate a license key. Returns (True, License) or (False, error message)."""
    if not license_key or not license_key.strip():
        return False, "No license key provided."

    try:
        public_key = _load_public_key(public_key_pem)
    except LicenseError as exc:
        return False, str(exc)

    try:
        claims = jwt.decode(license_key, public_key, algorithms=["RS256"])
    except InvalidTokenError as exc:
        return False, f"Invalid license: {exc}"

    try:
        expires_at = datetime.fromisoformat(claims["expiry"]).astimezone(timezone.utc)
        lic = License(
            licensed_to=claims["sub"],
            plan=claims.get("plan", "pro"),
            seats=int(claims.get("seats", 1)),
            expires_at=expires_at,
            raw_claims=claims,
        )
    except (KeyError, ValueError) as exc:
        return False, f"Malformed license claims: {exc}"

    if lic.is_expired:
        return False, f"License expired on {lic.expires_at:%Y-%m-%d}."

    return True, lic


def require_license(feature_name: str):
    """Decorator: raise LicenseError if no valid license is configured.

    Usage:
        @require_license("browser_navigate")
        def browser_navigate(...): ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = os.getenv("SEMANTICS_LICENSE_KEY")
            ok, result = validate_license(key or "")
            if not ok:
                raise LicenseError(
                    f"'{feature_name}' requires a valid Pro license. {result} "
                    "Get one at https://semantics.dev/pricing."
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
