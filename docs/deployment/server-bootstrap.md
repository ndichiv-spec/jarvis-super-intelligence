# Linux server bootstrap

1. Provision a maintained Ubuntu LTS or equivalent Linux server with
   persistent SSD storage. Keep SSH access restricted to administrator IPs.
2. Install Docker Engine and the Docker Compose plugin from Docker's official
   repository. Enable automatic Docker startup:

   ```sh
   sudo systemctl enable --now docker
   sudo usermod -aG docker "$USER"
   ```

   Log out and reconnect before using the Docker group.
3. Restrict inbound traffic to SSH plus web ports:

   ```sh
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow OpenSSH
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw allow 443/udp
   sudo ufw enable
   ```
4. Clone the authorized GitHub repository into a service-owned directory.
   Authenticate to GHCR with a package-read token, then check out an immutable
   release SHA rather than a floating branch or `latest` tag.
5. Create `/etc/jarvis/secrets` with mode `0700`; create the secret files
   listed in [production.md](production.md) with mode `0600`. Do not copy
   secrets into the checkout.
6. Set domain and image metadata in
   `deployment/production/.env`, validate with the Compose `config` command,
   then run the documented deployment script.
7. Confirm only 80/443 are listening publicly. Confirm container restart
   policies, health state, persistent volumes, and successful external HTTPS
   access after reboot.

This bootstrap document does not provision a host or certify firewall,
provider, or identity settings on an unprovided server.
