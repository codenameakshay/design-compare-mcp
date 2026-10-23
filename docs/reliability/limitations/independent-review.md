# Independent read-only color review

Verdict: PASS for the supplied frozen v2 contract. No blocking correctness,
certificate, runtime, metadata, or test-weakening finding was established.
One independently reproduced close-hue monotonicity limitation is recorded
below. This is not universal monotonicity or perceptual-accuracy approval.

No agents, commits, repository edits, website writes, evidence publication,
full color suite, or full npm suite were performed. All new files are in this
/tmp directory. Existing uncommitted work was preserved.

## Exact scope and identities

Repo: /Users/codenameakshay/Development/codenameakshay/design-compare-mcp.
Base resolves to b7139a2d29bc5fd2cae567688e5660b501f509ec. The reviewed
implementation is uncommitted, so this commit is not its delivery identity.

SHA256 identities held throughout the independent production probes:

- worker/vision_worker/metrics/color.py:
  296712351518bf2a88b46dcfa9f0811dc8ce68f8c1989d09d624e87d62724e46
- worker/tests/test_color_stability.py:
  812b4e44f88807852013547e9f3c1d58f6876a86cdf229f03dcb3b596471a7e1
- worker/vision_worker/pipeline.py:
  e121550fb92801346b0aca9c99e615c503eb59b0eebff27a26a6cd502faed76e
- README.md:
  ed8c893d4cf0e8721e9334f4380cfc76fa8ff38e28708249424a2cefa0af0f34
- calibration/README.md:
  32be2e8b95a0414a5dc1f97a80127f9a7f3b0117d199ee5fd07e0d251f654357

Read the three requested historical/design reports and the final implementation
report. The final implementation report was rehashed as
4fc71eeb24f4b053aa5e141d2254f41f98078cf37ddb0518ec34274baf3552c2.
Implementation-reported 41/41, worker/calibration, stable integrated V5 98/98,
and six fresh pipeline deadlines are separate implementation evidence. They
were not rerun or used to override the independent checks below. Final generated
website/assets and any later documentation regeneration are outside this review.

## Standards

Manual no-comments/suppressions inspection found no substantive new suppression
or comment-dependent correctness workaround in the v2 change. The existing
E402 import suppressions are present in the pre-v2 test snapshot as well. No
comments were removed or edits proposed solely to reduce comment count.

The v1-to-v2 source diff has one coverage policy. Obsolete helpers were removed,
not retained as competing paths. Independent AST extraction confirms all 17
public literal numeric/geometric policy constants equal v1. Whitespace checks
for the tracked reviewed files passed.

## Spec and correctness

- Lines 105-129 implement source-query alpha on BOTH own and target occupancy
  in each direction. The reverse direction uses its own source alpha. There is
  no target-density normalization substituted into the opposite direction.
- Histogram mass assignment is trilinear, processes every pixel in batches,
  and has no palette cardinality, shortlist, exact-search, or sampling branch.
  All 393,216 integer RGB samples on the six gamut faces fit the fixed lattice;
  their histogram is nonnegative and sums to 1. This is a domain probe, not an
  exhaustive test of every integer RGB triplet or floating-point input.
- The mass calculation is the exact CDF-gap integral for each of the fixed
  unit directions, followed by a maximum. Its documented interpretation is
  lattice projected W1, not 3D transport or input-space CIEDE2000.
- The score path is continuous in valid normalized histogram masses and
  barycentric coordinates. Floor changes in assignment meet at shared node
  weights. Density correction has a fixed positive denominator floor;
  normalized importance has a positive mass denominator. Exponential, positive
  part, maximum, and fixed integrals preserve continuity. Reporting thresholds
  intentionally need not preserve finding lists.
- Boundary direct calls reproduce mass256/257 scores
  58.96582448164317 / 58.9658193789908, M=7.996692496379749, distribution only.
  Support32/33 gives 77.31626827527465 / 77.31751640583639, coverage-deficit only.
  Both pairs have zero observed argument-symmetry and pixel-reversal error.
- Original four-width scores independently reproduce
  77.8790434934525, 65.78291692049561, 39.2019171831281, 37.7967580879949.
  The original strict ordering is repaired without a tolerance or retuning.
- An independent sparse-node oracle directly evaluates radial kernels and
  finite Gaussian density, rather than using FFT convolutions. Across 900 new
  seeded families with 1-6 shared background colors and 15 mass fractions,
  it found the one close-hue limitation below. Four actual production-histogram
  cross-checks have coverage error <=2.14e-14 and mass error <=6.76e-13.
- 80 new near-RGB+1 palette cases have minimum score 98.00493676630605,
  no findings, and zero certified absence. They use seeds outside the suite.
- At 768 squared, independent contamination counts 1/59/590/7373/29491 score
  99.9994941 / 99.9629520 / 97.5087463 / 62.6924576 / 30.2416418.
  The specified 38-column injection control reproduces
  30.436102279019327 -> 30.486711184212 and retains a material non-absence
  coverage-deficit report after the matching pixel invalidates literal absence.
- Certificate soundness is supported by the guard proof: each contributing
  original pixel is within sqrt(3)*4 of its lattice node. For certified source
  nodes, every occupied target node is farther than 10+2*sqrt(3)*4; triangle
  inequality then excludes any original target pixel within proxy distance 10.
  Summing the certified fractions cannot exceed the originating absent pixel
  mass. Independent exhaustive actual-pixel proxy distances on 180 new palette
  pairs confirm this bound, including 105 nonzero missing and 118 nonzero added
  cases. Maximum computed excess is 1.11e-16, ordinary summation roundoff.
- Work is O(pixels) plus fixed lattice/projection/convolution work. No
  input-dependent search or iteration count remains. Apart from input storage
  and possible reshape copies for noncontiguous caller arrays, conversion uses
  a bounded pixel batch and fixed-size metric arrays. One independent production
  768-noise color call took 0.342923s; this review process peaked at 333,250,560
  bytes including scientific/pipeline imports and retained review arrays.
  These are descriptive host samples, not a universal latency/memory guarantee.
- An actual compare_arrays call returns color status=scored, the current proxy
  reason string, v2 metadata, raw S, weighted .9*S, and max(M,.9*S). Root and
  calibration docs match these semantics and explicitly label old example
  palette/CIEDE fields as historical. No obsolete units or false transport
  correspondence were found in current color pipeline wording.

## Six-color migration and test weakening

The fixture is unchanged and independently scores 73.1225657097306 <80.
The only finding is color_missing, certified missing mass is approximately .1,
added mass is 0, and weighted coverage is 5.9476302381654 >1.

Purple's nearest actual reference color is blue at proxy distance
18.543698052501963, so actual added absent mass is .1. The conservative lattice
certificate fails to establish that absence. Its zero is not proof of a
counterpart within 10. The narrower reported finding is therefore appropriate
under the accepted versioned proof contract; fabricating color_added or
color_shift would be unjustified. Missing numeric detection was not hidden.

The v1-to-v2 test diff changes the two version-dependent pair score anchors,
metadata/version expectations, and this explicitly authorized finding contract.
It adds two monotonicity methods. Original score bands, fixtures, original
strict four-width monotonicity, two-sided recolor finding controls, injection
bounds, and deadline thresholds remain. Against the earlier rejected-source
test snapshot, the removed nearest-CIEDE/shortlist/search implementation oracles
are obsolete for the explicitly new metric, not required compatibility gates.
The crop raw-field tolerance is a documented migration from a rounded old
measurement, not a relaxation of the retained score/no-findings behavior.

## Non-blocking limitation: close-hue mass ordering

The broader independent sweep has one family with a score increase above 1e-8.
This is real nonmonotonicity, not floating-point noise. Exact direct production
reproduction is in reversal.py and reversal.json.

Use 1x8000 RGB arrays. Shared background is [255,29,255]. Reference accent is
[35,136,71], candidate accent is [53,133,76]. The accent colors are only
2.15159 projected proxy units apart in the full-mass lattice comparison.

- 200 accent pixels (2.5%): score 98.13473999163266, M=.05378984770330504,
  S=.3974959125073355.
- 400 accent pixels (5%): score 98.60237748044528, M=.10757969540661008,
  S=.29713492617413473.
- 600 and 800 pixels: score approximately 98.723534432987.

Thus doubling a small close-hue recolor improves similarity by .46763749.
Neither endpoint has an absence certificate or finding. The 2.5% and 5%
reversal values are IDENTICAL in frozen v1. The rejected pre-lattice heuristic
scored those endpoints 96.2895223 and 94.4862360; those old values are not numeric
compatibility gates or an accuracy oracle for this new metric.

This does not violate a claimed universal ordering theorem, because none is
claimed. It does not cross an existing material-detection or near-color gate,
and does not reverse the repaired original family. I classify it as a scoped
limitation, not a blocking new detection regression. Preserve this repro and
do not describe the six retained representative families or the design's
80-family sweep as evidence of general monotonicity. The other 899 independently
sampled families had no increases above 1e-8 at the tested fractions. The sweep
is finite and not held-out human-label validation.

## Reproduction

Run from the repository using its interpreter, without bytecode writes:

    env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 worker/.venv/bin/python -B /tmp/dcm-color-independent-BFGhsf/review.py
    env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 worker/.venv/bin/python -B /tmp/dcm-color-independent-BFGhsf/targeted.py
    env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 worker/.venv/bin/python -B /tmp/dcm-color-independent-BFGhsf/reversal.py

Results are sweep.json, targeted.json, and reversal.json. Scripts only write
these /tmp artifacts. The parent still owns final generated evidence checks,
publication, and any later source changes. No release/global-accuracy claim is
made by this review.
