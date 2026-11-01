export const meta = {
  name: 'review-fanout',
  description: 'Review an explainer run: five independent reviewers in parallel, adversarial verification of every blocker or major finding, merged summary',
  whenToUse: 'Optional workflow version of the explainer-review skill (steps 1-4). Pass the run folder, e.g. /review-fanout runs/2026-10-30-my-topic',
  phases: [
    { title: 'Review', detail: 'technical correctness, references, presentation, red team, linear reader (in parallel)' },
    { title: 'Verify', detail: 'one finding-verifier per blocker or major finding, as soon as its reviewer finishes' },
    { title: 'Merge', detail: 'tools/merge_reviews.py writes review/summary.md' },
  ],
}

// The run folder comes in through args: a string, an array or {run: "..."}.
const run = (typeof args === 'string' ? args : Array.isArray(args) ? args[0] : args && args.run || '').trim()
if (!run) throw new Error('pass the run folder, e.g. /review-fanout runs/2026-10-30-my-topic')

const REVIEWERS = [
  'technical-correctness-reviewer',
  'reference-verifier',
  'presentation-reviewer',
  'claims-red-team',
  'linear-reader',
]

const FINDINGS = {
  type: 'object',
  required: ['reviewer', 'findings'],
  properties: {
    reviewer: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'severity', 'location', 'issue'],
        properties: {
          id: { type: 'string' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          location: { type: 'string' },
          issue: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT = {
  type: 'object',
  required: ['finding', 'verdict', 'reason'],
  properties: {
    finding: { type: 'string' },
    verdict: { type: 'string', enum: ['confirmed', 'refuted', 'uncertain'] },
    reason: { type: 'string' },
  },
}

log(`Reviewing ${run} with ${REVIEWERS.length} independent reviewers`)

// No barrier between reviewers: a reviewer's serious findings are verified as soon as that reviewer finishes.
const results = await pipeline(
  REVIEWERS,
  name => agent(
    `Review the explainer in ${run}. Follow your instructions: write ${run}/review/${name}.json and ${run}/review/${name}.md, ` +
    `validate them with python3 tools/validate.py ${run}, then return the id, severity, location and issue of every finding.`,
    { agentType: name, label: name, phase: 'Review', schema: FINDINGS },
  ),
  async (report, name) => {
    if (!report) return { reviewer: name, failed: true, findings: [], verdicts: [] }
    const serious = report.findings.filter(f => f.severity === 'blocker' || f.severity === 'major')
    const verdicts = await parallel(serious.map(f => () => agent(
      `Run folder: ${run}. Finding ${f.id} in ${run}/review/${name}.json (${f.severity}, ${f.location}): ${f.issue}\n` +
      `Try to refute it and write ${run}/review/verify/${f.id}.json as your instructions say.`,
      { agentType: 'finding-verifier', label: `verify ${f.id}`, phase: 'Verify', schema: VERDICT },
    )))
    return { reviewer: name, failed: false, findings: report.findings, verdicts: verdicts.filter(Boolean) }
  },
)

const done = results.filter(Boolean)
const failed = REVIEWERS.filter(n => !done.some(r => r.reviewer === n && !r.failed))
if (failed.length) log(`Reviewers that returned nothing (rerun them): ${failed.join(', ')}`)

const merge = await agent(
  `From the repository root run: python3 tools/merge_reviews.py ${run}\nReturn its output unchanged.`,
  { label: 'merge reviews', phase: 'Merge' },
)

return {
  run,
  reviewers: done.map(r => ({
    reviewer: r.reviewer,
    findings: r.findings.length,
    blockerOrMajor: r.findings.filter(f => f.severity === 'blocker' || f.severity === 'major').map(f => f.id),
  })),
  verdicts: done.flatMap(r => r.verdicts.map(v => `${v.finding}: ${v.verdict} (${v.reason})`)),
  failedReviewers: failed,
  merge,
  next: `Read ${run}/review/summary.md, fix confirmed findings in draft/, code/ or references.json, record decisions in ` +
        `${run}/review/resolutions.json, rebuild, rerun the checks and tools/merge_reviews.py.`,
}
