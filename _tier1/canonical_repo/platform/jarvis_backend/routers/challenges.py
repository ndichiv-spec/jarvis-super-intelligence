"""Advanced Problem-Solving Arena API endpoints.

Provides managed curriculum runs that:
- Generate challenging multi-domain problems
- Have JARVIS analyze and solve them
- Use sandbox/tools for verification
- Perform adversarial testing
- Detect weaknesses and adapt difficulty
- Create verified lessons

Extends the existing curriculum API with progressive difficulty and resource governance.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from ..core import get_current_user, now_iso

router = APIRouter(prefix="/api/v1", tags=["challenges"])

log = logging.getLogger("jarvis.challenges")


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #
def _get_arena():
    """Get the Advanced Problem-Solving Arena instance."""
    try:
        from learning_arena.arena import ChallengeOrchestrator
        return ChallengeOrchestrator()
    except Exception as exc:
        log.warning("Arena not available: %s", exc)
        return None


def _problem_valid(domain: str) -> bool:
    """Validate domain against known domains."""
    try:
        from learning_arena.problem_generator import DOMAIN_CATEGORIES

        all_domains = {
            name
            for names in DOMAIN_CATEGORIES.values()
            for name in (names if isinstance(names, (list, tuple, set)) else [names])
        }
        return domain in all_domains
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# Challenge Run Management
# --------------------------------------------------------------------------- #
@router.post("/challenges/run")
async def start_challenge(
    body: dict[str, Any] = Body(default=None),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Start a new challenge run.

    Request body:
    ```json
    {
      "count": 5,
      "domains": ["Programming", "Algorithms"],
      "difficulty": 3,
      "adaptive": true,
      "resource_limit_seconds": 3600,
      "compound_domains": null
    }
    ```
    """
    arena = _get_arena()
    if arena is None:
        raise HTTPException(503, "Advanced Problem-Solving Arena not available")

    count = (body or {}).get("count", 5)
    domains = (body or {}).get("domains")
    difficulty = (body or {}).get("difficulty", 3)
    adaptive = bool((body or {}).get("adaptive", True))
    resource_limit = (body or {}).get("resource_limit_seconds", 3600)
    compound = (body or {}).get("compound_domains")

    challenge = arena.start_challenge(
        count=count,
        domains=domains,
        difficulty=difficulty,
        adaptive=adaptive,
    )

    return {
        "run_id": challenge.run_id,
        "status": "started",
        "problems_requested": challenge.problems,
        "domains": challenge.domains,
        "difficulty": challenge.difficulty,
        "adaptive": adaptive,
        "resource_limit_seconds": resource_limit,
        "compound_domains": compound,
        "started_at": now_iso(),
    }


@router.get("/challenges/{run_id}")
async def get_challenge_status(
    run_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get status of a challenge run."""
    arena = _get_arena()
    if arena is None:
        raise HTTPException(503, "Arena not available")

    challenge = arena.get_challenge(run_id)
    if challenge is None:
        raise HTTPException(404, f"Challenge {run_id} not found")

    return {
        "run_id": run_id,
        "status": challenge.to_dict(),
        "queried_at": now_iso(),
    }


@router.post("/challenges/{run_id}/execute")
async def execute_challenge(
    run_id: str,
    body: dict[str, Any] = Body(default=None),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Execute a challenge run (or individual problems within it).

    Request body:
    ```json
    {
      "problem_id": "optional-problem-id",
      "domain": "Programming",
      "difficulty": 4,
      "compound_domains": ["Programming", "Algorithms"],
      "require_sandbox": true
    }
    ```
    """
    arena = _get_arena()
    if arena is None:
        raise HTTPException(503, "Arena not available")

    challenge = arena.get_challenge(run_id)
    if challenge is None:
        raise HTTPException(404, f"Challenge {run_id} not found")

    domain = (body or {}).get("domain", "Programming")
    if not _problem_valid(domain):
        raise HTTPException(400, f"unknown domain: {domain}")

    difficulty = (body or {}).get("difficulty", challenge.difficulty)
    compound = (body or {}).get("compound_domains")
    require_sandbox = bool((body or {}).get("require_sandbox", False))

    # Run the episode
    result = arena.run_episode(
        domain=domain,
        difficulty=difficulty,
    )

    # Update challenge state
    challenge.attempted += 1
    challenge.state = "COMPLETED"
    challenge.events.append({
        "timestamp": time.time(),
        "event": "episode_completed",
        "details": {"status": result.get("status", "unknown")},
    })

    return {
        "run_id": run_id,
        "result": result,
        "challenge_status": challenge.to_dict(),
        "queried_at": now_iso(),
    }


# --------------------------------------------------------------------------- #
# Problem Generation
# --------------------------------------------------------------------------- #
@router.get("/problems/generate")
async def generate_problem(
    domain: Optional[str] = Query(None, description="Domain (e.g., Programming, Mathematics)"),
    difficulty: int = Query(3, ge=1, le=6, description="1-6 difficulty scale"),
    compound: bool = Query(False, description="Generate multi-domain problem"),
    domains: Optional[str] = Query(None, description="Comma-separated domains for compound problems"),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Generate a challenging problem for JARVIS to solve.

    Uses the curriculum generator with adaptive difficulty controls.
    """
    arena = _get_arena()
    if arena is None:
        raise HTTPException(503, "Arena not available")

    if compound and domains:
        domain_list = [d.strip() for d in domains.split(",")]
        from learning_arena.arena import MultiDomainProblemGenerator
        from learning_arena.problem_generator import DIFFICULTY_SCALE

        problem = MultiDomainProblemGenerator.generate_compound_problem(domain_list, difficulty)
    else:
        target_domain = domain or "Programming"
        if not _problem_valid(target_domain):
            target_domain = "Programming"
        problems = arena.curriculum.generator.generate(
            domain=target_domain, difficulty=difficulty, count=1
        )
        problem = problems[0] if problems else arena.curriculum._fallback_problem()

    return {
        "problem": {
            "id": problem.id,
            "title": problem.title,
            "domain": problem.domain,
            "difficulty": problem.difficulty.value,
            "question": problem.question,
            "context": problem.context,
            "constraints": problem.constraints,
            "expected_format": problem.expected_format,
            "tags": problem.tags,
        },
        "generated_at": now_iso(),
    }


# --------------------------------------------------------------------------- #
# Weakness Profiles
# --------------------------------------------------------------------------- #
@router.get("/profiles")
async def get_weakness_profiles(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get current weakness profiles for adaptive curriculum."""
    arena = _get_arena()
    if arena is None:
        raise HTTPException(503, "Arena not available")

    profiles = arena.get_profiles()
    return {
        "profiles": profiles,
        "queried_at": now_iso(),
    }


# --------------------------------------------------------------------------- #
# Adversarial Testing
# --------------------------------------------------------------------------- #
@router.get("/adversarial/edge-cases")
async def get_edge_cases(
    domain: str = Query(..., description="Domain to generate edge cases for"),
    count: int = Query(3, ge=1, le=10, description="Number of edge cases"),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate edge cases for adversarial testing."""
    from learning_arena.arena import AdversarialTester

    edge_cases = AdversarialTester.generate_edge_cases(domain, f"Problem in {domain}", count)
    return {
        "domain": domain,
        "edge_cases": edge_cases,
        "generated_at": now_iso(),
    }


# --------------------------------------------------------------------------- #
# Resource Governance
# --------------------------------------------------------------------------- #
@router.get("/resources/usage")
async def get_resource_usage(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get current resource usage for the arena."""
    arena = _get_arena()
    if arena is None:
        raise HTTPException(503, "Arena not available")

    total_problems = sum(c.attempted for c in arena._challenges.values())

    return {
        "active_challenges": len(arena._challenges),
        "problems_attempted": total_problems,
        "limits": {
            "max_problems": 100,
            "max_runtime_seconds": 3600,
            "max_model_calls": 1000,
            "max_sandbox_runs": 50,
        },
        "queried_at": now_iso(),
    }