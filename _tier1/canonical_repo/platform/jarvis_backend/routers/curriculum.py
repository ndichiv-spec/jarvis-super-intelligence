"""Governed curriculum API — Hub registry role + Teacher Mesh + learning loop.

Exposes the real, wire-once surfaces of the governed learning lifecycle
(spec §25-§31, §9) on a single router:

* Hub registry role (``providers/huggingface/hub.py``): real ``whoami`` auth
  probe + live model discovery from ``huggingface.co/api``. Feed records into
  the model-lifecycle registry (``model_lifecycle``).
* Teacher Mesh (``teacher_mesh``): health-gated selection of live provider
  adapters; never invents a "teacher" that is not ``HEALTHY``.
* Episodes (``learning_arena.learning_loop``): deterministic generator ->
  teacher solve -> sandbox verification -> lesson gate -> immutable dataset
  revisions.
* Model lifecycle + training: lineage and human-gated promotion; launching a
  training run requires a real ``remote_target`` (local PC only orchestrates).

Honesty rules: no fabricated results, no secrets returned, live probes are
opt-in (``?probe=true``) except endpoints whose entire point is a probe.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from ..core import DATA_DIR, get_current_user, now_iso

router = APIRouter(prefix="/api/v1", tags=["curriculum"])

log = logging.getLogger("jarvis.curriculum")

_CURRICULUM_DIR = DATA_DIR / "curriculum"
_CURRICULUM_DIR.mkdir(parents=True, exist_ok=True)
_DATASET_STORE = _CURRICULUM_DIR / "datasets.jsonl"


# --------------------------------------------------------------------------- #
# Helpers — heavy imports are lazy so importing the router never touches network
# --------------------------------------------------------------------------- #
def _hf_adapter() -> Optional[Any]:
    """The live HuggingFace adapter from the fabric, or a fresh instance."""
    try:
        from providers.registry import get_registry

        existing = get_registry().get("hf")
        if existing is not None:
            return existing
    except Exception:  # noqa: BLE001 — fabric may not be bootstrapped
        pass
    try:
        from providers.huggingface.client import HuggingFaceAdapter

        return HuggingFaceAdapter()
    except Exception as exc:  # noqa: BLE001
        log.warning("hf adapter unavailable: %s", exc)
        return None


def _adapters_map() -> dict[str, Any]:
    try:
        from providers.bootstrap import build_adapters

        return build_adapters()
    except Exception as exc:  # noqa: BLE001
        log.warning("fabric adapters unavailable: %s", exc)
        return {}


_SEEDED_REGISTRY = False


def _lifecycle_registry() -> Any:
    global _SEEDED_REGISTRY
    from model_lifecycle.registry import ModelRegistry  # type: ignore[import-not-found]

    store = DATA_DIR / "model_lifecycle" / "model_lifecycle.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    registry = ModelRegistry(store_path=store)
    if not _SEEDED_REGISTRY:
        try:
            from model_lifecycle.discovery import (  # type: ignore[import-not-found]
                seed_brain_lineage,
                seed_silverwing,
            )

            seed_brain_lineage(registry)
            seed_silverwing(registry)
            _SEEDED_REGISTRY = True
        except Exception as exc:  # noqa: BLE001 — seeding is best-effort
            log.warning("model lifecycle seed failed: %s", exc)
    return registry


def _lesson_gate() -> Any:
    from learning_arena.lesson_gate import LessonGate  # type: ignore[import-not-found]

    return LessonGate()


def _dataset_builder(gate: Any) -> Any:
    from learning_arena.dataset_builder import CurriculumDatasetBuilder  # type: ignore[import-not-found]

    return CurriculumDatasetBuilder(gate=gate, store_path=_DATASET_STORE)


def _mesh(adapters: Optional[dict[str, Any]] = None) -> Any:
    from teacher_mesh.mesh import TeacherMesh  # type: ignore[import-not-found]

    return TeacherMesh(adapters=adapters if adapters is not None else _adapters_map())


def _domain_valid(domain: str) -> bool:
    try:
        from learning_arena.problem_generator import DOMAIN_CATEGORIES  # type: ignore[import-not-found]

        all_domains = {
            name
            for names in DOMAIN_CATEGORIES.values()
            for name in (names if isinstance(names, (list, tuple, set)) else [names])
        }
        return domain in all_domains
    except Exception:  # noqa: BLE001
        return True  # non-blocking: generator validates anyway


# --------------------------------------------------------------------------- #
# Hub registry role (spec §9 / §13 / §45)
# --------------------------------------------------------------------------- #
@router.get("/hub/health")
async def hub_status(
    probe: bool = Query(
        False,
        description="Live-probe the HF registry (whoami + auth health). Off by default.",
    ),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    adapter = _hf_adapter()
    if adapter is None:
        raise HTTPException(503, "huggingface adapter not available")
    if not adapter.configured:
        return {
            "generated_at": now_iso(),
            "configured": False,
            "role": "registry",
            "health": {"status": "not_configured",
                       "detail": "No HF token configured (JARVIS_HF_TOKEN)."},
            "identity": None,
        }
    health = adapter.hub_health(force=True) if probe else adapter.hub_health(force=False)
    identity = None
    if probe and health.status == "healthy":
        try:
            who = adapter.hub_identity()
            identity = {
                "type": who.get("type", "unknown"),
                "name": who.get("name", ""),
                "fullname": who.get("fullname", ""),
                "org": (who.get("org") or {}).get("name") if isinstance(who.get("org"), dict) else None,
            }
        except Exception as exc:  # noqa: BLE001 — identity best-effort
            log.warning("hub identity probe failed: %s", exc)
    return {
        "generated_at": now_iso(),
        "configured": True,
        "probe": probe,
        "role": "registry",
        "health": health.to_dict(),
        "identity": identity,
    }


@router.get("/hub/models")
async def hub_models(
    search: Optional[str] = Query(None, max_length=100),
    author: Optional[str] = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=200),
    pipeline_tag: Optional[str] = Query(None, max_length=50),
    seed: bool = Query(False, description="Also feed the model-lifecycle registry."),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    adapter = _hf_adapter()
    if adapter is None:
        raise HTTPException(503, "huggingface adapter not available")
    try:
        rows = adapter.discover_models(
            search=search or "", author=author or "", limit=limit, pipeline_tag=pipeline_tag or ""
        )
    except Exception as exc:  # noqa: BLE001 — classify known hub errors
        raise HTTPException(502, f"hub discovery failed: {exc}") from exc
    models = [r if isinstance(r, dict) else asdict(r) for r in rows]
    for m in models:
        m["capabilities"] = sorted(str(c.value if hasattr(c, "value") else c) for c in m["capabilities"])
        m["tags"] = sorted(m["tags"]) if isinstance(m["tags"], (set, frozenset)) else m["tags"]

    registry_seeded = 0
    if seed:
        try:
            from model_lifecycle.discovery import seed_huggingface_discovery  # type: ignore[import-not-found]

            reg = _lifecycle_registry()
            seed_huggingface_discovery(adapter, search=search or "", limit=limit)
            registry_seeded = len(reg.all_records())
        except Exception as exc:  # noqa: BLE001 — registry best-effort
            log.warning("registry seed failed: %s", exc)

    return {
        "generated_at": now_iso(),
        "count": len(models),
        "source": "huggingface-hub",
        "models": models,
        "registry_records": registry_seeded,
    }


# --------------------------------------------------------------------------- #
# Teacher Mesh (spec §30)
# --------------------------------------------------------------------------- #
@router.get("/teachers")
async def teachers_status(
    refresh: bool = Query(False, description="Force probe adapters before reporting."),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    mesh = _mesh()
    mesh.refresh(force=refresh)
    return mesh.mesh_status()


# --------------------------------------------------------------------------- #
# Episodes (spec §31)
# --------------------------------------------------------------------------- #
@router.post("/episodes", status_code=200)
async def run_episode(
    body: Dict[str, Any] = Body(default=None),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    domain = (body or {}).get("domain") or "Programming"
    if not _domain_valid(domain):
        raise HTTPException(400, f"unknown domain: {domain}")
    difficulty = (body or {}).get("difficulty", 3)
    publish_dataset = bool((body or {}).get("publish_dataset", True))
    seed = (body or {}).get("seed")
    with_student = bool((body or {}).get("student_run", False))

    try:
        from learning_arena.problem_generator import ProblemGenerator  # type: ignore[import-not-found]
        from learning_arena.dataset_builder import CurriculumDatasetBuilder  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"learning arena not importable: {exc}") from exc

    gate = _lesson_gate()
    builder = CurriculumDatasetBuilder(gate=gate, store_path=_DATASET_STORE)
    mesh = _mesh()

    student_runner = None
    if with_student:
        try:
            from research_engine.tool_registry import ChatRunner  # type: ignore[import-not-found]

            ok = mesh.available(capabilities={"chat"})
            if ok:
                def _student(q: str) -> dict[str, Any]:
                    t = mesh.select(capabilities={"chat"})
                    return mesh.solve({"question": q}, teacher_key=t.key)
                student_runner = _student
        except Exception:  # noqa: BLE001 — student is optional
            student_runner = None

    from learning_arena.learning_loop import LearningLoop  # type: ignore[import-not-found]

    loop = LearningLoop(
        generator=ProblemGenerator(seed=seed),
        mesh=mesh,
        gate=gate,
        dataset_builder=builder,
        student_runner=student_runner,
    )
    episode = loop.run_episode(
        domain=domain,
        difficulty=difficulty,
        seed=seed,
        student_runner=student_runner,
        publish_dataset=publish_dataset,
        artifact_domain=domain,
    )
    result = episode.to_dict()
    result["meta"] = {"dataset_store": str(_DATASET_STORE)}
    if result.get("status") == "NO_HEALTHY_TEACHER":
        raise HTTPException(503, "no healthy teacher available (mesh requires a HEALTHY adapter)")
    return result


# --------------------------------------------------------------------------- #
# Datasets (spec §28)
# --------------------------------------------------------------------------- #
@router.get("/datasets")
async def datasets_list(
    dataset_id: Optional[str] = Query(None),
    version: Optional[int] = Query(None, ge=1),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    builder = _dataset_builder(_lesson_gate())
    if dataset_id:
        if version:
            revision = builder.get(dataset_id, version)
            if revision is None:
                raise HTTPException(404, f"revision {dataset_id} v{version} not found")
            return revision.to_dict()
        latest = builder.latest(dataset_id)
        if latest is None:
            raise HTTPException(404, f"dataset {dataset_id} not found")
        return latest.to_dict()
    revisions = [r.to_dict() for r in builder.all_datasets()]
    return {"generated_at": now_iso(), "count": len(revisions), "datasets": revisions}


# --------------------------------------------------------------------------- #
# Model lifecycle (spec §25)
# --------------------------------------------------------------------------- #
@router.get("/models/revisions")
async def model_revisions(
    lifecycle_type: Optional[str] = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        reg = _lifecycle_registry()
        records = reg.all_records()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"registry unavailable: {exc}") from exc
    if lifecycle_type:
        try:
            from model_lifecycle.types import ModelLifecycleType  # type: ignore[import-not-found]

            lifecycle = ModelLifecycleType(lifecycle_type)
        except Exception:  # noqa: BLE001
            raise HTTPException(400, f"unknown lifecycle_type: {lifecycle_type}") from None
        records = [r for r in records if r.lifecycle_type is lifecycle]
    return {
        "generated_at": now_iso(),
        "count": len(records),
        "records": [r.to_dict() for r in records],
    }


@router.get("/models/{record_id}/lineage")
async def model_lineage(
    record_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        reg = _lifecycle_registry()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"registry unavailable: {exc}") from exc
    if reg.get(record_id) is None:
        raise HTTPException(404, f"record {record_id} not found")
    return {"record_id": record_id, "lineage": reg.lineage(record_id)}


# --------------------------------------------------------------------------- #
# Training (spec §29; local PC orchestrates, training runs remotely)
# --------------------------------------------------------------------------- #
@router.post("/training/runs", status_code=200)
async def launch_training(
    body: Dict[str, Any] = Body(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    remote_target = (body or {}).get("remote_target") or ""
    dataset_ids = (body or {}).get("dataset_ids") or []
    if not remote_target:
        raise HTTPException(400, "remote_target is required (local PC only orchestrates)")
    if not dataset_ids:
        raise HTTPException(400, "dataset_ids is required — no dataset, no training")
    try:
        from model_lifecycle.training import TrainingLifecycle  # type: ignore[import-not-found]
        from model_lifecycle.types import ModelLifecycleType  # type: ignore[import-not-found]
        from model_lifecycle.discovery import seed_brain_lineage  # type: ignore[import-not-found]
        from model_lifecycle import registry as _reg

        reg = _lifecycle_registry()
        if not reg.all_records():
            seed_brain_lineage(reg)
        base_record_id = (body or {}).get("base_record_id") or ""
        if not base_record_id:
            bases = [r for r in reg.list_by_type(ModelLifecycleType.JARVIS_BASE)]
            if len(bases) != 1:
                raise HTTPException(
                    409,
                    "exactly one JARVIS_BASE required — pass base_record_id explicitly",
                )
            base_record_id = bases[0].record_id

        lifecycle = TrainingLifecycle(reg)
        run = lifecycle.launch(
            base_record_id=base_record_id,
            remote_target=remote_target,
            dataset_ids=[str(d) for d in dataset_ids],
            actor=_user_id(user),
            model_name=(body or {}).get("model_name") or None,
            hyperparameters=(body or {}).get("hyperparameters"),
            lifecycle_type=ModelLifecycleType(
                (body or {}).get("lifecycle_type", "jarvis_candidate")
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — expose honest enrollment errors
        raise HTTPException(409, f"training launch failed: {exc}") from exc
    return run.to_dict()


@router.get("/training/runs")
async def training_runs(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        from model_lifecycle.training import TrainingLifecycle  # type: ignore[import-not-found]

        lifecycle = TrainingLifecycle(_lifecycle_registry())
        runs = lifecycle.runs()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"training store unavailable: {exc}") from exc
    return {"generated_at": now_iso(), "count": len(runs), "runs": [r.to_dict() for r in runs]}


def _user_id(user: dict[str, Any]) -> str:
    return str(user.get("id") or user.get("email") or "unknown-user")