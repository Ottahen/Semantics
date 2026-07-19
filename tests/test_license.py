# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pro.license import LicenseError, require_license, validate_license


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _make_token(private_pem: str, *, plan="pro", seats=5, days=365, sub="acme-corp") -> str:
    claims = {
        "sub": sub,
        "plan": plan,
        "seats": seats,
        "expiry": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
    }
    return jwt.encode(claims, private_pem, algorithm="RS256")


def test_valid_license_passes(keypair):
    private_pem, public_pem = keypair
    token = _make_token(private_pem)
    ok, result = validate_license(token, public_key_pem=public_pem)
    assert ok is True
    assert result.plan == "pro"
    assert result.licensed_to == "acme-corp"
    assert result.seats == 5


def test_expired_license_fails(keypair):
    private_pem, public_pem = keypair
    token = _make_token(private_pem, days=-1)
    ok, result = validate_license(token, public_key_pem=public_pem)
    assert ok is False
    assert "expired" in result


def test_empty_key_fails(keypair):
    _, public_pem = keypair
    ok, result = validate_license("", public_key_pem=public_pem)
    assert ok is False
    assert "No license key" in result


def test_tampered_token_fails(keypair):
    private_pem, public_pem = keypair
    token = _make_token(private_pem)
    tampered = token[:-4] + "abcd"
    ok, result = validate_license(tampered, public_key_pem=public_pem)
    assert ok is False


def test_token_signed_by_wrong_key_is_rejected(keypair):
    _, public_pem = keypair
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private_pem = other_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    token = _make_token(other_private_pem)
    ok, result = validate_license(token, public_key_pem=public_pem)
    assert ok is False


def test_require_license_decorator_blocks_without_key(monkeypatch):
    monkeypatch.delenv("SEMANTICS_LICENSE_KEY", raising=False)

    @require_license("some_pro_feature")
    def gated():
        return "ran"

    with pytest.raises(LicenseError):
        gated()


def test_require_license_decorator_allows_with_valid_key(monkeypatch, keypair):
    private_pem, public_pem = keypair
    token = _make_token(private_pem)
    monkeypatch.setenv("SEMANTICS_LICENSE_KEY", token)
    monkeypatch.setenv("SEMANTICS_PUBLIC_KEY_PEM", public_pem)

    @require_license("some_pro_feature")
    def gated():
        return "ran"

    assert gated() == "ran"
