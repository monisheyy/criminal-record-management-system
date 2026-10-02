"""Password recovery providers and cryptographic helpers.

OTP/reset secrets are never persisted in plaintext. The development provider
logs the OTP locally; it does not pretend to deliver production email/SMS.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import smtplib
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger("ai_crms.password_recovery")

OTP_LENGTH = 6
OTP_TTL_SECONDS = int(os.getenv("RECOVERY_OTP_TTL_SECONDS", "300"))
OTP_MAX_ATTEMPTS = int(os.getenv("RECOVERY_OTP_MAX_ATTEMPTS", "5"))
REQUEST_COOLDOWN_SECONDS = int(os.getenv("RECOVERY_REQUEST_COOLDOWN_SECONDS", "60"))
REQUESTS_PER_IP_WINDOW = int(os.getenv("RECOVERY_REQUEST_WINDOW_SECONDS", "900"))
REQUESTS_PER_IP_MAX = int(os.getenv("RECOVERY_REQUESTS_PER_IP_MAX", "10"))
RESET_TOKEN_TTL_SECONDS = int(os.getenv("RECOVERY_RESET_TOKEN_TTL_SECONDS", "600"))


def _pepper() -> bytes:
    secret = os.getenv("SECRET_KEY")
    if not secret or len(secret) < 32:
        raise RuntimeError("SECRET_KEY must be configured before password recovery is used")
    return secret.encode("utf-8")


def generate_otp() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    return hmac.new(_pepper(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def secrets_match(value: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(value), stored_hash)


class RecoveryProvider(Protocol):
    def send_otp(self, destination: str, otp: str) -> None: ...


class DevelopmentRecoveryProvider:
    """Development-only provider: logs the OTP and never claims delivery."""
    def send_otp(self, destination: str, otp: str) -> None:
        logger.warning("PASSWORD_RECOVERY_DEV_OTP destination=%s otp=%s", destination, otp)


class SMTPRecoveryProvider:
    def send_otp(self, destination: str, otp: str) -> None:
        host = os.getenv("RECOVERY_SMTP_HOST")
        port = int(os.getenv("RECOVERY_SMTP_PORT", "587"))
        username = os.getenv("RECOVERY_SMTP_USERNAME")
        password = os.getenv("RECOVERY_SMTP_PASSWORD")
        sender = os.getenv("RECOVERY_SMTP_FROM")
        if not all([host, username, password, sender]):
            raise RuntimeError("SMTP recovery provider is not fully configured")
        message = EmailMessage()
        message["Subject"] = "AI-CRMS password recovery verification code"
        message["From"] = sender
        message["To"] = destination
        message.set_content(f"Your AI-CRMS verification code is {otp}. It expires shortly and can only be used once.")
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(message)


def get_recovery_provider() -> RecoveryProvider:
    provider = os.getenv("RECOVERY_PROVIDER", "dev").lower()
    if provider == "smtp":
        return SMTPRecoveryProvider()
    if provider == "dev":
        return DevelopmentRecoveryProvider()
    raise RuntimeError(f"Unsupported RECOVERY_PROVIDER: {provider}")
