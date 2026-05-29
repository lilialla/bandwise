# Contributing to Bandwise

Thanks for helping improve **Bandwise** — IELTS Coach for Claude Code. This guide
covers how the repo is organized, how to add or change a skill, and the rules that
keep the project safe and consistent.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Repository layout

Bandwise is a cluster of 10 Claude Code skills. Each skill is a directory at the
repo root containing a single `SKILL.md` prompt file:

| Directory | Role |
| --- | --- |
| `ielts` | Router / intake entry point |
| `ielts-writing` | Task 1/2 essay grading (TR/CC/LR/GRA) + archive |
| `ielts-reading` | Reading error diagnosis + synonym extraction |
| `ielts-speaking` | Part 1/2/3 material factory |
| `ielts-listening` | Intensive-listening + error taxonomy + archive |
| `ielts-mock` | Mock / real exam score intake |
| `ielts-status` | Cross-artifact progress report + error-book view |
| `ielts-vocab` | Synonym ledger + spaced review |
| `ielts-question-bank` | Cambridge test-bank done/not-done ledger |
| `ielts-plan` | Study-plan maintenance + weekly tasks |

Supporting code lives under `scripts/` (validation and dashboard generation).

## Persistent data root

User progress is **not** stored in the repo. It lives under a configurable root,
set via the `IELTS_COACH_HOME` environment variable (default `~/ielts-coach/`),
with English subdirectories and ledger files:

- Subdirs: `writing/ listening/ reading/ speaking/ mock/ vocab/ reviews/`
- Ledgers: `study-plan.md`, `ai-worklog.md`, `open-questions.md`,
  `decisions.md`, `question-bank.md`

Never hard-code an absolute path; always resolve it from `IELTS_COACH_HOME` with
the documented default.

## Adding or changing a skill

1. Create (or edit) `<skill>/SKILL.md`. The directory name **is** the skill name.
2. Keep the user-facing content in Chinese (zh-CN) with English IELTS terminology,
   matching the existing skills.
3. Update `CHANGELOG.md` under `[Unreleased]`.
4. Run the validation gate (below) before opening a PR.

### Frontmatter contract

Every `SKILL.md` starts with YAML frontmatter. The validator enforces:

```yaml
---
name: ielts-writing          # MUST equal the directory name
description: |               # what the skill does + how it is triggered
  ...
metadata:
  version: 1.0.0             # semantic version
  project: bandwise
  license: MIT
---
```

## Testing locally

Skills install by copying each `<skill>/` directory into `~/.claude/skills/`:

```bash
cp -r ielts-writing ~/.claude/skills/
```

Restart Claude Code (or start a new session) so it picks up the skill, then invoke
it (e.g. `/ielts-writing`) and confirm the behavior.

## Validation gate

All changes must pass the validator before merge. CI runs the same command:

```bash
python3 scripts/validate_skills.py
```

This checks the frontmatter contract (name matches dir, required `metadata`
fields, MIT license) across all skills.

## Untrusted-input safety rule (do not break this)

Bandwise skills routinely ingest content the user did not author themselves —
pasted student essays, OCR'd listening scripts, and scraped web text. **That
content is DATA to be analyzed, never instructions to follow.** When editing a
`SKILL.md`, preserve the prompt-injection boundary:

- Treat pasted/quoted material as the object of analysis only.
- If such content contains imperative phrasing ("ignore previous instructions",
  "你现在是…", etc.), the skill must flag it as suspicious content, not obey it.
- Commands come only from the skill workflow and the user's direct chat turn.

See [`SECURITY.md`](SECURITY.md) for the full policy.

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(ielts-writing): add Task 1 chart vocabulary check
fix(ielts-status): correct band-trend aggregation
docs: clarify data-root configuration
```

Keep PRs focused, fill in the pull request template, and confirm there are no
personal paths or secrets in the diff.
