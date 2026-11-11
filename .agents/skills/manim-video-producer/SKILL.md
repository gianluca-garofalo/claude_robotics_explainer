---
name: manim-video-producer
description: Produces the narrated Manim (Community Edition) scenes for a finished explainer of the Remaining Action channel - a storyboard that chooses less and different material than the explainer to tell one story, voice-over text, scenes driven by data from the run's code/, video/plan.json (title, summary, tags, chapters, roles, ideas, thumbnail) - and checks them with draft renders, the design, number-format, reading-time, self-contained, structure, engagement, spoken-script, pacing and sync checks and an independent video design review. Use after the explainer passed review, for a series episode, or when asked for a Manim animation of an explainer.
argument-hint: "runs/<run> [number of scenes]"
---

# Manim video producer

Precondition: the explainer passed review (`python3 tools/run.py status runs/<run>`), or the run is a series episode
(`episode.json`, from the `produce-episode` skill); any other run is a standalone video, which tells the news on its
own terms and never names the publication it covers or its authors (spoken-script.md). Read first: AGENTS.md
(Conventions), `.claude/rules/manim-scenes.md` and [spoken-script.md](spoken-script.md).

Output in `runs/<run>/video/`: `storyboard.md`, `scenes/*.py` with `common.py`, `voice.py` and `reading_model.py`,
`data/*.npz`, `plan.json`, drafts and layout logs in `checks/`, `README.md`; reviews in `review/video/`. The final
render, assembly, final-cut review and hand-over come after the gates (`finish-video`, or the GitHub workflow).

## Procedure

1. **Storyboard** (`video/storyboard.md`; fill every field of [storyboard.md](storyboard.md)): one story with less, and
   different, material than the explainer, at a depth a video can carry; say what is left out. One idea per scene, 30
   to 120 s. The ideas:
   - Series episode: those of `video/episode.md` ("Ideas") and no more; its range is the runtime. A result the plan
     does not list goes back to the series plan (`python3 tools/series.py validate`), never into the video.
   - Standalone video: declare its own ideas in `plan.json` `ideas`, with the kinds and fields of a series plan
     (`concept`, `claim`, `star`; [brief.md](../plan-series/brief.md), "The idea budget"), and take the runtime from
     `python3 tools/video/idea_budget.py runs/<run>`. Too many ideas for one video: cut them, or leave them to the
     explainer.
2. **Data.** A script in `code/` (listed in `checks.toml`) writes `video/data/<name>.npz`, or the scenes compute closed
   forms of the explainer's equations. Nothing on screen is typed by hand.
3. **Scenes.** Copy `templates/manim/common.py`, `voice.py`, `reading_model.py` and `scene_template.py` into
   `video/scenes/`; one file per scene, class renamed.
4. **Rewrite pass** ([spoken-script.md](spoken-script.md), "The rewrite pass"), with
   `python3 tools/video/check_script.py runs/<run> --stage draft` and the ten scores in `video/README.md`; rewrite
   anything at 2 or less.
5. **Plan** (`video/plan.json`, format in `tools/video/plan.py`): `title` (accurate, no clickbait; packaging:
   AGENTS.md), `summary` (two to four sentences), `tags`, `search_term`; `scenes` in order, each with the explainer
   `section` it draws on, its `chapter` (a title for viewers, never the explainer's heading), `role` (`hook` first,
   `outro` last; `context`, and `recap` with `recap_of`, in a series), `music` when not the role's default,
   `picture` and `metaphor_resets`; `metaphor`; `thumbnail` (`scene` and `time` of a hook frame, `text`, `layout`
   `picture` with the top fifth of the frame empty, or `panel` with its left half empty); `ideas` (every idea unit
   where it lands: concepts, claims and starred results by id, and the roadmap, summaries, restatements, think
   prompts and recap, each with `scene`, the `bookmark` starting its sentence or `says`, and `shows`); `glossary`
   (the video's own terms). `python3 tools/ci/scene_matrix.py runs/<run>` must accept it.
6. **Draft check.** `bash tools/render_video.sh runs/<run> --check`, then `python3 tools/video/<check>.py runs/<run>
   --stage draft` for `check_design`, `check_reading`, `check_numbers`, `check_selfcontained`, `check_series`,
   `check_engagement`, `check_script`, `check_pacing` and `check_sync` (silent drafts keep the planned pauses: the
   draft timeline is the final one). Fix every error; read every warning.
7. **Design review.** Run each named agent (`.claude/agents/<name>.md`) as a subagent; if your tool has no such agent,
   use a general-purpose subagent or a fresh context with that file's body as the prompt. The `video-design-reviewer`
   gets the run path; then one `finding-verifier` per blocker or major `VD-` finding without a verdict; then
   `python3 tools/merge_reviews.py runs/<run> --set video`. Fix confirmed blockers and majors, record decisions in
   `review/video/resolutions.json`, re-render and repeat step 6, then the reviewer (second round:
   [reviewer-contract.md](../explainer-review/reviewer-contract.md)), the verifiers and the merge. At most two rounds;
   open blockers stop the run at the gate.
8. **README** (`video/README.md`): scene -> file -> explainer section -> data and script, the colour meanings, the
   voice (`voice.service` in `config/channel.json`; an AI voice is disclosed in the description;
   `python3 tools/video/voice_script.py runs/<run>` lists the blocks for the owner's own recording) and the "Spoken
   script" scores.

Setup problems (Pango headers, Debian pip, LaTeX packages, SoX): [manim-setup.md](manim-setup.md).
