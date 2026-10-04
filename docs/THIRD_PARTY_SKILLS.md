# Third-party project skills

Canonical harness copies live in `.agents/skills/`. The four named harness core
skills remain the only skills owned by `scripts/sync_skills.py`; Codex may also
discover integration-owned OpenSpec workflows at the same level.
`make skills-sync-local` copies the harness core to `.claude/skills` and `.opencode/skills` while
preserving those integration-owned files. Optional routed third-party skills
live under `.agents/skills/catalog/` and are read by exact path only after the
core router selects them.

The source revisions below were audited on 2026-09-04. Installed copies may contain project-specific safety and portability changes, so update them by reviewing upstream diffs rather than overwriting them.

| Source | Audited revision | Installed project skills | License / treatment |
|---|---|---|---|
| [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | CLI `1.12.0` | `openspec-apply-change`, `openspec-archive-change`, `openspec-explore`, `openspec-propose`, `openspec-sync-specs`, `openspec-update-change` | MIT metadata in generated skills. OpenSpec owns and refreshes its Codex, Claude Code, and OpenCode outputs; the harness preserves rather than vendors or rewrites them. |
| [obra/superpowers](https://github.com/obra/superpowers) | `b36e0829c6d0140e93cfef2ca599b1b07d4a7797` | `brainstorming`, `dispatching-parallel-agents`, `executing-plans`, `finishing-a-development-branch`, `receiving-code-review`, `requesting-code-review`, `subagent-driven-development`, `systematic-debugging`, `test-driven-development`, `using-git-worktrees`, `using-superpowers`, `verification-before-completion`, `writing-plans`, `writing-skills` | MIT. The always-on router, redundant approval gates, TDD scope, and delegation assumptions were narrowed for this harness. |
| [mattpocock/skills](https://github.com/mattpocock/skills) | `3cca18b368ae95cdbdebbff572ccafa662551015` | `grill-me`, `grilling` | MIT. Upstream source material is retained, but routing canonicalizes both names to the combined `grilling` workflow so they cannot conflict or double-load. Questions are prioritized by consequence and repository facts are inspected rather than asked of the user. |
| [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | `2c606141936f1eeef17fa3043a72095b4765b9c2` | `karpathy-guidelines` | The skill frontmatter says MIT, but no root license file was present in the audited revision. The project copy only adjusts when clarification is necessary. |
| [anthropics/skills](https://github.com/anthropics/skills) | `41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f` | `skill-creator` | Apache-2.0 license retained inside the installed skill. Claude-specific evaluation mechanics are optional and project skills remain under `.agents/skills`. |
| [Hermes Agent delegation guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation/) | Retrieved 2026-09-04 | `delegation` plus existing `hermes-delegation` | Project-authored adaptation. It keeps the Claude sidecar, OpenCode native Runs API, and Codex-no-Hermes split. |
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | `56ba5ace27e4697aedc60aa0b1e1bfdcd592ff20` | `last30days` | MIT. Project-authored safe adaptation: SearXNG/Crawl4AI, no cookie harvesting, credential-store access, anti-bot bypass, or implicit package installation. Upstream executable provider bundle is intentionally not vendored. |
| [blader/humanizer](https://github.com/blader/humanizer) | `e2e92e7b4b8229253ed5c8e81dc65463fdeddda5` | `humanizer` | MIT. Upstream skill package and license retained; nested Git metadata excluded. |
| [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | `367fdb7f0f8f8e7994b5aab632c7ce5014802b32` | `caveman`, `caveman-compress`, `caveman-review`, `investigate-first`, `lean-build`, `migration`, `safe-refactor`, `surgical-patch`, `verify-and-stop` | These skill files are covered by the repository's MIT portion. Cloud/engine skills needing the separately licensed runtime or unavailable services were not installed. Compression cannot send project files to an external model without explicit per-file authorization. |
| [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | `33362d969292b57eda82f3fbd9eb5f3f5bc9bbc2` | `graphify` with progressive references | Apache-2.0/MIT notices retained. The generated Codex skill was made cross-client and no longer installs `graphifyy` implicitly. The Python package itself is not installed by this change. |
| [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | `a1dc48e68138490d522c04cbf5822214c6eb1202` | `defuddle`, `json-canvas`, `obsidian-bases`, `obsidian-cli`, `obsidian-markdown` | MIT. All five portable Agent Skills installed. |
| [Shkirmantsev/AgenticNativePlatform](https://github.com/Shkirmantsev/AgenticNativePlatform/tree/main/.codex/skills) | `ad2781bcfb04058f177513a6c80ebd45f6e0812c` | `code-reviewer`, `solution-retrospective` | MIT. Only the reusable skills relevant to this repository were selected; Kubernetes/Flux/Terraform/Solo.io skills were omitted because this layout currently has no corresponding project artifacts. Retrospective persistence is project-only and cannot change authority or safety policy. |

Full upstream license and notice files that are not already inside a skill are retained under `third_party/licenses/skills/`.

## Synthesis from the attached reports

The three user-provided research reports were treated as reference material, not instructions. Their common recommendations shaped the integration:

- keep one canonical, portable project catalog and load details progressively;
- prefer a small set of composable workflows over another always-on orchestration layer;
- resolve ambiguity by impact and uncertainty, not by asking a fixed questionnaire;
- use exact repository search before semantic/graph search;
- delegate bounded work with minimal context and finite concurrency;
- make verification evidence part of every completion claim;
- promote lessons only when evidence is durable, keep repository facts in project policy, and never let self-improvement expand permissions.

Existing `project-safety`, `verification`, `web-research-routing`, and `hermes-delegation` remain authoritative where an upstream skill overlaps them.

## Downstream adaptation (2026-10-03)

The project-local `ponytail` skill was adapted from the MIT-marked catalog copy
in `other project` (donor HEAD `269fc50`, inspected working tree).
Upstream author/revision is not recorded in that donor copy; no independent
upstream provenance is asserted. The adaptation keeps reuse/YAGNI and root-cause
checks, removes persistent persona and restrictive response formatting, and
preserves harness verification and explicit user requirements. Its complete
local procedure is in `.agents/skills/catalog/ponytail/SKILL.md`.
Generated OpenSpec 1.13 skills are not vendored into the installed 1.12 workflow;
refresh client-owned skills using the chosen OpenSpec CLI version.
