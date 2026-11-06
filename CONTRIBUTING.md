# Contributing

Thanks for helping. Contributions are welcome in five places: skills and agents (`.claude/`), deterministic tools
(`tools/`), templates (`templates/`), the automation (`.github/`, `ci/`, `docker/`), and corrections to published
explainers.

## Before you open a pull request

```bash
python3 -m unittest discover -s tests
python3 tests/dry_run.py
python3 tests/automation_dry_run.py
python3 tools/lint_project.py
```

The unit tests; the local pipeline on fictional fixtures (no network, nothing published); the CI path with YouTube,
LinkedIn and search stubbed, series mode included (needs ffmpeg, Manim, Node); and the lint of the `.claude/` formats,
CI settings and workflows, repository hygiene and the documents' command blocks (they must paste into zsh as well as
bash: no comments inside blocks, no `<placeholders>`, no unquoted `[ ] * ?`). All four must pass (`checks.yml` runs
them, plus actionlint and `tools/check_source.py --all`, on every push). If you changed the HTML template or CSS,
also run `node tools/check_html.js` on a source document and on a dry-run build (`python3 tests/dry_run.py --keep`
prints the folder).

## Testing

Tests and dry runs never depend on anything the owner may change: the source documents in `sources/`, the series
plans in `series/`, the preferences in `config/` and the wording of the documents.

- Tool tests use fixtures under `tests/fixtures/`: the fixture source `tests/fixtures/sources/fixture-predictive-control/`
  (a small explainer built with `tools/build_explainer.py`, its scripts with `checks.toml` and logs, a data file), the
  fixture series `tests/fixtures/series/fixture-series.json` (made by `tests/series_fixture.py`), and
  `tests/fixtures/config/`, a frozen copy of the preferences.
- Every test module and dry run calls `testenv.activate()` (`tests/testenv.py`) before it imports a tool: the tools,
  also in subprocesses, then read `tests/fixtures/config` (`$RA_CONFIG_DIR`, `$VIDEO_CONFIG`, `$CHANNEL_CONFIG`).
  A test that needs another preference makes a variant (`testenv.variant(folder, {"pipeline": {...}})`) and passes
  `testenv.env(variant)` to the tool; it never assumes the owner's value.
- The only test that reads `sources/` is `tests/test_sources_smoke.py`: it runs `tools/check_source.py` on each real
  source, asserts that it passes (properties, never wording, numbers, counts or hashes), and skips when `sources/` is
  empty.
- `tests/test_hermetic.py` fails if any other test file reads `sources/`, `series/` or `config/` of the repository, or
  names a real source or series, and checks that every test module activates the fixtures first.
- The lint rules on the documents (zsh-safe command blocks, no absolute paths, no model names) are deliberate; no test
  checks other wording of README.md, CLAUDE.md or the other documents.
- Tests check behaviour, not the wording of prompts, skills or generated text, nor a copy of a design constant (a
  threshold, a colour, a list of names). An agent or skill file is checked only for what a machine relies on: its
  frontmatter, its hooks, and the tools, files and ids it names.
- To change a fixture, change the tests that depend on it in the same commit.

## Skills

- One job per skill. The `description` says when to use it (Claude reads it to decide), not what it contains.
- Keep `SKILL.md` short (well under 500 lines): inputs, outputs, the checks that define done, and a **Gotchas** section.
  Move detail into supporting files in the skill folder and link them.
- Do not state what Claude already knows; write what it cannot see: our formats, our rules, our past failures.
- Add a gotcha when you hit a failure that the skill could have prevented, with the fix.
- Deterministic steps belong in a script in `tools/` (with `--help`, a clear exit status, standard library where
  possible), called from the skill.
- Skills with side effects or that stand for a human decision set `disable-model-invocation: true`.
- No `model` field in skills, agents or workflows: Claude Code's defaults apply.

## Reviewer agents

- Reviewers get fresh context, read-mostly tools and the write guard hook; they report in the format of
  `.claude/skills/explainer-review/reviewer-contract.md` and never edit what they review.
- Do not pass the writer's reasoning to a reviewer. Independence is the point.
- A new review dimension is a new agent plus a line in the explainer-review skill and the workflow, its finding-id
  prefix in `tools/validate.py` (`ID_PREFIX`), its name in `tools/gate.py` (`REVIEWERS`) and a fixture report in
  `tests/fixtures/run/review/`.

## Automation (workflows, CI settings, image)

- The publishing boundary is structural: jobs that run Claude get a read-only token, no environment and no secret but
  the Claude key; jobs that run code written during a run (code checks, renders) get no secret at all; YouTube and
  LinkedIn secrets live only in the `staging` and `publish` environments. `lint_project.py --automation` checks this;
  do not weaken it.
- Pass values into shell steps through `env:`, never as `${{ ... }}` inside `run:` (expression injection).
- Gates that decide whether a run continues run on a clean checkout, not in the job where Claude ran.
- New deterministic steps get a stub-backed case in `tests/automation_dry_run.py`.
- Design and reading-time thresholds live in `config/video.json` with their sources; change a constant there, with the
  reason in the pull request, not in the tools. A new design check gets a fixture from a real render in
  `tests/fixtures/design/` (layout logs from `tools/video/layout_probe.py`, trimmed to the snapshots that matter).
- CI settings (`ci/*.json`) are installed as user settings: use relative path rules, not `/path`.

## Hooks and permissions

- A hook is for a rule with no exceptions. Keep it fast (well under a second), standard library only, exit 2 with a
  clear message on stderr to block, and add cases to `tests/`.
- Deny rules first. Do not add allow rules for publishing commands or for unrestricted network tools.
- `tools/hooks/`, `tools/human/`, `tools/publish/`, `tools/ci/`, `config/`, `.github/` and `ci/` are denied to
  Claude's edit tools on purpose: edit them yourself.

## Content

- Sources: primary sources for technical claims, secondary ones for context; see
  `.claude/skills/robotics-news-scout/source-policy.md`.
- No copied text or images. Figures and animations are original and produced by scripts in the run's `code/`.
- Every number comes from a script; every reference detail was seen in a record.
- The rubric (`config/rubric.json`) is changed by hand: bump `version` and explain the change in the pull request.

## Corrections to an explainer

Open an issue with the explainer, the section or equation number, what is wrong and the evidence (a derivation, a
script output or a source passage). Fixes go through the same review as new content.

## Hygiene

No secrets, personal e-mail addresses, absolute local paths or model identifiers in the repository (`lint_project.py`
checks). Large binaries (videos) go to Git LFS or release assets. The repository is all rights reserved (see
`LICENSE`): contributions only by prior written agreement with the owner.
