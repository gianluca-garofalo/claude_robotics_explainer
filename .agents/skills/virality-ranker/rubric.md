# Score anchors (0-5)

Weights, gates and the formula are in `config/rubric.json`, printed at the top of every `ranking.md`; the computed
criteria (recency from `bands_days`, search demand, supply gap) are not judged. Use the nearest anchor; 1 and 3 are
the levels in between.

| Criterion | 0 | 2 | 4 | 5 |
|---|---|---|---|---|
| **novelty** | restatement of known results or a product update | known method in a new setting | new method or capability with a paper and evidence | qualitatively new capability or idea, clearly beyond prior work in the primary source's own comparison |
| **visual_potential** | nothing moves; only tables or text | a plot or two would do | the key idea is a motion, geometry or trade-off that animates from equations or computed data | the idea is clearest as an animation (phase portraits, contact forces, trajectories, optimisation landscapes) and we can compute every frame |
| **audience_fit** (robotics and control researchers and students) | outside robotics | robotics-adjacent (general AI, business), or core robotics with no transferable idea (a product spec, a benchmark table) | core robotics (locomotion, manipulation, planning, estimation) with a method our audience could reuse | a result that changes how our audience would design, tune or prove something about controllers: new theory, or a technique with clear evidence that transfers across robots; its being about MPC or whole-body control is not enough by itself |
| **teachability** | cannot be reduced without losing the point | a qualitative story only | a toy model with a few equations reproduces the main effect | a toy model, a few equations and a script under 200 lines reproduce a number in the primary source or a faithful analogue |
| **hype_risk** (penalty) | claims match the primary source, limits stated | minor overstatement in coverage, primary source sober | headline claims beyond the primary source, or demo-only evidence for part of it | central claim rests on a video, press release or anonymous post; superlatives; undisclosed teleoperation or simulation |

- Topic area alone never earns a 4 or 5 on audience fit: an MPC or whole-body-control paper that applies a known
  formulation to a new robot is a 3, the normal score for a good core-robotics paper.
- Teachability is about our toy model: if you cannot name the equation and the script that would reproduce a number,
  it is at most 2.
- A company's popularity is not novelty, and many articles about one demo are not evidence: they raise the hype risk.
  Controversy is a penalty: a topic that spreads because it misleads costs credibility.
- 5 is rare: in one run, at most one candidate gets a 5 on a given criterion; if two seem to, the weaker is a 4. Write
  in the reason what would have made it one point higher.
- Ties are broken by teachability, then visual potential, then audience fit (`tie_breakers` in the config).

The score does not predict views, does not measure scientific importance, and ignores everything outside the rubric
(the user can approve any topic they want covered).
