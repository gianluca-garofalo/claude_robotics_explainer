export const meta = {
  name: 'review-fanout',
  description: 'Independent review of one review set of a run: its reviewers in parallel, each report checked, the blocker and major findings verified per report, then merged',
  whenToUse: 'The explainer-review, manim-video-producer (design review), final-cut-review and plan-series skills run it with the object that python3 tools/merge_reviews.py RUN --set SET --workflow-args prints as args: run, set and reviewers',
  phases: [
    { title: 'Review', detail: 'the reviewers of the set in parallel, each given only the run path and its report path' },
    { title: 'Check', detail: 'the checks of tools/validate.py on each report (merge_reviews.py --pending); a reviewer whose report fails goes back once with the errors' },
    { title: 'Verify', detail: 'the blocker and major findings of each report, batched for one finding-verifier (at most four findings each)' },
    { title: 'Merge', detail: 'tools/merge_reviews.py for the set' },
  ],
}

// args: {run, set, reviewers}, printed by tools/merge_reviews.py --workflow-args, and for a second round an optional
// focus (the changed sections, never a view of them). The reviewers of each set are kept in tools/gate.py (REVIEWERS,
// VIDEO_REVIEWERS) and tools/merge_reviews.py (series_plan), never here.
const SETS = {
  explainer: { folder: 'review', what: 'the built explainer' },
  video: { folder: 'review/video', what: 'the draft renders of the video', stage: 'draft' },
  final_cut: { folder: 'review/final_cut', what: 'the assembled video', stage: 'final' },
  series_plan: { folder: 'review/series_plan', what: 'the proposed series plan' },
}
const MAX_BATCH = 4            // findings per finding-verifier: a report with more gets several verifiers
const HOW = 'python3 tools/merge_reviews.py runs/RUN --set SET --workflow-args prints them'

let a = args
if (typeof a === 'string' && a.trim().startsWith('{')) {
  try { a = JSON.parse(a) } catch (e) { a = {} }
}
a = a && typeof a === 'object' && !Array.isArray(a) ? a : {}
const run = String(a.run || '').trim().replace(/\/+$/, '')
const set = String(a.set || '')
const reviewers = Array.isArray(a.reviewers) ? a.reviewers : []
const focus = typeof a.focus === 'string' ? a.focus.trim() : ''
if (!/^[\w./-]+$/.test(run)) throw new Error(`args.run must be the run folder, e.g. runs/2026-10-30-my-topic (${HOW})`)
if (!Object.prototype.hasOwnProperty.call(SETS, set)) {
  throw new Error(`args.set must be one of ${Object.keys(SETS).join(', ')} (${HOW})`)
}
if (!reviewers.length || !reviewers.every(n => typeof n === 'string' && /^[a-z0-9-]+$/.test(n))) {
  throw new Error(`args.reviewers must list the reviewers of the set (${HOW})`)
}
const S = SETS[set]
const dir = `${run}/${S.folder}`

const COMMAND = {
  type: 'object',
  required: ['exit_code', 'output'],
  properties: {
    exit_code: { type: 'integer', description: 'the exit status of the command' },
    output: { type: 'string', description: 'its stdout and stderr, complete and unchanged' },
  },
}
const VERDICTS = {
  type: 'object',
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['finding', 'verdict', 'reason'],
        properties: {
          finding: { type: 'string' },
          verdict: { type: 'string', enum: ['confirmed', 'refuted', 'uncertain'] },
          reason: { type: 'string' },
        },
      },
    },
  },
}

// A workflow script has no shell: the mechanical review-runner agent runs each tool command for it.
const command = (cmd, label, phase) => agent(
  `Run this command once, from the repository root, and return its exit status and complete output:\n${cmd}`,
  { agentType: 'review-runner', label, phase, schema: COMMAND },
)

const reviewPrompt = name =>
  `Run folder: ${run}. Review ${S.what}${S.stage ? ` (stage: ${S.stage})` : ''}, following your instructions and ` +
  '.agents/skills/explainer-review/reviewer-contract.md.\n' +
  `Your report: ${dir}/${name}.json and its .md; if that report exists, this is a later round: write the next round ` +
  `file beside it. You are an independent subagent: write "independent": true and "reviewed_by": "${name} subagent" ` +
  'at its top level.\nYou get only the run path on purpose: form your own view.' +
  (focus ? `\nThis round covers only what changed since your last report: ${focus}.` : '')

const fixPrompt = (name, c) =>
  `${reviewPrompt(name)}\n\nThe report check (tools/validate.py and the independence fields) fails for ${c.report}:\n` +
  c.errors.map(e => `- ${e}`).join('\n') +
  '\nIf the report exists, fix what these errors name and keep its findings; if it is missing, do the review and ' +
  'write it.'

const verifyPrompt = (report, ids) => {
  const folder = report.replace(/\/[^/]+$/, '')
  return `Run folder: ${run}. Report: ${report}.\n` +
    (ids.length === 1 ? 'Verify its finding ' : `Verify these ${ids.length} findings of it, each on its own: `) +
    `${ids.join(', ')}, following your instructions. Write one verdict file per finding:\n` +
    ids.map(id => `- ${id}: ${folder}/verify/${id}.json`).join('\n')
}

const chunks = (xs, n) => Array.from({ length: Math.ceil(xs.length / n) }, (_, i) => xs.slice(i * n, i * n + n))

// The reviewer's newest report checked with tools/validate.py, and its blocker and major findings without a verdict.
async function check(name) {
  const res = await command(`python3 tools/merge_reviews.py ${run} --set ${set} --pending ${name}`, `check ${name}`,
    'Check')
  const line = String((res && res.output) || '').split('\n').map(s => s.trim()).filter(s => s.startsWith('{')).pop()
  let out = null
  try { out = line ? JSON.parse(line) : null } catch (e) { out = null }
  if (!out || !Array.isArray(out.errors) || !Array.isArray(out.verify)) {
    return { report: `${dir}/${name}.json`, errors: [], verify: [], checked: false,
      note: res ? `the check printed no result (exit ${res.exit_code}): ${String(res.output).slice(-300)}`
        : 'the check did not run' }
  }
  return { report: out.report, errors: out.errors, verify: out.verify, checked: true }
}

log(`Reviewing ${run} (${set}) with ${reviewers.length} independent reviewer(s): ${reviewers.join(', ')}`)

// No barrier between reviewers: each report is checked and its serious findings verified as soon as it is written.
const results = await pipeline(
  reviewers,
  name => agent(reviewPrompt(name), { agentType: name, label: name, phase: 'Review' }).then(text => ({ text })),
  async (prev, name) => {
    if (!prev || prev.text === null || prev.text === undefined) {
      return { reviewer: name, failed: true, resent: false, checked: false, errors: [], verify: [] }
    }
    let c = await check(name)
    let resent = false
    if (c.checked && c.errors.length) {
      log(`${name}: its report fails the check; sent back once with the errors`)
      resent = true
      await agent(fixPrompt(name, c), { agentType: name, label: `${name} (report fix)`, phase: 'Review' })
      c = await check(name)
    }
    return { reviewer: name, failed: false, resent, ...c }
  },
  async r => {
    if (r.failed || !r.checked || r.errors.length || !r.verify.length) return { ...r, verdicts: [] }
    const batches = r.verify.flatMap(v => chunks(v.findings, MAX_BATCH).map(ids => ({ report: v.report, ids })))
    if (batches.length > r.verify.length) {
      log(`${r.reviewer}: more than ${MAX_BATCH} serious findings in a report, so ${batches.length} verifiers`)
    }
    const out = await parallel(batches.map(b => () => agent(verifyPrompt(b.report, b.ids), {
      agentType: 'finding-verifier', label: `verify ${b.ids.join(' ')}`, phase: 'Verify', schema: VERDICTS,
    })))
    return { ...r, verdicts: out.filter(Boolean).flatMap(v => v.verdicts) }
  },
)

const done = results.filter(Boolean)
const failed = reviewers.filter(n => !done.some(r => r.reviewer === n && !r.failed))
const invalid = done.filter(r => !r.failed && r.errors.length).map(r => r.reviewer)
const unchecked = done.filter(r => !r.failed && !r.checked).map(r => `${r.reviewer}: ${r.note}`)
if (failed.length) log(`Reviewers that returned nothing (run them again): ${failed.join(', ')}`)
if (invalid.length) log(`Reports that still fail the check: ${invalid.join(', ')}`)

const merge = await command(`python3 tools/merge_reviews.py ${run} --set ${set}`, 'merge', 'Merge')

return {
  run,
  set,
  reviewers: done.map(r => ({ reviewer: r.reviewer, report: r.report, resent: r.resent, errors: r.errors,
    verified: (r.verdicts || []).map(v => v.finding) })),
  verdicts: done.flatMap(r => (r.verdicts || []).map(v => `${v.finding}: ${v.verdict} (${v.reason})`)),
  failedReviewers: failed,
  invalidReports: invalid,
  uncheckedReports: unchecked,
  merge: merge ? { exit: merge.exit_code, output: merge.output }
    : `not run: python3 tools/merge_reviews.py ${run} --set ${set}`,
  next: `Read ${dir}/summary.md. Run failed reviewers again, fix invalid reports through their reviewer, ` +
    'verify what is still unverified, then fix confirmed findings as the calling skill says, record decisions in ' +
    `${dir}/resolutions.json and merge again.`,
}
