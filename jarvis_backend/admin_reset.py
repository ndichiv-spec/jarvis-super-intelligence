"""Administrative password reset mechanism for JARVIS.

Enforces administrative safety invariants:
1. Requires explicit administrative execution (CLI or explicit admin call).
2. Uses the configured admin secret / password source or secure interactive prompt.
3. Hashes the password using the existing PBKDF2-HMAC-SHA256 password-hashing mechanism.
4. Never logs the plain password.
5. Never returns the plain password through any API or dictionary result.
6. Never overwrites an existing admin password silently during normal startup.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from typing import Any, Dict, Optional

from .core import (
    get_store,
    hash_password,
    verify_password,
    now_iso,
    is_admin,
)

logger = logging.getLogger("jarvis_backend.admin_reset")


class AdminResetError(Exception):
    """Raised when administrative password reset fails."""
    pass


def reset_admin_password(
    identifier: Optional[str] = None,
    new_password: Optional[str] = None,
    *,
    require_admin_role: bool = True,
) -> Dict[str, Any]:
    """Safely reset the password for an administrative user.

    Args:
        identifier: Email or user ID of the admin. If None, resolves to the
                    configured ADMIN_EMAIL / JARVIS_ADMIN_EMAIL or the canonical owner.
        new_password: The new plain text password. If None, reads from
                      JARVIS_ADMIN_PASSWORD or ADMIN_PASSWORD env vars.
        require_admin_role: If True, asserts the targeted user holds an admin role.

    Returns:
        A dictionary with status and metadata (user_id, email, updated_at).
        Never returns the password.
    """
    store = get_store("users")
    users = store.load()

    # 1. Resolve target user
    target_user_id: Optional[str] = None
    target_user: Optional[Dict[str, Any]] = None

    if identifier:
        norm_id = identifier.strip().lower()
        for uid, user in users.items():
            if not isinstance(user, dict):
                continue
            if uid == identifier or user.get("email", "").strip().lower() == norm_id:
                target_user_id = uid
                target_user = user
                break
        if not target_user:
            raise AdminResetError(f"User '{identifier}' not found in user store.")
    else:
        # Default to configured admin email or canonical owner
        admin_email = os.environ.get("ADMIN_EMAIL") or os.environ.get("JARVIS_ADMIN_EMAIL") or "admin@jarvis.local"
        norm_admin = admin_email.strip().lower()
        for uid, user in users.items():
            if not isinstance(user, dict):
                continue
            if user.get("email", "").strip().lower() == norm_admin:
                target_user_id = uid
                target_user = user
                break
        if not target_user:
            # Fall back to canonical owner or first admin user
            for uid, user in users.items():
                if isinstance(user, dict) and (user.get("owner") is True or user.get("role") == "admin"):
                    target_user_id = uid
                    target_user = user
                    break

    if not target_user or not target_user_id:
        raise AdminResetError("No administrator account found to reset.")

    # 2. Check admin role invariant
    if require_admin_role and not is_admin(target_user):
        raise AdminResetError(f"User '{target_user.get('email', target_user_id)}' does not have admin privileges.")

    # 3. Resolve password source
    password_to_set = new_password
    if not password_to_set:
        password_to_set = os.environ.get("JARVIS_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD")

    if not password_to_set or not password_to_set.strip():
        raise AdminResetError(
            "No password provided. Supply a password or configure JARVIS_ADMIN_PASSWORD in the environment."
        )

    if len(password_to_set) < 8:
        raise AdminResetError("Administrative password must be at least 8 characters long.")

    # 4. Hash using existing PBKDF2-HMAC-SHA256 mechanism
    new_hash = hash_password(password_to_set)

    # 5. Persist update
    now = now_iso()
    target_user["password_hash"] = new_hash
    target_user["password_updated_at"] = now
    target_user["updated_at"] = now
    # Ensure role is admin
    target_user["role"] = "admin"

    store.save()

    # 6. Audit log (never logging the password)
    logger.info(
        "Administrative password reset successfully for user_id=%s email=%s",
        target_user_id,
        target_user.get("email"),
    )

    # 7. Return safe metadata only
    return {
        "success": True,
        "user_id": target_user_id,
        "email": target_user.get("email"),
        "updated_at": now,
    }


def main() -> int:
    """CLI entrypoint for explicit administrative password reset."""
    parser = argparse.ArgumentParser(
        description="Explicit administrative password reset for JARVIS."
    )
    parser.add_argument(
        "--identifier",
        "-i",
        help="Email or user ID of the admin account (defaults to configured admin email).",
    )
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Read new password from JARVIS_ADMIN_PASSWORD or ADMIN_PASSWORD environment variable.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt securely for password from terminal (standard getpass).",
    )

    args = parser.parse_args()

    password: Optional[str] = None
    if args.interactive:
        password = getpass.getpass("Enter new admin password: ")
        confirm = getpass.getpass("Confirm new admin password: ")
        if password != confirm:
            print("Error: Passwords do not match.", file=sys.stderr)
            return 1
    elif not args.from_env:
        # Default behavior: try env first, if absent prompt
        env_pw = os.environ.get("JARVIS_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD")
        if env_pw:
            password = env_pw
        else:
            if sys.stdin.isatty():
                password = getpass.getpass("Enter new admin password: ")
            else:
                print(
                    "Error: In non-interactive mode, either set JARVIS_ADMIN_PASSWORD or pass --from-env.",
                    file=sys.stderr,
                )
                return 1

    try:
        result = reset_admin_password(
            identifier=args.identifier,
            new_password=password,
        )
        print(f"Success: Password reset for {result['email']} (id: {result['user_id']}) at {result['updated_at']}.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
