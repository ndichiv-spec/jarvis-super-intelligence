"""Static smoke checks for the legacy dashboard template."""

from pathlib import Path


def test_dashboard_template_contains_primary_panels():
    template = (
        Path(__file__).resolve().parents[1]
        / "frontend"
        / "templates"
        / "index.html"
    )
    content = template.read_text(encoding="utf-8")

    for panel_id in ("chatPanel", "processesPanel", "filesPanel", "knowledgePanel"):
        assert f'id="{panel_id}"' in content
