"""
API Endpoint Tests for Silverwing Backend

Run with:  python -m pytest test_api.py -v
Or:        python test_api.py
"""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

BASE = "http://localhost:8000"  # Only for manual testing; TestClient uses ASGI directly


# ---------------------------------------------------------------------------
# /api/core
# ---------------------------------------------------------------------------
class TestCore:
    def test_core_status(self):
        resp = client.get("/api/core")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ONLINE"
        assert "mode" in data
        assert "uptime_seconds" in data
        assert "version" in data

    def test_core_ping(self):
        resp = client.get("/api/core")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/core/events
# ---------------------------------------------------------------------------
class TestCoreEvents:
    def test_events(self):
        resp = client.get("/api/core/events")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# /api/core/metrics
# ---------------------------------------------------------------------------
class TestCoreMetrics:
    def test_metrics(self):
        resp = client.get("/api/core/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "uptime_seconds" in data
        assert "total_events" in data
        assert "events_per_minute" in data
        assert "active_missions" in data
        assert "total_evidence" in data
        assert "total_claims" in data
        assert "total_memories" in data


# ---------------------------------------------------------------------------
# /api/knowledge/*
# ---------------------------------------------------------------------------
class TestKnowledge:
    def test_entities(self):
        resp = client.get("/api/knowledge/entities")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if len(data) > 0:
            ent = data[0]
            assert "id" in ent
            assert "name" in ent
            assert "type" in ent
            assert "source" in ent

    def test_stats(self):
        resp = client.get("/api/knowledge/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "node_count" in data
        assert "edge_count" in data

    def test_graph(self):
        resp = client.get("/api/knowledge/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_entity(self):
        # First get the list, then fetch a specific entity
        resp = client.get("/api/knowledge/entities")
        data = resp.json()
        if len(data) > 0:
            entity_id = data[0]["id"]
            resp2 = client.get(f"/api/knowledge/entities/{entity_id}")
            assert resp2.status_code == 200
            ent = resp2.json()
            assert "id" in ent
            assert "name" in ent
            assert "type" in ent
            assert "source" in ent

    def test_knowledge_get(self):
        resp = client.get("/api/knowledge/entities")
        data = resp.json()
        if len(data) > 0:
            entity_id = data[0]["id"]
            resp2 = client.get(f"/api/knowledge/get/{entity_id}")
            assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# /api/agents/*
# ---------------------------------------------------------------------------
class TestAgents:
    def test_definitions(self):
        resp = client.get("/api/agents/definitions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_instances(self):
        resp = client.get("/api/agents/instances")
        assert resp.status_code == 200
        data = resp.json()
        # Backend wraps in {"agents": [...]}
        assert "agents" in data
        agents = data["agents"]
        assert isinstance(agents, list)
        if len(agents) > 0:
            agent = agents[0]
            assert "id" in agent
            assert "name" in agent
            assert "status" in agent

    def test_agent_instance(self):
        resp = client.get("/api/agents/instances")
        data = resp.json()
        agents = data.get("agents", [])
        if len(agents) > 0:
            agent_id = agents[0]["id"]
            resp2 = client.get(f"/api/agents/instances/{agent_id}")
            assert resp2.status_code == 200
            agent = resp2.json()
            assert "id" in agent
            assert "name" in agent
            assert "status" in agent


# ---------------------------------------------------------------------------
# /api/tools/*
# ---------------------------------------------------------------------------
class TestTools:
    def test_list(self):
        resp = client.get("/api/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_executions(self):
        resp = client.get("/api/tools/executions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_tool(self):
        resp = client.get("/api/tools")
        data = resp.json()
        if len(data) > 0:
            tool_id = data[0]["id"]
            resp2 = client.get(f"/api/tools/{tool_id}")
            assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# /api/evidence
# ---------------------------------------------------------------------------
class TestEvidence:
    def test_list(self):
        resp = client.get("/api/evidence")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if len(data) > 0:
            ev = data[0]
            assert "claim_text" in ev
            assert "source" in ev

    def test_get(self):
        resp = client.get("/api/evidence")
        data = resp.json()
        if len(data) > 0:
            evidence_id = data[0]["id"]
            resp2 = client.get(f"/api/evidence/{evidence_id}")
            assert resp2.status_code == 200
            ev = resp2.json()
            assert "claim_text" in ev
            assert "source" in ev


# ---------------------------------------------------------------------------
# /api/claims
# ---------------------------------------------------------------------------
class TestClaims:
    def test_list(self):
        resp = client.get("/api/claims")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get(self):
        resp = client.get("/api/claims")
        data = resp.json()
        if len(data) > 0:
            claim_id = data[0]["id"]
            resp2 = client.get(f"/api/claims/{claim_id}")
            assert resp2.status_code == 200
            claim = resp2.json()
            assert "text" in claim
            assert "status" in claim


# ---------------------------------------------------------------------------
# /api/citations
# ---------------------------------------------------------------------------
class TestCitations:
    def test_list(self):
        resp = client.get("/api/citations")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get(self):
        resp = client.get("/api/citations")
        data = resp.json()
        if len(data) > 0:
            citation_id = data[0]["id"]
            resp2 = client.get(f"/api/citations/{citation_id}")
            assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# /api/memory
# ---------------------------------------------------------------------------
class TestMemory:
    def test_list(self):
        resp = client.get("/api/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get(self):
        resp = client.get("/api/memory")
        data = resp.json()
        if len(data) > 0:
            mem_id = data[0]["id"]
            resp2 = client.get(f"/api/memory/{mem_id}")
            assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# /api/research/connectors
# ---------------------------------------------------------------------------
class TestResearch:
    def test_connectors(self):
        resp = client.get("/api/research/connectors")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# /api/laboratory/model
# ---------------------------------------------------------------------------
class TestLaboratory:
    def test_model(self):
        resp = client.get("/api/laboratory/model")
        assert resp.status_code == 200
        data = resp.json()
        assert "parameters" in data


# ---------------------------------------------------------------------------
# /api/observatory/*
# ---------------------------------------------------------------------------
class TestObservatory:
    def test_stream(self):
        resp = client.get("/api/observatory/stream")
        assert resp.status_code == 200

    def test_agents(self):
        resp = client.get("/api/observatory/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_tools(self):
        resp = client.get("/api/observatory/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# /api/missions/*
# ---------------------------------------------------------------------------
class TestMissions:
    def test_list(self):
        resp = client.get("/api/missions")
        assert resp.status_code == 200
        data = resp.json()
        # Backend wraps in {"missions": [...]}
        assert "missions" in data
        missions = data["missions"]
        assert isinstance(missions, list)
        if len(missions) > 0:
            mission = missions[0]
            assert "id" in mission
            assert "title" in mission
            assert "status" in mission

    def test_get(self):
        resp = client.get("/api/missions")
        data = resp.json()
        missions = data.get("missions", [])
        if len(missions) > 0:
            mission_id = missions[0]["id"]
            resp2 = client.get(f"/api/missions/{mission_id}")
            assert resp2.status_code == 200
            mission = resp2.json()
            assert "id" in mission
            assert "title" in mission
            assert "status" in mission


# ---------------------------------------------------------------------------
# Sandbox (item: sandboxed code execution)
# ---------------------------------------------------------------------------
class TestSandbox:
    def test_execute_ok(self):
        resp = client.post("/api/tools/invoke", json={
            "tool": "code_executor",
            "input": {"code": "x = 40 + 2\nprint(x)"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["output_data"]["result"] == "ok"
        assert "42" in data["output_data"]["stdout"]

    def test_execute_blocked_import(self):
        resp = client.post("/api/tools/invoke", json={
            "tool": "code_executor",
            "input": {"code": "import os\nprint(os.getcwd())"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["output_data"]["result"] == "error"
        assert data["output_data"]["error"]

    def test_execute_timeout(self):
        resp = client.post("/api/tools/invoke", json={
            "tool": "code_executor",
            "input": {"code": "while True: pass", "timeout": 2},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["output_data"]["result"] == "error"
        assert "Timeout" in data["output_data"]["error"]


# ---------------------------------------------------------------------------
# /api/orchestrator + /api/agents/spawn (item: agent execution engine)
# ---------------------------------------------------------------------------
class TestOrchestrator:
    def test_state(self):
        resp = client.get("/api/orchestrator/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "active_missions" in data
        assert "mission_ids" in data or "active_mission_ids" in data


# ---------------------------------------------------------------------------
# /api/evaluation/run (item: continual improvement / evaluation loop)
# ---------------------------------------------------------------------------
class TestEvaluation:
    def test_run_report(self):
        resp = client.get("/api/evaluation/run")
        assert resp.status_code == 200
        report = resp.json()
        assert report["scope"] == "alpha_eval_v1"
        assert "report_id" in report
        assert "timestamp" in report
        names = {c["name"] for c in report["checks"]}
        assert {"core_status", "db_integrity", "tool_engine", "sandbox", "connectors", "orchestrator"} <= names
        assert all(c["status"] == "ok" for c in report["checks"])
        assert report["overall"] == "pass"
        assert report["total_checks"] == report["passed"]


# ---------------------------------------------------------------------------
# /api/verification + verifier agent (item: verification engine)
# ---------------------------------------------------------------------------
class TestVerification:
    def test_verify_strong_mission(self):
        from main import Claim, Evidence, Mission, _verify_mission, generate_id
        mid = generate_id()
        mission = Mission(id=mid, title="t", query="q")
        ev = Evidence(id=generate_id(), claim_text="source", evidence_text="text", confidence=0.9)
        claim = Claim(id=generate_id(), text="supported conclusion", confidence=0.8,
                      evidence_ids=[ev.id], supporting_count=2, source_ids=["s1"], mission_id=mid)
        report = _verify_mission(mission, claims=[claim], evidence={ev.id: ev})
        assert report["verdict"] == "verified"
        assert report["score"] >= 0.6
        assert report["checked_claims"] == 1
        assert report["unsupported_claims"] == []

    def test_verify_flags_unsupported_claim(self):
        from main import Claim, Mission, _verify_mission, generate_id
        mid = generate_id()
        mission = Mission(id=mid, title="t", query="q")
        weak = Claim(id=generate_id(), text="unsupported assertion", confidence=0.3, mission_id=mid)
        report = _verify_mission(mission, claims=[weak], evidence={})
        assert report["verdict"] == "flagged"
        assert weak.id in report["unsupported_claims"]
        assert weak.id in report["low_confidence_claims"]
        assert "lack supporting evidence" in report["notes"][0]

    def test_verify_empty_mission_flags(self):
        from main import Mission, _verify_mission, generate_id
        mission = Mission(id=generate_id(), title="t", query="q")
        report = _verify_mission(mission, claims=[], evidence={})
        assert report["verdict"] == "flagged"
        assert report["checked_claims"] == 0

    def test_verify_tool_endpoint_updates_claims(self):
        from main import Claim, Evidence, Mission, db, generate_id
        mid = generate_id()
        mission = Mission(id=mid, title="t", query="q")
        db.missions[mid] = mission
        ev = Evidence(id=generate_id(), claim_text="s", evidence_text="e", confidence=0.9)
        db.evidence[ev.id] = ev
        strong = Claim(id=generate_id(), text="ok", confidence=0.8, evidence_ids=[ev.id],
                       supporting_count=1, source_ids=["s1"], mission_id=mid)
        db.claims[strong.id] = strong
        mission.claims = [strong.id]
        resp = client.post("/api/tools/invoke", json={
            "tool": "verify", "input": {"mission_id": mid},
        })
        assert resp.status_code == 200
        assert resp.json()["output_data"]["verdict"] == "verified"
        assert db.claims[strong.id].status == "verified"
        assert db.claims[strong.id].verified_at is not None

    def test_verification_status_endpoint(self):
        resp = client.get("/api/verification/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "missions_checked" in data
        assert "verified" in data
        assert "flagged" in data
        assert "reports" in data


# ---------------------------------------------------------------------------
# /api/models/health + /api/models/route (Silverwing Model Gateway)
# ---------------------------------------------------------------------------
class TestModelsGateway:
    def test_health(self):
        resp = client.get("/api/models/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["providers"], dict)
        # local and silverwing are available in the test env
        assert "local" in data["providers"]
        assert data["providers"]["local"]["available"] is True
        assert "silverwing" in data["providers"]
        assert data["providers"]["silverwing"]["available"] is True

    def test_health_provider_fields(self):
        resp = client.get("/api/models/health")
        assert resp.status_code == 200
        data = resp.json()
        for name, info in data["providers"].items():
            assert "status" in info
            assert "available" in info
            assert "authorized" in info
            assert "model" in info

    def test_route_default(self):
        resp = client.post("/api/models/route", json={})
        assert resp.status_code == 200
        decision = resp.json()
        assert "selected_model" in decision
        assert "provider" in decision
        assert "reason" in decision
        assert "success" in decision
        assert decision["success"] is True

    def test_route_with_task(self):
        resp = client.post("/api/models/route", json={
            "task": "fast_response",
            "requested_privacy": "private",
            "requested_cost": "low_cost",
        })
        assert resp.status_code == 200
        decision = resp.json()
        assert decision["success"] is True
        assert decision["selected_model"] is not None

    def test_route_private_falls_back_local(self):
        resp = client.post("/api/models/route", json={
            "task": "",
            "requested_capability": "",
            "requested_privacy": "private",
            "requested_cost": "local_only",
            "requested_latency": "low_latency",
        })
        assert resp.status_code == 200
        decision = resp.json()
        assert decision["success"] is True
        assert decision["provider"] == "local"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
