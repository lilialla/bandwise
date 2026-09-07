# Changelog

All notable changes to **Bandwise** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- ChatGPT Voice handoff template, per-session export contract and an offline
  record importer with preview, private save, duplicate detection and session summaries.
- Four-criterion external AI feedback preserves the source response; unsupported
  pronunciation/fluency bands and partial-session overall scores remain empty.
- Dated public speaking-bank source index for September–December 2026,
  distinguishing previews, forecasts, download leads and empty collections.
- Synthetic regression tests for score evidence, missing answers, duplicate/conflict
  imports, revisions, private paths, input boundaries and the CLI workflow.

### Changed

- Align README, contributor/security guidance and issue/PR templates with the
  current source: complete first-install instructions, copy-versus-symlink
  updates, optional dependencies, voice-record CLI paths, data layout and checks.
- Clarify that module versions differ from release tags, archived scores remain
  external AI feedback, and dated speaking-bank previews are not complete banks.
- Replace the issue chooser's unavailable Discussions link with usage and
  private-reporting documentation, and remove references to GitHub private messaging.
- Complete the existing ten-skill learning loop: learner attempt, evidence-based
  feedback, revision/retry and the next practice action; preserve current routines.
- Add shared official scoring references; remove unsupported band shortcuts,
  fixed AI score deductions, canned story coverage and fabricated exam dates.
- Add optional private config and reuse an existing Maimemo MCP or API connector;
  document read-only status, preview and separately authorized account writes.
- Add IELTS Wang corpus result-page/export/self-report intake with version,
  speed and attempt tracking. No public progress API integration is claimed.
- Distinguish original/revised writing, first/repeated practice and score sources;
  retain old field names where useful and clarify legacy dashboard limitations.
- Support Codex alongside Claude Code; install sibling skills together so shared
  references remain reachable. No personal data or credentials are included.

## [1.1.4] - 2026-05-29

### Changed

- Redesigned the brand mark: replaced the wide README banner with a compact,
  editorial **square monogram logo** — warm-paper tile, ink hairline colophon
  frame, a thin ink ring echoing the buyunfadian.com favicon, a serif "B", and
  a bronze colophon dot. Magazine-minimal, same visual family as the brand
  site. README header is now a centered logo + title + tagline. Removed
  `assets/banner.svg`.
- Enabled GitHub Actions CI (`.github/workflows/ci.yml`): runs the validation
  gate and byte-compiles scripts on every push/PR.

## [1.1.3] - 2026-05-29

### Changed

- Heatmap now shades by **weighted training load** instead of raw item count:
  a full mock counts 3, an essay or full listening set 2, a reading note 1.
  So a mock day reads heavier than a day with a single note. The tooltip shows
  both the item count and the training-load value (`N 项 · 训练量 W`). The
  "学习活跃天数" KPI still counts distinct active days.

## [1.1.2] - 2026-05-29

### Fixed

- Validator no longer false-flags the **documented** Chinese data-folder names
  (`03_写作批改`, `04_听力精听`, `02_模考记录`, `03_阅读精读`) as personal-path
  leaks when they appear in docs/code. The leak rule now matches the full
  folder token and allowlists these four; any other `0N_中文` token is still
  caught. (Regression from v1.1.1, which shipped with a red validator gate.)

## [1.1.1] - 2026-05-29

### Added

- Dashboard now reads **Chinese folder names** in addition to the English ones
  (`writing` ↔ `03_写作批改`, `listening` ↔ `04_听力精听`, `mock` ↔
  `02_模考记录`, `reading` ↔ `03_阅读精读`), so a Chinese-organized data root
  renders without migration. Records are de-duplicated by file path.

## [1.1.0] - 2026-05-29

### Added

- Maintainer email (`1733970552@qq.com`) as a commercial-licensing contact in
  `LICENSE` and the README, alongside the website and GitHub issues.

### Changed

- `/ielts-status` now renders all error tags with **Chinese labels** (English
  machine tag kept in parentheses for search); stored tags are unchanged so
  aggregation still works. This matches the dashboard's localized labels.

### Note

- `v1.0.0` is now frozen at its released commit. Subsequent changes ship as
  new versions rather than moving the `1.0.0` tag.

## [1.0.0] - 2026-05-29

Initial public release.

### Added

- **10 Claude Code skills** that turn Claude Code into an IELTS prep coach:
  `ielts` (router/intake), `ielts-writing`, `ielts-reading`, `ielts-speaking`,
  `ielts-listening`, `ielts-mock`, `ielts-status`, `ielts-vocab`,
  `ielts-question-bank`, and `ielts-plan`.
- **Four-skill coverage** of the core test sections: writing (Task 1/2 grading
  on the four dimensions TR/CC/LR/GRA), reading (error diagnosis + synonym
  extraction), speaking (Part 1/2/3 material factory), and listening
  (intensive-listening + error taxonomy).
- **Configurable data root** via the `IELTS_COACH_HOME` environment variable
  (default `~/ielts-coach/`), with English subdirectories
  (`writing/ listening/ reading/ speaking/ mock/ vocab/ reviews/`) and ledger
  files (`study-plan.md`, `ai-worklog.md`, `open-questions.md`,
  `decisions.md`, `question-bank.md`).
- **Evidence-grade 7-tier source labeling** so every score, grade, or band
  output is annotated with the provenance of its claim.
- **Multi-model consensus check**: when two models (e.g. Opus and GPT-5.5)
  diverge by ≥ 0.5 on the same item, the disagreement is recorded as an open
  verification rather than averaged away.
- **Cross-artifact progress dashboard** generated by `scripts/dashboard.py`
  (self-contained offline HTML, inline SVG, zero dependencies): exam countdown
  hero with a goal progress ring, KPI cards, per-skill goal-gap bars, a
  GitHub-style study consistency heatmap, writing/listening trend lines, top
  error-tag bars, and a recent-activity feed — with hover tooltips and a
  light/dark theme toggle. UI localized to Chinese.
- **Validation gate** (`scripts/validate_skills.py`) enforcing the skill
  frontmatter contract (name matches directory, required `metadata` fields,
  PolyForm-Noncommercial-1.0.0 license), wired into CI.

[Unreleased]: https://github.com/lilialla/bandwise/compare/v1.1.4...HEAD
[1.1.4]: https://github.com/lilialla/bandwise/compare/v1.1.3...v1.1.4
[1.1.3]: https://github.com/lilialla/bandwise/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/lilialla/bandwise/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/lilialla/bandwise/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/lilialla/bandwise/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/lilialla/bandwise/releases/tag/v1.0.0
