# JARVIS M3D — External Alert Delivery

## Endpoint

`POST /api/v1/alerts/test-delivery` sends one test message using the SMTP configuration and recipient allow-list already held by the alerting engine. It accepts no caller-supplied recipient, subject, body, or alert details.

## Enablement

External test dispatch is disabled unless the backend environment contains:

```dotenv
JARVIS_ALERT_EMAIL_EXTERNAL_NOTIFY=true
```

The value is trimmed and compared case-insensitively against the literal `true`; missing values and all other values remain disabled. Keep the flag disabled until the endpoint is reviewed and live provider delivery is explicitly approved.

## Protections

- Uses JARVIS's existing `_require_admin` dependency; unauthenticated calls are rejected and authenticated non-admin calls are forbidden.
- Fails closed when the feature flag is missing or invalid.
- Limits this endpoint to five requests per fifteen minutes per process, in addition to the SMTP sender's own outbound-send limit.
- Uses the configured SMTP recipient allow-list; the API does not accept recipient parameters.
- Emits audit events for blocked, attempted, failed, rate-limited and SMTP-accepted outcomes without returning exception traces or credentials.
- Does not register the synthetic test alert as an actual active monitoring alert.
- Reports SMTP acceptance only. It does not claim that the destination mailbox received the message.

## Deployment and operations

The endpoint rate limiter is process-local. Multi-worker or multi-replica deployments must also use a shared gateway/distributed limit to prevent the limit being multiplied by worker count. Deploy the code with the flag unset or set to `false`; do not turn it on by default in a shared `.env.example` or production manifest.

Before production enablement:
1. Run the API tests and the existing SMTP alert tests.
2. Run the broader suite and compare against the documented baseline.
3. Configure provider credentials through the deployment secret manager, not committed files.
4. Perform a controlled live test using an approved recipient and verify the mailbox separately.
5. Monitor the security audit events and disable the feature flag after the test if ongoing access is not needed.

## Test commands

```bash
pytest tests/test_alert_external_delivery_api.py tests/test_alert_email_delivery.py -q
pytest tests/ --continue-on-collection-errors -q --ignore=tests/test_nvidia_provider.py --ignore=tests/test_nvidia.py
```

The API tests use a fake engine and do not prove live SMTP delivery.
