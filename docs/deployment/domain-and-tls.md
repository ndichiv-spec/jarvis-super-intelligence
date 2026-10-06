# Domain and TLS

Choose a hostname under a domain you control and place that exact hostname in
`JARVIS_DOMAIN`. No example domain is embedded in the production configuration.

At the authoritative DNS provider, create:

- An `A` record for the chosen hostname pointing to the VPS public IPv4 address.
- An `AAAA` record only if the server has stable, working public IPv6 and the
  firewall allows TCP 80/443 and UDP 443 over IPv6 too. Otherwise omit AAAA.

Wait for DNS propagation and verify every published address resolves to the
intended server before bringing up Caddy. Permit inbound TCP 80 and 443 plus
UDP 443. Caddy obtains and renews certificates automatically using ACME and
redirects HTTP to HTTPS. Keep `caddy_data` persistent; it stores certificates
and ACME account state. Do not mount self-signed certificates or use the
legacy Nginx certificate paths for production.

Set `ACME_EMAIL` to an operational contact. The application origin is
`https://<configured-hostname>`; API and WebSocket calls use that same origin.
No API, PostgreSQL, Redis, worker, gRPC, or monitoring port should be exposed
in public DNS or firewall rules.
