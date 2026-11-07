# Automated pipeline: one-time setup (optional)

Cloud sessions (README.md, Quick start) need none of this. Once it is set up, the GitHub workflow runs every Monday
or when you start it: it makes the explainer and the video, uploads the video to YouTube as **private** and opens a
review issue. Approve it (a GitHub deployment review, or a label only your account counts for; Claude can give
neither) and it makes the video public, publishes the explainer and its code on GitHub Pages and optionally posts on
LinkedIn; reject it and the run is archived.

Plan about two hours, plus Google's API audit (step 5.6), which can take weeks; until it passes, use
`YOUTUBE_UPLOAD=manual` (step 7) and upload the approved video yourself.

## Before you start

- A GitHub account and this repository, **public**: in a private repository, required reviewers need GitHub
  Enterprise, so on Pro or Team use label approval (`APPROVAL_MODE=label`, step 7); private on GitHub Free is not
  supported. In a public repository the review issue, logs, artifacts and the `gh-pages` preview are readable before
  you approve; only the YouTube upload stays private.
- The Google account that owns the Remaining Action YouTube channel.
- A Claude Console API key, or a Claude subscription for `claude setup-token`.
- An Azure Speech resource for the channel voice (step 4).
- Python 3.11 or newer on your computer, once, for the YouTube token (step 5.5).

## 1. Repository and Actions settings

1. Push the repository to GitHub (default branch `main`). The push starts the **CI image** workflow (step 3).
2. Settings, Actions, General:
   - Actions permissions: allow all actions, or allow `actions/*`, `anthropics/claude-code-action@*` and `docker/*`.
   - Workflow permissions: **Read repository contents and packages permissions**.
   - Leave "Allow GitHub Actions to create and approve pull requests" off.
3. Settings, Rules (or Branches): protect `main` against force pushes and deletion.

## 2. Claude Code authentication

Add **one** repository secret (Settings, Secrets and variables, Actions, Secrets):

- `ANTHROPIC_API_KEY`: a Claude Console key (set a monthly spend limit on its workspace); or
- `CLAUDE_CODE_OAUTH_TOKEN`: from `claude setup-token` on your computer (Pro, Max, Team or Enterprise plans).

## 3. CI image

The gate, narration, render and assembly jobs run in `ghcr.io/<owner>/<repo>/explainer-ci:latest`, which the **CI
image** workflow builds from `docker/Dockerfile` on the first push, when the Dockerfile or requirements change, and
monthly. Check that it finished (Actions, CI image) before the first pipeline run. If a job cannot pull the image
("denied"): your profile, Packages, `explainer-ci`, Package settings, Manage Actions access: give this repository
the Read role.

## 4. Narration (text to speech)

The voice is `voice.service` in `config/channel.json`; the workflow's `voice` input overrides it for one run. There
is no fallback voice: a final render whose voice cannot work stops and says why. Drafts are always silent.

| `voice.service` | Voice | Needs |
|---|---|---|
| `azure` | the channel voice, `voice.azure_voice` (Steffan HD) | repository secrets `AZURE_SUBSCRIPTION_KEY`, `AZURE_SERVICE_REGION` |
| `piper` | Piper, offline | nothing: its model is in the CI image |
| `recorded` | your own voice | one recording per narration block (below) |
| `silent` | none: drafts and tests; the final gate stops it | nothing |

**Azure.** In the Azure portal create a **Speech** resource; put one key and its region (for example
`swedencentral`) into the two secrets. Only the narration job reads them, and it never runs code written in a run.

**Piper.** Read the licence in the model's `MODEL_CARD` (`python3 tools/video/piper_model.py info`) before you
publish with it; to pin the model, copy the SHA-256 it prints into `voice.piper.sha256`.

**Your own voice.** A run with `voice: recorded` stops before rendering and lists the blocks to record in the job
summary. Download the `run-gated` artifact; `python3 tools/video/voice_script.py runs/<run>` lists the blocks; record
one file per block into `video/voice/` (WAV, MP3, M4A, FLAC or OGG). Then render with `bash tools/render_video.sh
runs/<run> --voice recorded --quality h`, run `tools/video/assemble.py`, `thumbnail.py`, `metadata.py`,
`tools/gate.py --stage final`, the final-cut review and `tools/gate.py --stage release`, and upload it yourself
(`YOUTUBE_UPLOAD=manual`).

## 5. YouTube: Google Cloud project, consent screen, refresh token

1. **Project.** In the Google Cloud console create a project, for example `remaining-action-pipeline`.
2. **API.** APIs and Services, Library: enable **YouTube Data API v3**.
3. **Consent screen** (Google Auth Platform):
   - Branding: app name "Remaining Action pipeline", your support e-mail. Audience: **External**.
   - Data access: the scopes `https://www.googleapis.com/auth/youtube.upload` and
     `https://www.googleapis.com/auth/youtube.force-ssl`.
   - Audience: add the channel owner's Google account as a test user, then **Publish app** ("In production"); in
     "Testing", refresh tokens expire after 7 days. Your own account needs no app verification: at consent, choose
     Advanced, then continue.
4. **Client.** Clients, Create client, type **Desktop app**. Download its JSON; keep it outside the repository.
5. **Refresh token**, on your computer, in the repository folder:

   ```bash
   python3 -m venv .venv-auth && .venv-auth/bin/pip install google-auth-oauthlib
   .venv-auth/bin/python tools/publish/get_refresh_token.py path/to/client_secret.json
   ```

   Sign in with the account that owns the channel (pick the Brand Account if asked). It prints `YOUTUBE_CLIENT_ID`
   and `YOUTUBE_REFRESH_TOKEN`; the client secret is `client_secret` in the JSON. Then delete the JSON and
   `.venv-auth`. Uploads go only to the channel named `youtube.expected_channel_title` in `config/channel.json`.
6. **API audit (for public videos).** API uploads from a project created after 28 July 2020 stay locked private
   until it passes Google's audit: fill in the "YouTube API Services - Audit and Quota Extension Form" (a
   single-channel publishing tool for your own channel). Until then, `YOUTUBE_UPLOAD=manual`.
7. **Channel.** Verify it by phone and set its audience to "not made for kids" (README.md, Quick start); unverified,
   the API cannot set the thumbnail.
8. **Search data key (optional).** Credentials, Create credentials, API key, restricted to the YouTube Data API v3:
   the repository secret `YOUTUBE_API_KEY`, read only by the search job. Without it, search demand uses YouTube
   suggestions only.

Quota: 10,000 units a day; a run uses about 2,200, plus up to 1,200 for search data (`max_api_queries_per_run` in
`config/search.json`).

## 6. GitHub environments and their secrets

Settings, Environments, New environment:

| Environment | Protection | Secrets |
|---|---|---|
| `staging` | Deployment branches: selected, `main` | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` |
| `publish` | **Required reviewers: you**, "Prevent self-review" unchecked; deployment branches: `main` | the three YouTube secrets; optional `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN` |
| `publish-label` | only for `APPROVAL_MODE=label`: no reviewers; branches: `main` | same as `publish` |

## 7. Repository variables

Settings, Secrets and variables, Actions, Variables:

| Variable | Set to | Meaning |
|---|---|---|
| `PIPELINE_ENABLED` | `true` | Kill switch: any other value stops runs before they start |
| `PUBLISH_ENABLED` | `true` | Read at approval: otherwise an approval publishes nothing |
| `SITE_BASE_URL` | `https://<owner>.github.io/<repo>` | Previews in the review issue; links in the description when links are on |
| `YOUTUBE_UPLOAD` | `api` (default) or `manual` | `manual`: you upload the approved video |
| `APPROVAL_MODE` | `environment` (default) or `label` | `label`: private repositories without required reviewers |
| `APPROVER_LOGIN` | your GitHub login | Label mode: only your labels count |
| `PREVIEW_MODE` | `pages` (default) or `artifact` | Where the explainer preview lives during review |
| `CLAUDE_SANDBOX` | unset (sandbox on) or `false` | `false` only if Claude Code's sandbox cannot start on the runner |
| `CLAUDE_BUDGET_SCOUT_USD`, `_RANK_`, `_WRITE_`, `_REVIEW_`, `_VIDEO_`, `_EPISODE_` | defaults 6, 3, 25, 25, 20, 20 | Dollar cap per Claude stage; `_REVIEW_` also caps the final-cut review (default 10): raise it for long explainers |
| `LINKEDIN_ENABLED`, `LINKEDIN_VERSION` | `true`, a current `YYYYMM` | Optional LinkedIn post |

## 8. GitHub Pages

The first staged run creates the `gh-pages` branch. Then Settings, Pages, Source "Deploy from a branch", branch
`gh-pages`, folder `/ (root)`. Published explainers appear at `<SITE_BASE_URL>/explainers/<slug>/` with their code.

## 9. Optional: LinkedIn

1. At developer.linkedin.com create an app (it needs a LinkedIn company page) with the products "Share on LinkedIn"
   (scope `w_member_social`) and "Sign In with LinkedIn using OpenID Connect".
2. Get a member access token with scopes `openid profile w_member_social` (the portal's OAuth token tool). Call
   `https://api.linkedin.com/v2/userinfo` with it; your author URN is `urn:li:person:<sub>`.
3. Add `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_AUTHOR_URN` to the `publish` environment, and the variables
   `LINKEDIN_ENABLED=true` and `LINKEDIN_VERSION`.

The token lasts 60 days and cannot be refreshed: renew it by hand. An expired token skips the post, never the
publication.

## 10. First runs

1. Actions, **Explainer pipeline**, Run workflow, `stop_after: produce`: Claude's part only. Read the job summary;
   download the `run-src` artifact.
2. Again with `stop_after: render`: adds the clean-checkout gates, narration and 1080p60 renders. Download `run-final`
   and watch `video/final/<slug>.mp4`.
3. Then `full`: private upload, preview and review issue. Approve or reject it to see the whole loop.

Other inputs: `mode`, `focus`, `series`, `episode`, `fresh` (step 11), `voice` (step 4) and `links` (`config` follows
`links.include`, default off; `on` adds the explainer and code links to this run's description and needs
`SITE_BASE_URL`).

## 11. Series mode

First commit the plan files a session sent you, under `series/<slug>/` (README.md, Quick start). Then Run workflow
with `mode: series`, `series:` that folder name and `episode: next` (the release order; it waits for an episode of
another series that it builds on) or a number; `fresh` leaves out the scenes kept for the episode. On approval the episode joins its series
playlist; then do the YouTube Studio steps the review issue lists (end screen, optional cards, once per series "Set as
official series for this playlist").

## 12. Day to day

- A run starts **every Monday** (the `cron` line in `.github/workflows/pipeline.yml`); one run is in review at a time.
- **You get** GitHub's deployment review notification and an issue labelled `pipeline:review` with the private video,
  the preview, the gates and the reviewers' findings.
- **Approve:** in the workflow run, Review deployments, tick `publish`, Approve and deploy. **Reject:** the same, with
  the reason in the comment box. Label mode: comment, then add `approve-publish` or `reject-publish`. No decision in
  30 days counts as not approved.
- **Stopped runs** open an issue labelled `pipeline:stopped` with the failed job.
- **Switch off:** `PIPELINE_ENABLED` to anything but `true`, or disable the workflow.
- **A rejected topic** is not picked again; to allow it, remove `rejected` from `skip_ledger_statuses` in
  `config/pipeline.json`, or its entry from `ledger.json` on `gh-pages`.

## 13. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Claude steps fail at start with a sandbox error | bubblewrap cannot start on the runner: set `CLAUDE_SANDBOX=false` |
| `invalid_grant` from YouTube | refresh token expired or revoked (consent screen in "Testing", or access removed): repeat step 5.5 |
| "authorised channel is ..." | step 5.5 signed in with another channel: repeat it, pick Remaining Action |
| Thumbnail warning in the review issue | channel not phone-verified (step 5.7) |
| `quotaExceeded` | more than about four runs in a day: wait for the daily reset |
| Narration job fails "needs AZURE_SUBSCRIPTION_KEY" | the voice is `azure` without the step 4 secrets |
| Narration job fails "the Piper voice model is not here" | the image was built without the model: rebuild it (Actions, CI image, Run workflow) |
| Final gate "narration present" fails | `voice.service` or the run's `voice` input is `silent` |
| A design, reading-time, self-contained or number-format gate fails | `review/design/<stage>/check_*.md` in the run artifact names the scene, the time and the text |
| Gate "series plan approved by the owner" fails | `series.plan_approval` is `required` and the plan is unapproved or changed: read `series/<slug>/PLAN.md`, run `./tools/human/approve_series.py series/<slug>` yourself, commit, start the episode again |
| Gate "series plan (owner approval optional)" fails | the plan changed after the episode started: start it again |
| Release gate fails, before the upload | an open blocker in the final-cut review, or it watched another version: read `review/final_cut/summary.md` in `run-final`; fix the scenes in a new run. "NOT INDEPENDENT": the session that made the video reviewed it |
| Preview link 404 | Pages not enabled yet (step 8) |
| Render job timeout | a scene too long or redrawing too much per frame: the gotchas in `.agents/skills/manim-video-producer/SKILL.md` |
| Unreachable records in a review, or "Sources unreadable from this network" in `ranking.md` | a session's network blocks doi.org, api.crossref.org, arxiv.org, Semantic Scholar, OpenAlex or publisher sites: allow the named hosts there, or let CI run it (GitHub-hosted runners reach them) |
| Search data all "unavailable" | no suggestion endpoint, `YOUTUBE_API_KEY` or Trends client: the ranking works without them |
| "search.json changed after the search job" | the search data was modified inside the Claude job: investigate before re-running |
