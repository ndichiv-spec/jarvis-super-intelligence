"""Manual probe for an optional legacy Flask observation service."""


def run_observation_probe():
    import json

    from observation_blueprint import observation_bp
    from web_server import app

    app.register_blueprint(observation_bp)
    client = app.test_client()

    for path in (
        "/api/observation/status",
        "/api/observation/report",
        "/api/observation/events?limit=10",
        "/api/observation/metrics?minutes=5",
    ):
        response = client.get(path)
        print(f"{path}: {response.status_code}")
        print(json.dumps(response.json, indent=2))


if __name__ == "__main__":
    run_observation_probe()
