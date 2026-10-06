# Independent JARVIS backend supervision

The backend and web frontend are separate processes. The API liveness route is
`/health/live`; database readiness is reported at `/health/ready`. Model
providers and frontend reachability are diagnostic states and do not stop API
readiness. The configured frontend origin is reported by
`/api/v1/runtime/frontend` using `JARVIS_APP_URL`.

## Windows startup task

Run PowerShell as the account that owns the project files, from the project
root:

```powershell
.\scripts\install_backend_task.ps1
```

The task starts the API supervisor at system startup. The supervisor logs API
stdout/stderr and its own state under `jarvis_data\supervisor`. It allows a
startup grace period, restarts an unresponsive API with bounded exponential
backoff, reports restart-budget exhaustion, and retries after a cooldown. It
does not start or depend on the frontend.

Remove the task with:

```powershell
Unregister-ScheduledTask -TaskName "JARVIS Backend Supervisor" -Confirm:$false
```

The scheduled task runs as the installing Windows account and reads the
project's environment through the normal `jarvis_api.py` bootstrap. Keep `.env`
readable only by that account. To start the backend and frontend interactively,
use `F:\AI\start_all.ps1`; the frontend can fail or restart without stopping
the API supervisor.

## Containers

Use `restart: unless-stopped` for Compose and the corrected `/health/live` and
`/health/ready` probes in Kubernetes. Liveness must remain independent of
external AI providers and the frontend.
