"""Server-owned email delivery for account verification and recovery."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote, urlsplit, urlunsplit


class AuthEmailNotConfigured(RuntimeError):
    pass


class AuthEmailDeliveryError(RuntimeError):
    pass


def ensure_auth_email_configured() -> None:
    required = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
    missing = [name for name in required if not os.environ.get(name)]
    sender = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER")
    base_url = os.environ.get("JARVIS_PUBLIC_BASE_URL") or os.environ.get("JARVIS_APP_URL")
    if missing or not sender or not base_url:
        raise AuthEmailNotConfigured("Account email delivery is not configured.")

    parsed = urlsplit(base_url)
    production = os.environ.get("JARVIS_ENV", "").lower() == "production"
    local_http = parsed.hostname in {"localhost", "127.0.0.1"} and not production
    if (
        parsed.scheme not in ({"https"} if production else {"https", "http"})
        or (parsed.scheme != "https" and not local_http)
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise AuthEmailNotConfigured("Account email delivery URL configuration is invalid.")


def _action_url(action: str, token: str) -> str:
    ensure_auth_email_configured()
    base_url = os.environ.get("JARVIS_PUBLIC_BASE_URL") or os.environ["JARVIS_APP_URL"]
    parsed = urlsplit(base_url)
    base_path = parsed.path.rstrip("/")
    page = "verify-email" if action == "verify" else "forgot-password"
    fragment = f"token={quote(token, safe='')}"
    return urlunsplit((parsed.scheme, parsed.netloc, f"{base_path}/{page}", "", fragment))


def send_auth_email(recipient: str, action: str, token: str) -> None:
    """Send a one-time account link; never log its address, URL, or token."""
    if action not in {"verify", "reset"}:
        raise ValueError("Unsupported account email action")
    ensure_auth_email_configured()

    link = _action_url(action, token)
    verification = action == "verify"
    message = EmailMessage()
    message["From"] = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]
    message["To"] = recipient
    message["Subject"] = "Verify your JARVIS account" if verification else "Reset your JARVIS password"
    message.set_content(
        (
            "Verify your JARVIS account using the following link. It expires in 24 hours:\n"
            if verification
            else "Reset your JARVIS password using the following link. It expires in 1 hour:\n"
        )
        + link
        + "\n\nIf you did not request this, you can ignore this message.\n"
    )

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    context = ssl.create_default_context()
    server = None
    try:
        if os.environ.get("SMTP_USE_SSL", "").lower() in {"1", "true", "yes"}:
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        server.login(user, password)
        server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise AuthEmailDeliveryError(
            f"Account email delivery failed ({type(error).__name__})."
        ) from error
    finally:
        if server is not None:
            try:
                server.quit()
            except (OSError, smtplib.SMTPException):
                pass
