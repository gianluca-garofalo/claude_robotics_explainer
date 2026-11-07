# Contributing

The repository is all rights reserved (`LICENSE`): contributions only by prior written agreement with the owner.
AGENTS.md has the commands, conventions and rules for changing the pipeline, for people too. This file adds what only
people do.

- **Corrections to an explainer**: open an issue with the explainer, the section or equation number, what is wrong
  and the evidence (a derivation, a script output or a source passage). Fixes go through the same review as new
  content.
- **The owner's files** (`config/`, `series/`, `sources/`, `tools/hooks/`, `tools/human/`, `tools/publish/`,
  `tools/ci/`, `.github/`, `ci/`) are edited by people, never by an agent.
  - `config/rubric.json`: bump `version`. Design and reading-time thresholds live in `config/video.json` with their
    sources: change them there, not in the tools. Give the reason in the pull request.
  - Automation: jobs that run Claude hold a read-only token, no environment and only the Claude key; jobs that run
    code written during a run hold no secret; YouTube and LinkedIn secrets live only in the `staging` and `publish`
    environments (`python3 tools/lint_project.py --automation` checks it; never weaken it). Values reach shell steps
    through `env:`, never `${{ ... }}` inside `run:`. Gates that decide whether a run continues run on a clean
    checkout. A new deterministic step gets a stub-backed case in `tests/automation_dry_run.py`. `ci/*.json` are
    installed as user settings: relative path rules only.
  - Hooks only for rules with no exceptions: well under a second, standard library only, exit 2 with a clear message
    on stderr to block, with tests. Deny rules first; no allow rules for publishing commands or unrestricted network
    tools.
