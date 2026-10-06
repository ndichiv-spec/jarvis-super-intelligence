"""
Startup validation CLI.

Usage:
    python -m infrastructure.startup.cli
    python -m infrastructure.startup.cli --ci
"""

import os
import sys
import json
import asyncio
import argparse
from infrastructure.startup.validator import (
    get_startup_validator,
    check_tcp_connectivity,
    check_env_var,
    check_disk_space,
    check_directory_writable,
)


def build_checks(validator):
    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://jarvis:jarvis_password@postgres:5432/jarvis")
    redis_url = os.environ.get("REDIS_URL", "redis://:redis_password@redis:6379/0")

    db_host = "localhost"
    db_port = 5432
    if "://" in database_url:
        parts = database_url.split("://")[1].split("@")
        if len(parts) > 1:
            host_part = parts[1].split("/")[0]
        else:
            host_part = parts[0].split("/")[0]
        if ":" in host_part:
            db_host, db_port_str = host_part.split(":")
            db_port = int(db_port_str)
        else:
            db_host = host_part

    redis_host = "localhost"
    redis_port = 6379
    if "://" in redis_url:
        parts = redis_url.split("://")[1].split("@")
        host_part = parts[-1].split("/")[0]
        if ":" in host_part:
            redis_host, redis_port_str = host_part.split(":")
            redis_port = int(redis_port_str)
        else:
            redis_host = host_part

    validator.register(check_tcp_connectivity(db_host, db_port, "database"))
    validator.register(check_tcp_connectivity(redis_host, redis_port, "redis"))

    validator.register(check_env_var("SECRET_KEY", severity="critical"))
    validator.register(check_env_var("GOOGLE_GEMINI_API_KEY", severity="warning"))
    validator.register(check_env_var("OPENAI_API_KEY", severity="warning"))

    min_gb = float(os.environ.get("STARTUP_CHECK_DISK_MIN_GB", "1"))
    validator.register(check_disk_space(".", min_gb=min_gb))

    validator.register(check_directory_writable("logs"))
    validator.register(check_directory_writable("data"))


async def main():
    parser = argparse.ArgumentParser(description="JARVIS startup validation")
    parser.add_argument("--ci", action="store_true", help="CI mode (exit 1 on any failure)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    validator = get_startup_validator()
    build_checks(validator)

    results = await validator.run()
    report = validator.report(results)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  JARVIS Startup Validation Report")
        print(f"{'='*60}")
        print(f"  Timestamp:  {report['timestamp']}")
        print(f"  Checks:     {report['passed']}/{report['total']} passed")
        print(f"  Critical:   {report['critical_failures']}")
        print(f"  Can start:  {'YES' if report['can_start'] else 'NO'}")
        print(f"{'='*60}\n")

        for check in report["checks"]:
            icon = "✓" if check["passed"] else "✗"
            sev = check["severity"].upper()
            print(f"  [{sev:8s}] {icon} {check['name']:30s} {check['message']}")
        print()

    if args.ci and not report["all_passed"]:
        sys.exit(1)

    if not report["can_start"]:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
