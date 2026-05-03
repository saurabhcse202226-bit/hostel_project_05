import os


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


# SMTP (Email) configuration
SMTP_HOST: str = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = _get_int("SMTP_PORT", 587)
SMTP_USER: str = os.environ.get("SMTP_USER", "")
SMTP_PASS: str = os.environ.get("SMTP_PASS", "")
SMTP_FROM: str = os.environ.get("SMTP_FROM", "") or SMTP_USER

# Fast2SMS (SMS) configuration
# For Fast2SMS, `authorization` header value is typically the API key itself.
# Keep a fallback for typo-ed env name used by some deployments.
FAST2SMS_API_KEY: str = os.environ.get("FAST2SMS_API_KEY", "") or os.environ.get("FAS2SMS_API_KEY", "")
FAST2SMS_ROUTE: str = os.environ.get("FAST2SMS_ROUTE", "q").strip() or "q"
FAST2SMS_SENDER_ID: str = os.environ.get("FAST2SMS_SENDER_ID", "").strip()

