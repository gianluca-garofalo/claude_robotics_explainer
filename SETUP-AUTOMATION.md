# Automated pipeline: one-time setup (optional)

The channel is run from Claude Code cloud sessions now (`/produce-from-source sources/<name>`, CLOUD-SESSION.md):
each session plans and makes one episode and hands you the finished files, which you upload yourself. Nothing on this
page is needed for that. This page sets up the optional GitHub Actions automation for later.

Once these steps are done, the pipeline runs on its own every Monday (or when you start it). It finds the news,
picks the topic, writes and checks the explainer, renders a narrated 1080p60 video (the Piper voice; it opens with
the hook and ends with an outro scene that shows the channel name), uploads it to YouTube as **private**, and opens one review issue for you. **Your review of the video is the
only human step:** approve it and the same workflow makes the video public, publishes the explainer and its code on
GitHub Pages and, if you enabled it, posts on LinkedIn. Reject it (with a reason) and the run is archived; nothing
goes public.

Your approval is a GitHub deployment review (or, in private repositories, a label only your account counts for).
Claude cannot give it: the job that runs Claude has a read-only token, no environment and no publishing secret.

Plan about two hours, plus Google's review of your API project (step 5.6), which can take weeks. Until Google
approves it, run with `YOUTUBE_UPLOAD=manual` (step 7): everything stays automatic except that you upload the
approved video in YouTube Studio yourself.

## What works out of the box, and what needs you

| Part | Without setup | Needs |
|---|---|---|
| A cloud session from a source to the hand-over (`/produce-from-source`) | yes, with the environment of CLOUD-SESSION.md (network entries and setup script) | |
| Local pipeline in Claude Code (`/produce-explainer`, `/produce-from-source`) | yes, after `./setup.sh` (it also downloads the Piper model for final renders, which needs `huggingface.co`, step 4) | |
| Tests, dry runs with stubbed YouTube and LinkedIn, config lint | yes | |
| Scheduled run up to the pre-render gates | | Claude secret (step 2), CI image (step 3), `PIPELINE_ENABLED` (step 7) |
| Narrated video, captions, chapters, thumbnail | yes: Piper, offline, no key (in the CI image) | optional: Azure key or your recordings (step 4) |
| Private upload, preview, review issue | | Google Cloud OAuth client and refresh token (step 5), `staging` environment (step 6), Pages (step 8) |
| Approval makes it public | | `publish` environment with you as required reviewer (step 6), `PUBLISH_ENABLED` (step 7), Google's API audit (step 5.6) or manual upload |
| LinkedIn post | | optional (step 9); the token must be renewed every 60 days |
| Search demand in the ranking | YouTube suggestions (no key) when reachable; otherwise unknown, weights renormalised | optional `YOUTUBE_API_KEY` (step 5.8) for views and competition; optional Google Trends client |
| Series mode in the workflow (episodes of a source explainer) | plans are made in a session and committed under `series/` (step 11) | the same setup as news mode; Run workflow with `mode: series` and the plan's folder name |

## Before you start

- A GitHub account; the repository **public** (see "Public or private" below).
- The Google account that owns the Remaining Action YouTube channel, with the channel created.
- A Claude Console API key, or a Claude subscription for `claude setup-token`.
- Nothing for the narration voice: Piper (offline, no key) is the default. Optional: an Azure account, or your own
  recordings (step 4).
- Python 3.11+ on your computer, once, for the YouTube token (step 5.5).

**Public or private.** Environments with required reviewers, which carry your approval, work in public repositories
on every GitHub plan. In private repositories they need GitHub Enterprise; on GitHub Pro or Team use the label
approval (`APPROVAL_MODE=label`, step 7). Private repositories on GitHub Free are not supported. In a public
repository, the review issue, workflow logs and artifacts, and the preview on the `gh-pages` branch are readable by
anyone before you approve: the draft explainer is effectively public, only the YouTube upload stays private.

## 1. Repository and Actions settings

1. Push the repository to GitHub (default branch `main`). The push also starts the **CI image** workflow (step 3).
2. Settings, Actions, General:
   - Actions permissions: allow all actions, or allow `actions/*`, `anthropics/claude-code-action@*` and `docker/*`.
   - Workflow permissions: **Read repository contents and packages permissions**. The workflows grant each job only
     what it needs (`permissions:` per job).
   - Leave "Allow GitHub Actions to create and approve pull requests" off.
3. Settings, Rules (or Branches): protect `main` against force pushes and deletion. The pipeline never pushes to
   `main`; it writes only to `gh-pages`.

## 2. Claude Code authentication

Add **one** repository secret (Settings, Secrets and variables, Actions, Secrets):

- `ANTHROPIC_API_KEY`: a key from the Claude Console; set a monthly spend limit on its workspace; or
- `CLAUDE_CODE_OAUTH_TOKEN`: run `claude setup-token` on your computer (Pro, Max, Team or Enterprise plans).

Each Claude stage also has a dollar cap and a turn cap (`--max-budget-usd`, `--max-turns`); the caps are repository
variables (step 7). They are limits, not estimates.

## 3. CI image

The render, gate, narration and assembly jobs run in `ghcr.io/<owner>/<repo>/explainer-ci:latest`, built from
`docker/Dockerfile` (Manim, TeX Live, ffmpeg, Node, Playwright with Chromium, KaTeX 0.16.9, Piper with its voice
model, the Azure text-to-speech client and the publishing clients). The image build downloads the voice model from
`huggingface.co`, which GitHub-hosted runners can reach. The **CI image** workflow builds it on the first push, whenever the Dockerfile or requirements
change, and monthly. Check that it finished (Actions, CI image; or start it there with Run workflow) before the first
pipeline run. If a job later cannot
pull the image ("denied"), open the package (your profile, Packages, `explainer-ci`, Package settings), and under
"Manage Actions access" give this repository the Read role.

## 4. Narration (text to speech)

The voice is **one setting**, `voice.service` in `config/channel.json`; a manual run can override it with the
workflow's `voice` input (Run workflow, `voice`). The choices:

| `voice.service` | What it is | Needs |
|---|---|---|
| `piper` (default) | Piper, an offline neural voice: the voice of final renders and the review copy | nothing: no key, no account (the model is in the CI image) |
| `azure` | Azure AI Speech neural voices; exact word timings | secrets `AZURE_SUBSCRIPTION_KEY`, `AZURE_SERVICE_REGION` |
| `recorded` | your own voice | you record one file per block (below) |
| `silent` | no audio: every draft render, and tests (the final gate stops it) | nothing |

There is no fallback voice: a final render whose voice cannot work stops before rendering and says why (for Piper, a
missing model: `./setup.sh` downloads it). Draft renders are always silent.

**Piper (default, no key).** `./setup.sh` installs `piper-tts` and downloads the voice model into `.cache/piper/`
(git-ignored); the CI image keeps it in `/opt/piper`. The model is `voice.piper.voice` (default
`en_US-ljspeech-medium`), from the Hugging Face repository `rhasspy/piper-voices`, where the Piper project
publishes its voices; it was trained on the LJ Speech dataset (public-domain LibriVox recordings read by Linda
Johnson). The download saves the voice's `MODEL_CARD` (training data and licence) and `<voice>.source.json` (URLs,
SHA-256) next to the model: read the card before you publish with that voice, and pin the file by copying the
printed SHA-256 into `voice.piper.sha256`. `python3 tools/video/piper_model.py info` shows all of this again;
`list` shows other voices. The Piper software is GPL-3.0-or-later; it is installed, not copied into this
repository, and the audio it makes is yours to use under the voice's licence. `length_scale` above 1 slows the voice,
`sentence_pause_s` sets the pause between sentences; a block faster than the house pacing (150 words per minute,
`config/video.json`) is synthesized again, slower. Draft renders are silent everywhere (they check layout and reading
time; the gate job renders them again, silent); the narration job makes the final voice, and the design and reading
checks run again on the final renders.

Network: the model download needs **`huggingface.co`** and its download CDN, hosts under **`hf.co`**
(`cdn-lfs.hf.co`, `cdn-lfs-us-1.hf.co` or `cas-bridge.xethub.hf.co`, depending on how the file is stored).
GitHub-hosted runners reach them. If your own network or a sandboxed session blocks them, allow those hosts, or copy
the three files (`<voice>.onnx`, `<voice>.onnx.json`, `<voice>.MODEL_CARD`) into `.cache/piper/` by hand; until then
a final render stops with that instruction (drafts are silent and need no model).

**Word timings.** Bookmarks (`<bookmark mark='x'/>` in a voiceover text) need to know when each word is spoken. Azure
reports it. Piper does not, so its timings are **estimated**: each sentence is synthesized separately,
which makes the sentence starts exact, and the words inside a sentence are spread by character position (a few
tenths of a second off at most). Recordings get linear estimates over the whole block, or the timings stored when
the narration was synthesized. Every timing list is made "bookmark-safe" (re-anchored on the
scene's text and bracketed by the start and end of the audio), so a bookmark always lands inside its block.

**Azure (optional).** In the Azure portal create a **Speech** resource (the free tier is enough to start; check its
current limits), copy one key and its region (for example `westeurope`), add them as the secrets above, and set
`voice.service` to `azure` (or pick `azure` in the `voice` input of one run). The voice is `voice.azure_voice`
(default `en-US-AndrewNeural`). The narration is synthesized once per run in its own job, which parses the scene files and never runs them, so keys never reach code
written during the run.

**Your own voice.** CI cannot record you: a run with `voice: recorded` stops before
rendering and lists the blocks to record in the job summary. Download the run (`run-gated` artifact), run
`python3 tools/video/voice_script.py runs/<run>`, record one file per block into `video/voice/` (WAV, MP3, M4A, FLAC
or OGG), then render and assemble locally (`tools/render_video.sh runs/<run> --voice recorded --quality h`, then
`tools/video/assemble.py`, `thumbnail.py`, `metadata.py`, `tools/gate.py --stage final`, the final-cut review and
`tools/gate.py --stage release`) and upload the result yourself (manual YouTube mode, step 7). That step is manual by
nature.

## 5. YouTube: Google Cloud project, consent screen, refresh token

1. **Project.** In the Google Cloud console create a project, for example `remaining-action-pipeline`.
2. **API.** APIs and Services, Library: enable **YouTube Data API v3**.
3. **Consent screen** (Google Auth Platform):
   - Branding: app name "Remaining Action pipeline", your support e-mail. Audience: **External**.
   - Data access: add the scopes `https://www.googleapis.com/auth/youtube.upload` and
     `https://www.googleapis.com/auth/youtube.force-ssl` (upload, then status, thumbnail and captions).
   - Audience: add the channel owner's Google account as a test user, then **Publish app** (status "In production").
     An app left in "Testing" gets refresh tokens that expire after 7 days. You do not need Google's app
     verification for your own account: at consent, Google warns that the app is unverified; choose Advanced,
     then continue.
4. **Client.** Clients, Create client, type **Desktop app**. Download its JSON. Keep it outside the repository.
5. **Refresh token**, on your computer, from the repository folder:

   ```bash
   python3 -m venv .venv-auth && .venv-auth/bin/pip install google-auth-oauthlib
   .venv-auth/bin/python tools/publish/get_refresh_token.py path/to/client_secret.json
   ```

   Sign in with the account that owns the channel; if the channel is a Brand Account, pick it when asked. The script
   prints `YOUTUBE_CLIENT_ID` and `YOUTUBE_REFRESH_TOKEN`; the client secret is `client_secret` in the JSON. Then
   delete the JSON file and `.venv-auth`. The pipeline refuses to upload when the authorised channel is not
   "Remaining Action" (`youtube.expected_channel_title` in `config/channel.json`).
6. **API audit (for public videos).** Videos uploaded through the API by a project created after 28 July 2020 that
   has not passed Google's audit are locked as private. Fill in the "YouTube API Services - Audit and Quota Extension
   Form" for this project (describe it as a single-channel publishing tool for your own channel). Until it passes,
   set `YOUTUBE_UPLOAD=manual`; if you leave `api`, the approved publish step fails with this explanation and the
   video stays private.
7. **Channel.** Verify the channel by phone (youtube.com/verify) so the API may set custom thumbnails; without it the
   upload continues with a warning in the review issue. In YouTube Studio, set the channel audience so that videos can
   be "not made for kids" (the pipeline declares each video; a channel-wide "made for kids" setting would override it).

8. **Search data key (optional).** In the same project, Credentials, Create credentials, API key; restrict it to the
   YouTube Data API v3. Add it as the repository secret `YOUTUBE_API_KEY`. Only the search job reads it (public data:
   search results, view counts); it holds no access to your channel. Without it, search demand uses YouTube
   suggestions only and the supply gap is unknown.

Quota: the project gets 10,000 units a day. One run uses about 2,200: the upload (listed at 1,600 units in Google's
quota calculator; some newer pages list 100), captions 400, thumbnail 50, status update 50, lists 1 each. The search
job adds up to 12 searches of 100 units (`max_api_queries_per_run` in `config/search.json`), and a series episode up
to about 100 more for its playlist (created once, 50; each episode added, 50).

## 6. GitHub environments and their secrets

Settings, Environments, New environment:

| Environment | Protection | Secrets |
|---|---|---|
| `staging` | Deployment branches: selected, `main` | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` |
| `publish` | **Required reviewers: you.** Leave "Prevent self-review" unchecked (you start the runs, so it would block your own approval). Deployment branches: `main` | the three YouTube secrets; optional `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN` |
| `publish-label` | only for `APPROVAL_MODE=label`: no reviewers, branches `main` | same as `publish` |

The staging job uploads privately with the repository's own scripts; the publish job's secrets are released only
after your approval. No job that runs Claude or code written during a run holds any of these secrets
(`python3 tools/lint_project.py --automation` checks this on every push).

## 7. Repository variables

Settings, Secrets and variables, Actions, Variables:

| Variable | Set to | Meaning |
|---|---|---|
| `PIPELINE_ENABLED` | `true` | Kill switch. Any other value: scheduled and manual runs stop before they start |
| `PUBLISH_ENABLED` | `true` | Second switch, read at approval time: otherwise an approval publishes nothing |
| `SITE_BASE_URL` | `https://<owner>.github.io/<repo>` | Previews in the review issue; explainer and code links in the YouTube description, only for runs with links on (`links.include` or the `links` input). Not needed while links are off |
| `YOUTUBE_UPLOAD` | `api` (default) or `manual` | `manual` until the API audit passes: no upload; you upload the approved video |
| `APPROVAL_MODE` | `environment` (default) or `label` | `label`: private repositories without required reviewers |
| `APPROVER_LOGIN` | your GitHub login | Label mode: only labels you add count |
| `PREVIEW_MODE` | `pages` (default) or `artifact` | Where the explainer preview lives during review |
| `CLAUDE_SANDBOX` | unset (sandbox on) or `false` | `false` only if Claude Code's sandbox cannot start on the runner |
| `CLAUDE_BUDGET_SCOUT_USD`, `_RANK_`, `_WRITE_`, `_REVIEW_`, `_VIDEO_`, `_EPISODE_` | defaults 6, 3, 25, 25, 20, 20 | Dollar cap per Claude stage. The explainer review runs five reviewers and a verifier per serious finding: one review of the 19-section source document used about 1.3 M subagent tokens, plus about 0.5 M for verification, so `CLAUDE_BUDGET_REVIEW_USD` may need raising for long explainers (the same variable caps the final-cut review, default 10) |
| `LINKEDIN_ENABLED`, `LINKEDIN_VERSION` | `true`, a current version `YYYYMM` | Optional LinkedIn post |

Your preferences live in `config/`: `channel.json` (branding, voice, `links.include` for description links (default
off), YouTube defaults: category, tags, review
privacy, `publish_mode` public or scheduled, `on_reject` keep private or delete, synthetic-media declaration),
`pipeline.json` (automatic topic selection threshold, which ledger statuses are never picked again, gate limits),
`rubric.json` (weights, including search demand and supply gap), `search.json` (search lookups and quota cap) and
`video.json` (design and reading-time thresholds, the palette and its meanings, with the sources of every constant;
`palette.background` is the one place to change the video background, `equation_numbers` and `self_contained` the
self-contained rule, `recall` the recall-load warning).

## 8. GitHub Pages

The first staged run creates the `gh-pages` branch (previews, published explainers, `ledger.json`, archive). Then:
Settings, Pages, Source "Deploy from a branch", branch `gh-pages`, folder `/ (root)`. Previews of earlier runs become
reachable within a few minutes. Published explainers live at `<SITE_BASE_URL>/explainers/<slug>/` with their code,
`code.zip` and the review and gate summaries.

## 9. Optional: LinkedIn

1. At developer.linkedin.com create an app (it needs a LinkedIn company page to associate with) and add the products
   "Share on LinkedIn" (scope `w_member_social`) and "Sign In with LinkedIn using OpenID Connect".
2. Get a member access token for yourself with scopes `openid profile w_member_social` (the developer portal's
   OAuth token tool does this). Call `https://api.linkedin.com/v2/userinfo` with it; your author URN is
   `urn:li:person:<sub>`.
3. Add `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_AUTHOR_URN` to the `publish` environment, and the variables
   `LINKEDIN_ENABLED=true` and `LINKEDIN_VERSION` (a version LinkedIn currently lists, format `YYYYMM`).

The token lasts 60 days and standard apps get no refresh token: renew it by hand. An expired token makes the LinkedIn
step say so and skip; it never blocks the publication.

## 10. First runs

1. Actions, **Explainer pipeline**, Run workflow, `stop_after: produce`: Claude's part only. Read the job summary
   (selection reasons) and download the `run-src` artifact.
2. Again with `stop_after: render`: adds the clean-checkout gates, narration and 1080p60 renders; download
   `run-final` and watch `video/final/<slug>.mp4`.
3. Then `full`: private upload, preview and the review issue. Approve or reject it to see the whole loop.

Run workflow inputs, besides `mode`, `focus`, `series`, `episode` and `stop_after`: `voice` (step 4), `links`
(`config` = `links.include` in `config/channel.json`, default off; `on` adds the explainer and code links to this run's
YouTube description, never to the video, and needs `SITE_BASE_URL`; `off`), and `fresh` (series mode, below).

The video itself is always self-contained: no reference to the explainer, code, files, links or other episodes, and
no equation labels (`equation_numbers` in `config/video.json`, default false). The gate "self-contained video" checks
the renders, the narration, the captions and the chapters for the explainer, code, files, links, equation labels and
another episode's equation numbers ("equation 4 of episode 2"); mentions of other episodes themselves are left to the
reviewers. When it fails, its finding names the scene and the text.

**Network for the reviewers.** The reference-verifier and the other reviewers open records on doi.org,
api.crossref.org, arxiv.org (and ar5iv.labs.arxiv.org), publisher sites and university repositories (for example
skoge.folk.ntnu.no, lup.lub.lu.se). GitHub-hosted runners reach them: in CI, Claude's Bash commands have no network
inside the sandbox, but WebFetch does. A sandboxed local or cloud session may block these hosts; the reviewers then
record each lookup as unreachable, with the host, and never guess what the record says. Allow the hosts in that
session's network settings if you want the references verified there.

## 11. Series mode

Series are planned from a source document, `sources/<name>/`, by `/plan-series sources/<name>` or as the first step of
`/produce-from-source sources/<name>` in a session (a curator subagent proposes, an independent red team checks every
episode, `tools/series.py write` stores `series/<slug>/series.json` and `PLAN.md`). A plan made in a cloud session
exists only there until you commit it: the session sends you the files; put them in `series/<slug>/`, commit and push.
`python3 tools/series.py from-source sources/<name>` lists a source's series in release order.

Plan approval follows `config/pipeline.json` `series.plan_approval`. It is `optional` (since 2026-11-01, your
decision): episodes start from the plan as written, with an informational note, and you approve only the finished
video. Set it to `required` to approve each plan first, in a terminal opened in the repository folder (the tool uses
`.venv`, made by `./setup.sh`), after reading `series/<slug>/PLAN.md`:

```bash
./tools/human/approve_series.py series/the-plan-folder-name
```

It records the approval in series.json with the plan's hash (any later change needs a new approval); then commit
`series/`.

In the workflow: Actions, **Explainer pipeline**, Run workflow, `mode: series`, `series:` the plan's folder name (the
input is required in series mode), `episode: next` (or a number); `next` follows the plan's release order and waits
for an episode of another series that it builds on. The episode job starts the run with `tools/series.py start`, Claude
makes the narrated scenes with the series beats and passes the checks and the design review, and the rest is the same
as news mode: final render, assembly, the final-cut review job, the private upload and your approval. Scenes are kept
only for an episode made again after a fix (`series/<slug>/episodes/epNN/scenes/`); tick `fresh` to leave them out.
On approval the episode is added to its series playlist (created on first use, public, episodes in plan order); after
publishing, do the YouTube Studio steps the review issue lists (end screen, optional cards, once per series "Set as
official series for this playlist").

## 12. Day to day

- **Every Monday** a run starts (change the `cron` line in `.github/workflows/pipeline.yml`). One run is in review
  at a time: later runs wait until you decide.
- **You get** GitHub's "deployment review" notification and a review issue labelled `pipeline:review`: links to the
  private video and the preview, why the topic was chosen, every gate result, the reviewers' findings and what was
  done about them, the claims that are still unverified, and a checklist.
- **Approve:** in the workflow run, Review deployments, tick `publish`, Approve and deploy. **Reject:** same place,
  Reject, and write the reason in the comment box (label mode: comment, then add `approve-publish` or
  `reject-publish`). No decision within 30 days counts as not approved.
- **Stopped runs** open an issue labelled `pipeline:stopped` with the failed job and the link to its logs; nothing is
  uploaded when a gate fails, and nothing goes public without your approval.
- **Switch off:** set `PIPELINE_ENABLED` to anything but `true`, or disable the workflow in the Actions tab.
- **A rejected topic** is not picked again; to allow it, remove `rejected` from `skip_ledger_statuses` in
  `config/pipeline.json` or delete its entry from `ledger.json` on `gh-pages`.

## 13. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Claude steps fail at start with a sandbox error | bubblewrap cannot start on the runner: set `CLAUDE_SANDBOX=false` (settings without the sandbox; deny rules and the read-only token still apply) |
| `invalid_grant` from YouTube | refresh token expired or revoked: consent screen still in "Testing", or access removed in your Google account; repeat step 5.5 |
| "authorised channel is ..." | you signed in with another channel in step 5.5: repeat it and pick Remaining Action |
| Publish fails with "kept the video private" | API audit not passed (step 5.6): use `YOUTUBE_UPLOAD=manual` meanwhile |
| Thumbnail warning in the review issue | channel not phone-verified (step 5.7) |
| `quotaExceeded` | more than about four runs in one day; wait for the daily reset |
| Narration job fails "needs AZURE_SUBSCRIPTION_KEY" | `voice.service` (or the run's `voice` input) is `azure` without the step 4 secrets: add them, or use `piper` (no key) |
| Narration job fails "voice service piper: the Piper voice model is not here" | the CI image was built without the model (the build could not reach `huggingface.co`): rebuild the image (Actions, CI image, Run workflow) |
| A local final render stops: "the final render needs the piper voice; nothing was rendered" | the Piper model is not in `.cache/piper/`: run `./setup.sh` (or `python3 tools/video/piper_model.py fetch`); there is no fallback voice |
| Final gate "narration present" fails | the silent voice reached the final render: `voice.service` or the run's `voice` input is `silent` |
| Gate "self-contained video" fails | the video names the explainer, code, a file or a link, shows an equation label, or cites another episode's equation number: the finding gives the scene, the time or the narration block, and the text (`review/design/<stage>/check_selfcontained.md`) |
| Gate "number format" fails | a number on screen, in the narration or the captions breaks the house format (0.500000, 1.28 beside 1.277, a readout whose decimals change): the finding names the scene, time and text (`review/design/<stage>/check_numbers.md`); format with `fmt()` |
| Gate "series plan approved by the owner" fails | `series.plan_approval` is `required` and the episode was started from a plan you have not approved, or the plan changed since: read `series/<slug>/PLAN.md`, run `./tools/human/approve_series.py series/<slug>` yourself and commit, then start the episode again |
| Gate "series plan (owner approval optional)" fails | the plan changed after the episode was started: start the episode again from the current plan |
| The episode job fails "series mode needs the series input" | Run workflow in series mode without `series`, or with a folder that has no committed plan: commit the plan the session sent you (`series/<slug>/`) and give its folder name |
| Release gate fails (stage job, before the upload) | the final-cut review found an open blocker, or watched another version of the video: read `review/final_cut/summary.md` in the run-final artifact; fix the scenes in a new run. "NOT INDEPENDENT" in the gate detail means the review was done by the session that made the video |
| Metadata step fails "links are on for this run but there is no site base URL" | the run's `links` input (or `links.include`) is on: set `SITE_BASE_URL` (step 7) or run with links off |
| Thumbnail error "frame text behind the title" | the thumbnail frame has text where the title goes: pick another `thumbnail.time` in `plan.json` (a moment with the left half free of text) |
| `piper_model.py fetch` exits with status 2 | your network blocks `huggingface.co` or its CDN (`*.hf.co`): allow them, or copy the model files in by hand |
| Preview link 404 | Pages not enabled yet (step 8) |
| Render job timeout | a scene is too long or redraws too much per frame: see the gotchas in `.claude/skills/manim-video-producer/SKILL.md` |
| Gate "video design" or "reading time" fails | `review/design/<stage>/check_design.md` or `check_reading.md` in the run artifact (also in the job summary) names the scene, the time and the item |
| Reference findings or the review summary say a record was unreachable | the session's network blocks doi.org, api.crossref.org, publisher sites or a university repository (step 10, Network for the reviewers): allow them there, or let CI run the review |
| ranking.md lists "Sources unreadable from this network" | a local or cloud session blocks hosts the scout needs (arXiv, its API, Crossref, Semantic Scholar, OpenAlex, publishers): allow them in the session's network settings; GitHub-hosted runners are not restricted this way |
| Search data all "unavailable" | the runner cannot reach the suggestion endpoint, no `YOUTUBE_API_KEY`, no Trends client: the ranking still works without the search criteria |
| "search.json changed after the search job" | the ranking step found the search data modified inside the Claude job; investigate the run before re-running |
