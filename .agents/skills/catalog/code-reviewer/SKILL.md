---
name: code-reviewer
description: "High-signal review workflow for codebases, pull requests, ADRs, configuration, infrastructure-as-code, and targeted file or folder audits. Use when reviewing code or project artifacts for correctness, readability, consistency, typos, security, maintainability, compatibility, and whether the chosen approach is still current. Applicable to source code, ADRs, YAML/JSON/TOML configs, Helm charts, Flux resources, Terraform, Makefiles, and security-sensitive changes."
---

# Code Reviewer

Give reviews that help the author ship safely and keep the project technically current.

## Quick Start
1. Identify the review scope:
   - Whole project or repository area
   - Specific files or folders
   - Diff or pull request
   - Docs or ADRs
   - Infrastructure or deployment config
2. Understand intent before judging implementation:
   - What behavior, policy, or operational outcome is intended?
   - What constraints matter: compatibility, upgrade safety, security, runtime, team conventions?
3. Review in this order:
   - Correctness and behavioral risk
   - Security and secret handling
   - Compatibility and upgrade safety
   - Maintainability and consistency
   - Operational quality
   - Tests and verification
   - Typos, naming, and editorial quality
4. Report findings as:
   - Must-fix issues
   - Recommended improvements
   - Verification gaps
   - Open questions only when evidence is insufficient

## Review Modes

### Diff Review
- Start with entrypoints, data writes, auth, networking, release logic, and migrations.
- Separate mechanical churn from behavior changes.
- Verify tests cover the changed behavior rather than only unchanged happy paths.

### Targeted File or Folder Review
- Infer how the selected files fit the wider system before judging local changes.
- Read adjacent docs, values files, modules, templates, or callers only as needed to validate assumptions.
- Call out cross-file inconsistencies explicitly.

### Project Health Review
- Look for stale patterns, drift between docs and implementation, version pinning gaps, duplicated configuration, and missing guardrails.
- Prefer a small set of high-signal issues over exhaustive lint-like noise.

## Artifact-Specific Focus

### Code
- Check invariants, error handling, interfaces, test coverage, observability, and performance-sensitive paths.

### ADRs and Docs
- Check that the decision, constraints, rejected alternatives, and consequences are coherent.
- Flag stale architecture claims, missing dates or status, and terminology drift from the implementation.
- Catch typos, ambiguous wording, and contradictions.

### Configuration
- Check defaults, overrides, secret handling, environment-specific assumptions, and schema or API-version compatibility.
- Verify examples and comments still match the live configuration shape.

### Helm and Charts
- Check values-to-template wiring, safe defaults, naming consistency, upgrade compatibility, Kubernetes API usage, probes/resources/securityContext, and chart/documentation drift.
- Watch for brittle template logic, unquoted values where type coercion matters, and missing required validation where misconfiguration is dangerous.

### Flux
- Check source references, reconciliation order, dependency edges, namespace assumptions, health checks, prune behavior, and image automation safety.
- Flag patterns that can cause partial rollouts or hidden drift.

### Terraform
- Check provider and module version constraints, state-impacting changes, lifecycle behavior, input/output contract stability, data-source assumptions, and destructive plan risk.
- Prefer compatibility with current provider semantics over legacy patterns.

### Makefiles and Automation
- Check phony targets, dependency ordering, shell portability assumptions, error propagation, environment-variable handling, and documentation of dangerous targets.

### Security-Sensitive Areas
- Check authn/authz boundaries, network exposure, secret material, encryption expectations, least privilege, supply-chain trust, and unsafe defaults.
- Treat logging, metrics, and error messages as possible data exfiltration paths.

## When to Request Changes
- Bugs or correctness issues that can ship user-impacting failures.
- Security/privacy regressions or data handling gaps.
- Compatibility or upgrade risks that are likely to break deployment, provisioning, or consumers.
- Missing or inadequate tests or verification steps for risky behavior.
- Docs, ADRs, or configs that materially mislead operators or future maintainers.

## Output Format
- Present findings first, ordered by severity, with file references when possible.
- Then list assumptions or open questions.
- Then add a short change summary.
- End with verification gaps or follow-up checks.

## Actuality and Compatibility Checks
- When the review depends on current external behavior, verify against primary sources instead of relying on memory.
- Prefer official documentation, release notes, changelogs, API references, provider docs, Kubernetes docs, Helm docs, Terraform registry docs, or project-owned docs.
- State clearly when a conclusion is source-backed versus inferred from local files.
- If the repository contains its own version matrix, upgrade notes, or platform docs, read those before general web sources.

## Optional Tool
Generate a review report from git diff when the user asks for PR or diff review:

```bash
python3 .agents/skills/catalog/code-reviewer/scripts/review_diff.py --base origin/main --out /tmp/review.md
```

## References
- Use `references/review-checklist.md` as the default checklist for reviews.
- Load additional project documentation only when the artifact under review depends on it.

## Review Discipline
- Optimize for issues that change correctness, safety, operability, or long-term maintainability.
- Avoid flooding the user with style-only nits unless they indicate real inconsistency or future risk.
- Treat typos and wording defects as real findings when they affect commands, identifiers, configuration keys, policy meaning, or operator understanding.
- If no issues are found, say that explicitly and mention any residual testing or evidence gaps.
