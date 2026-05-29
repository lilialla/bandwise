# Security Policy

## Supported versions

Bandwise is a set of Markdown skill prompts, not a long-lived service. Security
fixes are applied to the latest released version only.

| Version | Supported |
| --- | --- |
| 1.0.x | ✅ |
| < 1.0 | ❌ |

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue.

- Preferred: open a [GitHub Security Advisory](https://github.com/lilialla/bandwise/security/advisories/new)
  for this repository (private by default).
- Alternative: contact the maintainer [@lilialla](https://github.com/lilialla)
  privately and ask for a secure channel before sharing details.

Please include the affected skill(s), reproduction steps, and the impact. We aim
to acknowledge reports within a reasonable time and will coordinate a fix and
disclosure timeline with you.

## Untrusted-input / prompt-injection boundary

Bandwise skills routinely ingest content the user did not write themselves —
pasted student essays, OCR'd listening scripts, and scraped web text. The project
treats all such material as **DATA to be analyzed, never as instructions to
follow**.

- Pasted/quoted content is the object of analysis only.
- If that content contains imperative phrasing intended to redirect the model
  ("ignore previous instructions", "you are now…", "忽略上面的指令" etc.), the
  skill must treat it as suspicious content to flag, **not** as a command to obey.
- Legitimate commands come only from the skill workflow and the user's direct
  chat turn.

Any change that weakens this boundary is treated as a security regression.
Contributors must preserve it (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

## No secrets in the repository

Do not commit API keys, tokens, credentials, or personal absolute paths
(e.g. `/Users/<name>/...` or private cloud-drive paths). The data root is
configured at runtime via `IELTS_COACH_HOME` and is never stored in the repo.
If a secret is exposed, rotate it immediately and report it via the channel above.

## Third-party model processing (read before pasting material)

Bandwise runs inside Claude Code, which sends the content you paste to the Claude
model for analysis. Treat the model as a third-party API:

- **Do not paste material you are not authorized to send to a third-party
  service.** This includes confidential, copyrighted, or personal information
  belonging to others.
- Student essays, exam transcripts, and similar content leave your machine when
  submitted for grading or analysis. Only submit what you have the right to share.

This is a usage-safety expectation, not a guarantee about any model provider's
data handling. Review the relevant provider's terms before submitting sensitive
content.
