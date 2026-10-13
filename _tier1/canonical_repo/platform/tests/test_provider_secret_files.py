from providers.secrets import SecretManager


def test_secret_manager_reads_mounted_secret_files_without_exposing_paths(tmp_path):
    secret_file = tmp_path / "provider-key"
    secret_file.write_text("provider-secret-value\n", encoding="utf-8")
    manager = SecretManager(env={"OPENAI_API_KEY_FILE": str(secret_file)})

    assert manager.get("OPENAI_API_KEY") == "provider-secret-value"
    secrets = manager.secrets()
    assert secrets == {"OPENAI_API_KEY": "provider-secret-value"}
    assert str(secret_file) not in secrets.values()


def test_secret_manager_fails_closed_for_missing_secret_file(tmp_path):
    manager = SecretManager(env={
        "GOOGLE_API_KEY_FILE": str(tmp_path / "missing-key"),
    })

    assert manager.get("GOOGLE_API_KEY") is None
    assert manager.secrets() == {}
