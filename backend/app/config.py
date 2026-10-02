"""Centralised, environment-aware application settings.

Every runtime setting is read from the environment (optionally via ``.env``)
exactly once, validated, and exposed through ``settings``. Production mode
(``APP_ENV=production``) refuses to start with development conveniences that
would be unsafe on a real deployment: wildcard CORS, demo data, the
development OTP provider, non-HTTPS cookies or interactive API docs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise RuntimeError(f"{name} must be a boolean (true/false), got {raw!r}")


def _int(name: str, default: int, low: int, high: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise RuntimeError(f"{name} must be between {low} and {high}")
    return value


def _float(name: str, default: float, low: float, high: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not low <= value <= high:
        raise RuntimeError(f"{name} must be between {low} and {high}")
    return value


def _list(name: str, default: str) -> List[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class ModelQualityGate:
    """Minimum holdout metrics a candidate must reach before activation.

    These thresholds are deliberately configurable: the right values depend on
    the operational use case and must be agreed and documented by the model
    owner. Passing them is necessary but NOT sufficient for real-world use.
    """

    min_macro_f1: float
    min_balanced_accuracy: float
    max_zero_recall_classes: int
    require_beats_majority_baseline: bool
    max_expected_calibration_error: float
    min_test_samples: int

    def as_dict(self) -> dict:
        return {
            "min_macro_f1": self.min_macro_f1,
            "min_balanced_accuracy": self.min_balanced_accuracy,
            "max_zero_recall_classes": self.max_zero_recall_classes,
            "require_beats_majority_baseline": self.require_beats_majority_baseline,
            "max_expected_calibration_error": self.max_expected_calibration_error,
            "min_test_samples": self.min_test_samples,
        }


@dataclass(frozen=True)
class Settings:
    app_env: str
    secret_key: str
    database_url: str
    cors_origins: List[str]
    access_token_expire_minutes: int
    seed_demo_data: bool
    enable_api_docs: bool
    cookie_secure: bool
    cookie_samesite: str
    trusted_hosts: List[str]
    login_max_failed_attempts: int
    login_lockout_minutes: int
    rate_limit_auth_per_minute: int
    ai_predictions_enabled: bool
    ai_allow_synthetic_models: bool
    model_quality_gate: ModelQualityGate
    log_json: bool
    log_level: str
    recovery_provider: str
    algorithm: str = field(default="HS256")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


def _load_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV must be one of: development, test, production")
    production = app_env == "production"

    secret_key = os.getenv("SECRET_KEY") or ""
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and set a strong random value.")
    if len(secret_key) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters long")
    if production and secret_key.lower().startswith(("change-me", "test-", "dev-")):
        raise RuntimeError("SECRET_KEY looks like a placeholder; generate a real secret for production")

    algorithm = os.getenv("ALGORITHM", "HS256")
    if algorithm != "HS256":
        raise RuntimeError("Unsupported JWT algorithm; only HS256 is allowed")

    cors_default = "" if production else "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    cors_origins = _list("CORS_ORIGINS", cors_default)
    if "*" in cors_origins:
        raise RuntimeError("CORS_ORIGINS must be an explicit allowlist; '*' is not permitted with credentials")
    if production:
        if not cors_origins:
            raise RuntimeError("CORS_ORIGINS must be set explicitly in production")
        insecure = [origin for origin in cors_origins if not origin.startswith("https://")]
        if insecure:
            raise RuntimeError(f"Production CORS origins must use HTTPS: {insecure}")

    seed_demo_data = _bool("SEED_DEMO_DATA", default=not production)
    if production and seed_demo_data:
        raise RuntimeError("SEED_DEMO_DATA must be false in production (demo credentials are public)")

    recovery_provider = os.getenv("RECOVERY_PROVIDER", "dev").strip().lower()
    if production and recovery_provider == "dev":
        raise RuntimeError("RECOVERY_PROVIDER=dev logs OTPs and is not allowed in production")

    cookie_secure = _bool("COOKIE_SECURE", default=production)
    if production and not cookie_secure:
        raise RuntimeError("COOKIE_SECURE must be true in production (HTTPS only)")
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "strict").strip().lower()
    if cookie_samesite not in {"strict", "lax"}:
        raise RuntimeError("COOKIE_SAMESITE must be 'strict' or 'lax'")

    enable_api_docs = _bool("ENABLE_API_DOCS", default=not production)

    ai_allow_synthetic = _bool("AI_ALLOW_SYNTHETIC_MODELS", default=not production)
    if production and ai_allow_synthetic:
        raise RuntimeError("AI_ALLOW_SYNTHETIC_MODELS must be false in production")

    trusted_hosts = _list("TRUSTED_HOSTS", "" if production else "*")
    if production and (not trusted_hosts or "*" in trusted_hosts):
        raise RuntimeError("TRUSTED_HOSTS must list the public host name(s) in production")

    gate = ModelQualityGate(
        min_macro_f1=_float("MODEL_GATE_MIN_MACRO_F1", 0.60, 0.0, 1.0),
        min_balanced_accuracy=_float("MODEL_GATE_MIN_BALANCED_ACCURACY", 0.60, 0.0, 1.0),
        max_zero_recall_classes=_int("MODEL_GATE_MAX_ZERO_RECALL_CLASSES", 0, 0, 1000),
        require_beats_majority_baseline=_bool("MODEL_GATE_REQUIRE_BEATS_BASELINE", True),
        max_expected_calibration_error=_float("MODEL_GATE_MAX_ECE", 0.15, 0.0, 1.0),
        min_test_samples=_int("MODEL_GATE_MIN_TEST_SAMPLES", 100, 1, 10_000_000),
    )

    return Settings(
        app_env=app_env,
        secret_key=secret_key,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./acrms.db"),
        cors_origins=cors_origins,
        access_token_expire_minutes=_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60, 5, 1440),
        seed_demo_data=seed_demo_data,
        enable_api_docs=enable_api_docs,
        cookie_secure=cookie_secure,
        cookie_samesite=cookie_samesite,
        trusted_hosts=trusted_hosts,
        login_max_failed_attempts=_int("LOGIN_MAX_FAILED_ATTEMPTS", 5, 1, 100),
        login_lockout_minutes=_int("LOGIN_LOCKOUT_MINUTES", 15, 1, 24 * 60),
        rate_limit_auth_per_minute=_int("RATE_LIMIT_AUTH_PER_MINUTE", 20, 1, 10_000),
        ai_predictions_enabled=_bool("AI_PREDICTIONS_ENABLED", True),
        ai_allow_synthetic_models=ai_allow_synthetic,
        model_quality_gate=gate,
        log_json=_bool("LOG_JSON", default=production),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        recovery_provider=recovery_provider,
        algorithm=algorithm,
    )


settings = _load_settings()
