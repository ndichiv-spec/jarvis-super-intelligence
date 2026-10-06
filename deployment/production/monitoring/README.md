# Monitoring profile

Enable the bundled Prometheus scrape and alert rules with:

```sh
docker compose --env-file .env -f docker-compose.prod.yml --profile monitoring up -d prometheus
```

Prometheus is not published to the host or internet. Alerts are evaluated and
stored locally; no notification receiver is configured, so this profile does
not deliver pages or email. Until a real receiver is implemented and
configured, alert delivery must be reported as
`ALERT_DELIVERY_NOT_CONFIGURED`; Prometheus rule evaluation is not delivery.
The API currently exports request, latency, and
error metrics. Database, host, provider, connector, and certificate alerting
requires additional exporters and an externally configured notification
receiver.
