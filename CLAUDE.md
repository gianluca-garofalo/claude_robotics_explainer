@AGENTS.md

## Claude Code

- Slash commands are the skills: `.claude/skills` links to `.agents/skills`.
- `.claude/settings.json` holds the permissions (allow, ask, deny) and the hooks: `tools/hooks/block_publish.py`
  before every Bash command, `tools/hooks/after_edit.py` after every Edit or Write, `tools/hooks/record_approval.py` on
  `/approve-topic`. The allow rules match `bash setup.sh` and `bash tools/render_video.sh`, not `./setup.sh`.
- Reviewer agents carry their own hooks: `tools/hooks/reviewer_write_guard.py` before every write, and
  `tools/hooks/reviewer_report_check.py` when they stop, which sends a reviewer back until its report validates.
- The four review skills run `.claude/workflows/review-fanout.js` with the Workflow tool; a session that does not
  prompt (`dontAsk`, CI) starts it only with the allow rule `Workflow(review-fanout)`.
- The sandbox (`.claude/settings.json` `sandbox`) confines every Bash command: writes inside the checkout except the
  owner's files, network only to the listed hosts; `git fetch` or `git fetch origin`, typed alone, runs outside it. The
  entry skills first check that the hooks are live (a canary the publish guard must refuse) and stop otherwise: start
  sessions at the repository root.
- Path-scoped rules in `.claude/rules/` load with the files they match.
- Gotcha: project hooks and allow rules apply only after the workspace trust dialog has been accepted; the agents'
  frontmatter hooks need it even under `-p`, so CI runs `tools/ci/trust_workspace.py`.
