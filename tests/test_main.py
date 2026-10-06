from __future__ import annotations

from pathlib import Path

import main


def test_slice_content_limits_lines() -> None:
    content = "one\ntwo\nthree\nfour"
    assert main._slice_content(content, start_line=2, line_count=2) == "two\nthree"


def test_read_file_returns_content_for_repo_file(capsys) -> None:
    exit_code = main.read_file(
        main.build_parser().parse_args(["read", "README.md", "--lines", "2"])
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Jarvis" in captured.out


def test_launch_backend_uses_uvicorn(monkeypatch) -> None:
    called = {}

    def fake_run(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs

    monkeypatch.setattr(main.uvicorn, "run", fake_run)

    exit_code = main.main(["launch", "--host", "127.0.0.1", "--port", "9000"])

    assert exit_code == 0
    assert called["args"] == ("api.main:create_application",)
    assert called["kwargs"]["factory"] is True
    assert called["kwargs"]["host"] == "127.0.0.1"
    assert called["kwargs"]["port"] == 9000
