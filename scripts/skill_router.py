#!/usr/bin/env python3
"""Deterministic, low-context router for project Agent Skills.

The router reads skill metadata locally and returns only a bounded activation
plan. It never imports or executes code from a skill directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from common import ROOT


SKILLS_ROOT = ROOT / ".agents" / "skills"
CANONICAL = {
    "grill-me": "grilling",
}
ALIASES = {
    "grill me": "grilling",
    "karpathy": "karpathy-guidelines",
    "last 30 days": "last30days",
    "last30days": "last30days",
    "superpowers": "using-superpowers",
    "obsidian": "obsidian-markdown",
}

RUNTIME_CONFIG = ROOT / ".harness" / "runtime.json"


def load_profiles() -> dict[str, dict]:
    try:
        configured = json.loads(RUNTIME_CONFIG.read_text(encoding="utf-8"))[
            "routing_profiles"
        ]
        profiles = {
            name: {
                "max_skills": int(values["max_active_skills"]),
                "max_steps": int(values["max_steps"]),
                "instruction_style": str(values["instruction_style"]),
                "escalate_below_confidence": float(
                    values["escalate_below_confidence"]
                ),
            }
            for name, values in configured.items()
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid harness runtime config: {exc}") from exc
    if "balanced" not in profiles or any(
        values["max_skills"] < 1 or values["max_steps"] < 1
        for values in profiles.values()
    ):
        raise SystemExit("Invalid harness runtime config: unusable routing profiles")
    return profiles


PROFILES = load_profiles()

# Rules are deliberately explicit. Weak/local models receive the same plan as
# strong models, and adding a skill remains a reviewable config/code change.
SIGNALS: tuple[tuple[str, tuple[str, ...], int, str], ...] = (
    ("llm-wiki-maintenance", ("llm wiki", "project wiki", "knowledge base", "wiki index", "kb_search", "kb_get"), 96, "project knowledge maintenance requested"),
    ("openspec-change", ("openspec", "spec driven", "spec-driven", "behavioral spec", "context-impact"), 97, "OpenSpec/spec-driven change requested"),
    ("project-exploration", ("understand this project", "explore repository", "project orientation", "project map", "unfamiliar repository"), 91, "bounded project orientation requested"),
    ("architecture-design", ("architecture design", "system architecture", "design architecture", "adr", "architecture review"), 90, "architecture work requested"),
    ("java-maven-jar-analysis", ("maven dependency", "maven dependencies", "maven project", "maven coordinate", "jar contents", "jar api", "javap", "jdeps", "mvn dependency:tree", "pom.xml"), 94, "Java/Maven/JAR inspection requested"),
    ("humanizer", ("humanize", "ai sounding", "sound natural", "natural prose"), 100, "prose rewrite requested"),
    ("grilling", ("grill me", "stress test this plan", "interrogate this plan", "challenge my plan"), 100, "requirements stress-test requested"),
    ("graphify", ("graphify", "knowledge graph", "dependency graph across"), 100, "knowledge-graph analysis requested"),
    ("last30days", ("last 30 days", "past 30 days", "recent trend", "what changed lately"), 95, "freshness-bounded research requested"),
    ("obsidian-cli", ("obsidian cli", "search my vault", "manage my vault", "obsidian vault"), 95, "Obsidian vault operation requested"),
    ("obsidian-bases", ("obsidian base", ".base file", "card view", "database view in obsidian"), 96, "Obsidian Base artifact detected"),
    ("obsidian-markdown", ("wikilink", "obsidian markdown", "callout", "frontmatter"), 88, "Obsidian-flavored Markdown requested"),
    ("json-canvas", ("json canvas", ".canvas file", "obsidian canvas"), 96, "JSON Canvas artifact detected"),
    ("hermes-delegation", ("delegate to hermes", "hermes worker", "remote hermes"), 100, "native Hermes delegation requested"),
    ("delegation", ("delegate", "subagent", "parallel agent", "independent worker"), 70, "bounded delegation may help"),
    ("dispatching-parallel-agents", ("parallel agents", "parallel subagents", "independent tasks in parallel"), 86, "independent parallel work requested"),
    ("subagent-driven-development", ("subagent driven", "execute with subagents"), 90, "subagent-driven execution requested"),
    ("skill-creator", ("create a skill", "write a skill", "update the skill", "optimize the skill", "skill eval"), 95, "skill authoring or optimization requested"),
    ("repo-recon", ("repo recon", "repository profile", "detect the toolchain", "detect build and test"), 93, "deterministic repository profile requested"),
    ("context-builder", ("context pack", "contextpack", "bounded context", "model handoff"), 93, "bounded evidence handoff requested"),
    ("cache-aware-context", ("prompt cache", "cache prefix", "cache hit", "token cost", "context compaction"), 92, "cache-aware prompt topology requested"),
    ("using-superpowers", ("use superpowers", "/superpowers", "$superpowers"), 100, "Superpowers explicitly requested"),
    ("brainstorming", ("brainstorm", "explore design options", "unclear product idea"), 72, "consequential design choices remain open"),
    ("writing-plans", ("write an implementation plan", "implementation plan", "plan this change"), 76, "multi-step implementation planning requested"),
    ("executing-plans", ("execute this plan", "implement the written plan"), 82, "written plan execution requested"),
    ("systematic-debugging", ("intermittent", "flaky", "unexpected behavior", "test failure", "failing", "bug"), 86, "failure requires evidence-first diagnosis"),
    ("investigate-first", ("investigate", "diagnose", "root cause", "why is"), 75, "cause is not yet established"),
    ("surgical-patch", ("fix", "bugfix", "small behavior change", "regression"), 72, "narrow behavior fix requested"),
    ("test-driven-development", ("regression test", "test first", "tdd", "add a test"), 78, "executable behavior proof is practical"),
    ("safe-refactor", ("refactor", "restructure", "extract", "consolidate", "cleanup code"), 84, "behavior-preserving structural change requested"),
    ("migration", ("migration", "schema change", "compatibility transition", "data backfill"), 88, "reversible compatibility transition requested"),
    ("code-reviewer", ("review this code", "review the diff", "code review", "audit this", "review for regressions"), 88, "independent review requested"),
    ("receiving-code-review", ("review feedback", "review comment", "address reviewer", "implement feedback"), 91, "review feedback requires verification"),
    ("requesting-code-review", ("request review", "ready for review", "before merging"), 82, "completion review gate requested"),
    ("caveman-review", ("compressed code review", "brief code review", "one line per finding"), 94, "compressed review format requested"),
    ("caveman-compress", ("caveman compress", "compress claude.md", "compress memory file"), 98, "memory-file compression requested"),
    ("caveman", ("caveman mode", "talk like caveman", "less tokens", "be ultra brief"), 90, "compressed communication requested"),
    ("verification", ("verify", "test", "check", "prove", "regression"), 66, "task calls for concrete evidence"),
    ("verify-and-stop", ("verify only", "validation only", "do not change", "check completion"), 92, "validation-only scope requested"),
    ("verification-before-completion", ("finish branch", "before commit", "before pr", "before merge"), 73, "final Superpowers evidence gate may apply"),
    ("finishing-a-development-branch", ("finish this branch", "merge this branch", "branch complete"), 91, "branch integration decision requested"),
    ("using-git-worktrees", ("git worktree", "isolated worktree", "new worktree"), 94, "isolated Git worktree requested"),
    ("lean-build", ("implement", "build feature", "add feature", "new behavior", "integration"), 55, "feature work benefits from strict scope"),
    ("karpathy-guidelines", ("implement", "write code", "change code", "fix", "refactor", "review code"), 54, "coding task benefits from surgical assumptions and success criteria"),
    ("solution-retrospective", ("retrospective", "self improvement", "learn from this", "durable lesson"), 91, "durable learning was requested"),
    ("web-research-routing", ("web research", "search the web", "research online", "browse the internet"), 88, "public web research requested"),
    ("ponytail", ("ponytail", "yagni", "be lazy", "lazy mode"), 92, "minimal implementation posture requested"),
    ("defuddle", ("read this webpage", "extract this page", "clean this webpage"), 78, "known web page needs compact extraction"),
)

DEPENDENCIES = {
    "hermes-delegation": ("delegation", "harness-project-access"),
    "delegation": ("context-builder",),
    "dispatching-parallel-agents": ("delegation",),
    "subagent-driven-development": ("delegation",),
    "verification-before-completion": ("verification",),
    "requesting-code-review": ("code-reviewer",),
    "caveman-review": ("code-reviewer",),
}

PREFER = {
    frozenset(("grilling", "grill-me")): "grilling",
    frozenset(("verify-and-stop", "verification-before-completion")): "verify-and-stop",
    frozenset(("caveman-review", "code-reviewer")): "caveman-review",
}

STOPWORDS = {
    "about", "after", "agent", "before", "change", "create", "from", "project",
    "request", "skill", "task", "that", "this", "when", "with", "work", "working",
}


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path


def normalize(value: str) -> str:
    value = value.lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.+/$ ]+", " ", value)).strip()


def frontmatter(path: Path) -> tuple[str, str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return path.parent.name, ""
    data: dict[str, str] = {}
    index = 1
    while index < len(lines) and lines[index].strip() != "---":
        line = lines[index]
        match = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if not match:
            index += 1
            continue
        key, value = match.groups()
        if value in {">", "|", ">-", "|-"}:
            parts: list[str] = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index][:1].isspace()):
                if lines[index].strip():
                    parts.append(lines[index].strip())
                index += 1
            data[key] = " ".join(parts)
            continue
        data[key] = value.strip().strip('"').strip("'")
        index += 1
    return data.get("name", path.parent.name), data.get("description", "")


def discover() -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    for path in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        name, description = frontmatter(path)
        name = CANONICAL.get(name, name)
        candidate = Skill(name=name, description=description, path=path)
        # Prefer the canonical-named directory over a deprecated alias.
        current = skills.get(name)
        if current is None or path.parent.name == name:
            skills[name] = candidate
    return skills


def explicit_names(task: str, skills: dict[str, Skill]) -> set[str]:
    normalized = normalize(task)
    selected: set[str] = set()
    for raw_name in skills:
        phrase = normalize(raw_name)
        markers = (
            f"use {phrase}", f"using {phrase}", f"/{phrase}", f"${phrase}",
            f"skill {phrase}", f"{phrase} skill",
        )
        if any(marker in normalized for marker in markers):
            selected.add(CANONICAL.get(raw_name, raw_name))
    for alias, canonical in ALIASES.items():
        if normalize(alias) in normalized and (
            "use " + normalize(alias) in normalized
            or "skill" in normalized
            or canonical in {"grilling", "last30days"}
        ):
            selected.add(canonical)
    return selected


def lexical_score(task: str, skill: Skill) -> int:
    task_tokens = set(normalize(task).split()) - STOPWORDS
    metadata_tokens = set(normalize(f"{skill.name} {skill.description}").split()) - STOPWORDS
    overlap = {token for token in task_tokens & metadata_tokens if len(token) >= 5}
    return min(len(overlap), 3)


def reasons_for(task: str, skills: dict[str, Skill]) -> dict[str, tuple[int, list[str]]]:
    normalized = normalize(task)
    result: dict[str, tuple[int, list[str]]] = {}

    def add(name: str, score: int, reason: str) -> None:
        name = CANONICAL.get(name, name)
        if name not in skills:
            return
        old_score, old_reasons = result.get(name, (0, []))
        reasons = old_reasons + ([reason] if reason not in old_reasons else [])
        result[name] = (max(old_score, score), reasons)

    for name in explicit_names(task, skills):
        add(name, 1000, "explicitly named by the user")

    for name, phrases, score, reason in SIGNALS:
        if any(normalize(phrase) in normalized for phrase in phrases):
            add(name, score, reason)

    # Metadata contributes only as a tie-breaker; it cannot activate a skill by
    # itself. This prevents generic descriptions from producing skill sprawl.
    for name, skill in skills.items():
        if name in result:
            score, why = result[name]
            result[name] = (score + lexical_score(task, skill), why)

    # A modification must end in evidence even when the prompt omits "test".
    if any(term in normalized for term in ("implement", "fix", "refactor", "change code", "add feature", "migration")):
        add("verification", 69, "repository modification requires an evidence gate")

    return result


def apply_conflicts(names: list[str]) -> list[str]:
    active = list(names)
    for group, preferred in PREFER.items():
        present = group.intersection(active)
        if len(present) > 1:
            active = [name for name in active if name not in present or name == preferred]
    return active


def select_with_dependencies(
    ranked: list[str],
    scores: dict[str, tuple[int, list[str]]],
    skills: dict[str, Skill],
    limit: int,
) -> tuple[list[str], list[str]]:
    selected: list[str] = []
    omitted: list[str] = []

    def closure(name: str, seen: set[str] | None = None) -> list[str]:
        seen = seen or set()
        canonical = CANONICAL.get(name, name)
        if canonical in seen or canonical not in skills:
            return []
        seen.add(canonical)
        result: list[str] = []
        for dependency in DEPENDENCIES.get(canonical, ()):
            result.extend(closure(dependency, seen))
            if dependency not in scores:
                scores[dependency] = (50, [f"required by {canonical}"])
        result.append(canonical)
        return result

    for name in ranked:
        group = [candidate for candidate in closure(name) if candidate not in selected]
        if len(selected) + len(group) > limit:
            omitted.append(name)
            continue
        selected.extend(group)
    return apply_conflicts(selected), omitted


def build_plan(task: str, profile_name: str) -> dict:
    skills = discover()
    scored = reasons_for(task, skills)
    ranked = sorted(scored, key=lambda name: (-scored[name][0], name))
    profile = PROFILES[profile_name]
    selected, omitted = select_with_dependencies(
        ranked, scored, skills, profile["max_skills"]
    )

    def item(name: str) -> dict:
        skill = skills[name]
        return {
            "name": name,
            "path": str(skill.path.relative_to(ROOT)),
            "reason": "; ".join(scored[name][1]),
        }

    top_score = scored[selected[0]][0] if selected else 0
    confidence = 0.98 if top_score >= 1000 else 0.90 if top_score >= 90 else 0.78 if top_score >= 70 else 0.55
    ambiguity = not selected or confidence < profile["escalate_below_confidence"]

    normalized = normalize(task)
    code_task = any(
        term in normalized
        for term in (
            "implement", "fix", "bug", "refactor", "migration", "review code",
            "repository", "repo", "test failure",
        )
    )
    return {
        "schema_version": "1.0",
        "profile": profile_name,
        "required_skills": [item(name) for name in selected],
        "optional_skills": [],
        "not_activated": [
            {"name": name, "reason": "activation cap reached"} for name in omitted[:3]
        ],
        "catalog_index": ([
            {"name": name, "description": skill.description}
            for name, skill in sorted(skills.items())
            if name not in selected and skill.path.is_relative_to(SKILLS_ROOT / "catalog")
        ] if ambiguity else []),
        "needs_clarification": ambiguity,
        "confidence": confidence,
        "preflight": (
            [
                {
                    "command": "python3 scripts/repo_recon.py",
                    "reason": "ground routing and planning in repository metadata",
                }
            ]
            if code_task
            else []
        ),
        "execution_contract": {
            "instruction_style": profile["instruction_style"],
            "max_steps": profile["max_steps"],
            "max_active_skills": profile["max_skills"],
            "require_verification": True,
            "on_uncertainty": "ask_parent_or_user",
            "read_only_until_routed": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", help="Compact task text; stdin is used when omitted")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="balanced")
    parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args()
    task = args.task if args.task is not None else sys.stdin.read()
    if not task.strip():
        parser.error("task text is required via --task or stdin")
    print(json.dumps(build_plan(task, args.profile), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
