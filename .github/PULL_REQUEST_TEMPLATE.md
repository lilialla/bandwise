# Summary

<!-- What does this PR change and why? Keep it focused. -->

## Skills touched

<!-- List the skill dirs you modified, e.g. ielts-writing, ielts-status.
     Write "none (docs/scripts only)" if no SKILL.md changed. -->

## Checklist

- [ ] Ran `python3 scripts/validate_skills.py` and it passes.
- [ ] For importer changes, ran `python3 -B -m unittest discover -s tests -v`; otherwise marked not applicable in validation notes.
- [ ] Updated `CHANGELOG.md` under the `[Unreleased]` section.
- [ ] Updated affected README, workflow references and templates; checked changed relative links and command examples.
- [ ] No personal paths (e.g. hard-coded `/Users/...`, real cloud-drive paths) and no secrets/API keys committed.
- [ ] For each touched skill, the frontmatter `name` matches its directory name.
- [ ] For each touched skill, `metadata.version`, `metadata.project: bandwise`, and `metadata.license: PolyForm-Noncommercial-1.0.0` are present.
- [ ] Preserved the untrusted-input boundary: pasted student content stays DATA, never instructions (see `CONTRIBUTING.md` / `SECURITY.md`).

## Validation

<!-- State what ran and what remains unverified. Use synthetic data only.
     Passing local checks does not prove real voice grading, current question-bank
     completeness, or external account integration. -->

## Notes for reviewers

<!-- Optional: anything that needs extra attention, follow-ups, or open questions. -->
