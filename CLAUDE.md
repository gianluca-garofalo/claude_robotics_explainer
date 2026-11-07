@AGENTS.md

## Claude Code

- Slash commands are the skills: `.claude/skills` links to `.agents/skills`.
- `.claude/settings.json` holds the permissions (allow, ask, deny) and the hooks: `tools/hooks/block_publish.py`
  before every Bash command, `tools/hooks/after_edit.py` after every Edit or Write, `tools/hooks/record_approval.py` on
  `/approve-topic`. The allow rules match `bash setup.sh` and `bash tools/render_video.sh`, not `./setup.sh`.
- Path-scoped rules in `.claude/rules/` load with the files they match.
- Gotcha: project hooks and allow rules apply only after the workspace trust dialog has been accepted.
