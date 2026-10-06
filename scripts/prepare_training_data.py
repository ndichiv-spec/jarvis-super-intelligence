"""Prepare JARVIS project data as an SFT dataset (JSONL) for fine-tuning.

This is the data-side prerequisite for "training the project LLM": it turns the
project's own *ju1ce* into conversation-style SFT examples that the model can
fine-tune on so it learns to act as JARVIS (and to carry the Claude
`~/.claude/skills` expert skills).

Sources
-------
* chat_sessions -> real multi-turn conversations (completed turns only).
* knowledge     -> grounded fact completion ("What is <key>?" -> value).
* memory        -> recalled-memory completion, scoped per user.
* skills        -> mines the Claude skill packs under ``.claude/skills``:
    - ``SKILL.md`` / ``references/*.md``: section-level Q/A
      ("What are the <skill> <heading>?" -> section body).
    - ``data/*.csv``:
      - ``prompts.csv``      -> design-style Q/A.
      - ``ux-guidelines.csv``-> Do/Don't/good-bad-code Q/A.

Usage
-----
    python scripts/prepare_training_data.py --out jarvis_data/sft_dataset.jsonl
    python scripts/prepare_training_data.py --source skills --skills-root F:/AI/.claude/skills
    python scripts/prepare_training_data.py --source chat --max-examples 500

The script is safe to re-run; it overwrites the output file.  The output JSONL
format is a list of:

    {"messages": [{"role": "user", "content": "..."},
                  {"role": "assistant", "content": "..."}],
     "metadata": {"source": "chat"|"knowledge"|"memory"|"skills", ...}}

which is directly consumable by `transformers` chat templates and `trl`'s
`SFTTrainer`.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# Make the project importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_backend.core import get_store  # noqa: E402


# --------------------------------------------------------------------------- #
# Store-backed sources (read from the SQL `jarvis_kv` layer)
# --------------------------------------------------------------------------- #
def _chat_examples(sessions: dict, max_messages: int = 64):
    """Yield one SFT example per (completed) chat session.

    Only ``COMPLETED`` assistant turns are kept so the supervised signal is
    always a real provider answer (never a fabricated/local-rule reply).
    """
    for sid, session in sessions.items():
        if not isinstance(session, dict):
            continue
        turns = []
        for m in session.get("messages") or []:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if not content or role not in ("user", "assistant"):
                continue
            if role == "assistant" and m.get("status") != "COMPLETED":
                continue
            turns.append({"role": role, "content": content})
        if len(turns) > max_messages:
            # Keep the most recent window to fit context-window budgets.
            turns = turns[-max_messages:]
        # Require at least one user/assistant pair to be a trainable example.
        has_user = any(t["role"] == "user" for t in turns)
        has_assistant = any(t["role"] == "assistant" for t in turns)
        if has_user and has_assistant:
            yield {
                "messages": turns,
                "metadata": {
                    "source": "chat",
                    "session_id": str(sid),
                    "user_id": session.get("user_id"),
                },
            }


def _knowledge_examples(knowledge: dict):
    """Turn the key/value knowledge base into fact-completion examples."""
    for key, item in knowledge.items():
        if not isinstance(item, dict):
            continue
        value = (item.get("value") or "").strip()
        if not value:
            continue
        yield {
            "messages": [
                {"role": "user", "content": f"What is {key}?"},
                {"role": "assistant", "content": value},
            ],
            "metadata": {
                "source": "knowledge",
                "key": str(key),
                "category": item.get("category"),
            },
        }


def _memory_examples(memory: dict):
    """Turn user memories into recalled-memory completion examples.

    Memories are owner-scoped: each example is tagged with its owning user so
    training never cross-contaminates users' data.
    """
    for mid, mem in memory.items():
        if not isinstance(mem, dict):
            continue
        content = (mem.get("content") or "").strip()
        if not content:
            continue
        yield {
            "messages": [
                {"role": "user",
                 "content": "What do you know about my preferences?"},
                {"role": "assistant", "content": content},
            ],
            "metadata": {
                "source": "memory",
                "memory_id": str(mid),
                "layer": mem.get("layer", "short_term"),
                "importance": mem.get("importance", 0.5),
                "user_id": mem.get("user_id"),
            },
        }


# --------------------------------------------------------------------------- #
# File-backed source: Claude ``.claude/skills`` skill packs
# --------------------------------------------------------------------------- #
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _default_skills_root() -> Path:
    """Locate the `.claude/skills` directory.

    Prefers a project-local `.claude/skills`; falls back to the sibling
    layout observed in this workspace (``<parent>/.claude/skills``).
    """
    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        project_root / ".claude" / "skills",
        project_root.parent / ".claude" / "skills",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[1]  # the sibling layout used in this workspace


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + "..."


def _strip_frontmatter(text: str):
    m = _FRONTMATTER_RE.match(text)
    if m:
        return m.group(1), text[m.end():]
    return "", text


def _frontmatter_desc(frontmatter: str, fallback_name: str) -> str:
    for line in frontmatter.splitlines():
        if line.lower().startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    for line in frontmatter.splitlines():
        if line.lower().startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return fallback_name.replace("-", " ")


def _md_sections(text: str):
    """Split markdown into (heading, body) pairs by `#` headings."""
    sections = []
    heading = None
    body = []
    for ln in text.splitlines():
        if ln.lstrip().startswith("#"):
            if heading:
                sections.append((heading, "\n".join(body).strip()))
            heading = ln.lstrip("#").strip()
            body = []
        else:
            body.append(ln)
    if heading:
        sections.append((heading, "\n".join(body).strip()))
    return sections


# Low-signal placeholder bodies that add no training value.
_PLACEHOLDER_BODIES = {
    "Implementation details", "What not to do", "Another important pattern",
    "Implementation details and examples.", "Key takeaways for using this",
}


def _md_skill_examples(skill: str, md_path: Path, root: Path,
                       max_answer_chars: int = 900):
    text = md_path.read_text(encoding="utf-8")
    rel = str(md_path.relative_to(root))
    frontmatter, rest = _strip_frontmatter(text)
    desc = _frontmatter_desc(frontmatter, skill)

    # Identity / contract example drawn from the SKILL.md frontmatter.
    yield {
        "messages": [
            {"role": "user",
             "content": f"Who are you when acting as the {skill} skill?"},
            {"role": "assistant",
             "content": (f"You are the {skill.replace('-', ' ')} expert skill. "
                         f"{desc}")},
        ],
        "metadata": {"source": "skills", "skill": skill, "file": rel,
                     "kind": "identity"},
    }

    for heading, body in _md_sections(rest):
        body = (body or "").strip()
        if not heading or len(body) < 40:
            continue
        if any(body.startswith(p) for p in _PLACEHOLDER_BODIES):
            continue
        yield {
            "messages": [
                {"role": "user",
                 "content": f"What are the {skill} {heading}?"},
                {"role": "assistant",
                 "content": _truncate(body, max_answer_chars)},
            ],
            "metadata": {"source": "skills", "skill": skill, "file": rel,
                         "heading": heading},
        }


def _csv_skill_examples(skill: str, csv_path: Path, root: Path,
                        max_answer_chars: int = 1200):
    rel = str(csv_path.relative_to(root))
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if not row:
                continue
            c = {}
            for k, v in row.items():
                if k is None:
                    continue  # overflow fields from ragged/unquoted CSV rows
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v)
                c[k] = (v or "").strip()

            # prompts.csv: design styles.
            if "Style Category" in c and "AI Prompt Keywords (Copy-Paste Ready)" in c:
                cat = c["Style Category"]
                kw = c["AI Prompt Keywords (Copy-Paste Ready)"]
                tech = c.get("CSS/Technical Keywords", "")
                chk = c.get("Implementation Checklist", "")
                vars_ = c.get("Design System Variables", "")
                parts = [kw]
                if tech:
                    parts.append("Technical keywords: " + tech)
                if chk:
                    parts.append("Implementation checklist: " + chk)
                if vars_:
                    parts.append("Design-system variables: " + vars_)
                answer = " ".join(parts)
                question = f"How do I design a {cat} interface?"
            # ux-guidelines.csv: Do/Don't/good-bad.
            elif "Issue" in c and "Do" in c:
                issue = c["Issue"]
                cat = c.get("Category", "")
                do = c.get("Do", "")
                dont = c.get("Don't", "")
                good = c.get("Code Example Good", "")
                bad = c.get("Code Example Bad", "")
                parts = []
                if do:
                    parts.append(f"Do: {do}")
                if dont:
                    parts.append(f"Don't: {dont}")
                if good:
                    parts.append(f"Good example: {good}")
                if bad:
                    parts.append(f"Bad example: {bad}")
                if not parts:
                    continue
                answer = "; ".join(parts)
                question = f"How should I handle {issue} ({cat})?" if issue else None
                if not question:
                    continue
            else:
                continue

            yield {
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant",
                     "content": _truncate(answer, max_answer_chars)},
                ],
                "metadata": {"source": "skills", "skill": skill, "file": rel,
                             "category": cat},
            }


def _skill_examples(skills_root, max_answer_chars: int = 1000):
    root = Path(skills_root)
    if not root.is_dir():
        sys.stderr.write(f"[prepare_training_data] skills root not found: {root}\n")
        return
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        skill = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            yield from _md_skill_examples(skill, skill_md, root, max_answer_chars)
        ref_dir = skill_dir / "references"
        if ref_dir.is_dir():
            for md in sorted(ref_dir.glob("*.md")):
                yield from _md_skill_examples(skill, md, root, max_answer_chars)
        data_dir = skill_dir / "data"
        if data_dir.is_dir():
            for csv in sorted(data_dir.glob("*.csv")):
                yield from _csv_skill_examples(skill, csv, root, max_answer_chars)


# --------------------------------------------------------------------------- #
# Dataset assembly
# --------------------------------------------------------------------------- #
# Source name -> the generator (closure) that yields its examples.
def _source_generator(name: str, skills_root, max_messages: int):
    """Return an iterator over examples for a named source."""
    if name == "chat":
        sessions = get_store("chat_sessions").load() or {}
        return _chat_examples(sessions, max_messages=max_messages)
    if name == "knowledge":
        return _knowledge_examples(get_store("knowledge").load() or {})
    if name == "memory":
        return _memory_examples(get_store("memory").load() or {})
    if name == "skills":
        return _skill_examples(skills_root)
    raise ValueError(f"unknown source: {name}")


_SOURCES = ("chat", "knowledge", "memory", "skills")


def build_dataset(sources=(ALL := tuple(_SOURCES)),
                  max_messages: int = 64,
                  skills_root=None) -> list:
    """Materialise SFT examples from the configured sources."""
    examples = []
    counts = {}
    for name in sources:
        gen = _source_generator(name, skills_root or _default_skills_root(),
                                max_messages)
        n = 0
        for ex in gen:
            examples.append(ex)
            n += 1
        counts[name] = n
    counts["total"] = len(examples)
    return examples, counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="jarvis_data/sft_dataset.jsonl",
                        help="output JSONL path")
    parser.add_argument("--source", default="all",
                        choices=["all", "chat", "knowledge", "memory", "skills"],
                        help="which source(s) to export")
    parser.add_argument("--max-messages", type=int, default=64,
                        help="max messages per chat session example")
    parser.add_argument("--skills-root", default=None,
                        help="directory of .claude/skills (auto-detected if omitted)")
    parser.add_argument("--max-examples", type=int, default=0,
                        help="cap total examples (0 = no cap)")
    args = parser.parse_args(argv)

    sources = (args.source,) if args.source != "all" else tuple(_SOURCES)
    examples, counts = build_dataset(
        sources=sources, max_messages=args.max_messages,
        skills_root=args.skills_root,
    )

    if args.max_examples and args.max_examples > 0:
        examples = examples[: args.max_examples]
        counts["total"] = len(examples)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Companion summary so the training script can introspect counts cheaply.
    info_path = out_path.with_suffix(".info.json")
    with info_path.open("w", encoding="utf-8") as fh:
        json.dump({"counts": counts, "output": str(out_path),
                   "sources": list(sources)}, fh, indent=2)

    print(f"[prepare_training_data] sources={list(sources)}")
    print(f"[prepare_training_data] counts={counts}")
    print(f"[prepare_training_data] wrote {len(examples)} examples -> {out_path}")
    print(f"[prepare_training_data] info -> {info_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
