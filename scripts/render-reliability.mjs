#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SITE = path.join(ROOT, 'site');
const SCRATCH = '/tmp/dcm-reliability-show-me.html';
const START = '<!-- reliability-examples:start -->';
const END = '<!-- reliability-examples:end -->';
const verifiedEvidence = new WeakMap();
const stagedEvidence = new WeakSet();
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const escape = (value) => String(value).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const canonical = (value) => JSON.stringify(value, (_, v) => v && !Array.isArray(v) && typeof v === 'object'
  ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b, 'en'))) : v);
const equal = (a, b) => canonical(a) === canonical(b);
const inside = (base, file) => file === base || file.startsWith(base + path.sep);
const git = (...args) => execFileSync('git', ['-C', ROOT, ...args], { maxBuffer: 16 * 1024 * 1024 });
const sourceFiles = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
  const file = path.join(dir, entry.name);
  return entry.isDirectory() ? sourceFiles(file) : entry.name.endsWith('.py') ? [path.relative(ROOT, file)] : [];
});
function bundleBytes(base) {
  if (fs.lstatSync(base).isSymbolicLink()) throw new Error('Evidence symlinks are not allowed.');
  const files = new Map();
  const visit = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) visit(file);
      else if (entry.isFile()) files.set(path.relative(base, file), fs.readFileSync(file));
      else throw new Error(`Evidence symlinks or special files are not allowed: ${file}`);
    }
  };
  visit(base);
  return files;
}

function unchangedBundle(base, expected) {
  const actual = bundleBytes(base);
  if (!equal([...actual.keys()].sort(), [...expected.keys()].sort())) throw new Error('Evidence changed on disk: bundle file set.');
  for (const [file, bytes] of expected) {
    if (!bytes.equals(actual.get(file))) throw new Error(`Evidence changed on disk: ${file}`);
  }
}
const at = (object, key) => key.split('.').reduce((v, part) => v?.[part], object);
const printed = (value) => value === undefined ? 'not returned' : typeof value === 'string' ? value : JSON.stringify(value);

function verifyMeasurements(resultsJSON, rawJSON) {
  const python = path.join(ROOT, 'worker/.venv/bin/python');
  const child = spawnSync(fs.existsSync(python) ? python : 'python3', [path.join(ROOT, 'scripts/reliability-benchmark.py'), '--verify-evidence'], {
    input: JSON.stringify({ results_json: resultsJSON, baseline_json: rawJSON.baseline, current_json: rawJSON.current }),
    encoding: 'utf8', maxBuffer: 32 * 1024 * 1024, timeout: 30_000,
  });
  if (child.error) throw new Error(`Evidence verifier failed: ${child.error.message}`);
  let verification;
  try { verification = JSON.parse(child.stdout); }
  catch { throw new Error(`Evidence verifier failed: ${child.stderr || 'invalid JSON response'}`); }
  if (child.status !== 0 || !Array.isArray(verification.problems) || verification.problems.length) {
    throw new Error(`Evidence verification failed:\n- ${verification.problems?.join('\n- ') || child.stderr || `exit ${child.status}`}`);
  }
  if (!Array.isArray(verification.publication_problems) || !Array.isArray(verification.assertions?.current) || !/^[a-f0-9]{64}$/.test(verification.report_sha256)) throw new Error('Evidence verifier returned incomplete outcomes.');
  return verification;
}

function retainedVerification(data, base, raw) {
  const verified = verifiedEvidence.get(data);
  if (!verified || verified.base !== fs.realpathSync(base) || verified.raw !== raw || verified.identity !== sha(canonical({ data, raw }))) throw new Error('Evidence changed or was not verified by loadEvidence.');
  unchangedBundle(verified.base, verified.files);
  if (!verified.files.get('results.json').equals(fs.readFileSync(verified.resultsPath))) throw new Error('Evidence changed on disk: input results.json.');
  return verified;
}

export function publicationProblems(data, base, raw) {
  const problems = [];
  let verified;
  try { verified = retainedVerification(data, base, raw); }
  catch (error) { return [error.message]; }
  problems.push(...verified.verification.publication_problems);
  if (data.run.phase !== 'integrated') problems.push(`phase is ${data.run.phase}, not integrated`);
  if (/provisional/i.test(data.run.qualification)) problems.push('run is explicitly qualified as provisional');
  if (data.run.current_source_changed_during_run !== false) problems.push('source drift during benchmark');
  for (const check of verified.verification.assertions.current) if (check.passed !== true) problems.push(`failed current assertion: ${check.id}`);
  if (data.run.current_head !== git('rev-parse', 'HEAD').toString().trim()) problems.push('HEAD differs from the measured snapshot base');
  if (sha(fs.readFileSync(path.join(ROOT, 'scripts/reliability-benchmark.py'))) !== data.run.harness_sha256) problems.push('benchmark source drift since run');
  const manifest = data.implementations.current.source.files;
  const currentFiles = [...sourceFiles(path.join(ROOT, 'worker/vision_worker')), 'worker/pyproject.toml'].sort();
  if (!equal(currentFiles, Object.keys(manifest).sort())) problems.push('worker source file set drift');
  for (const [file, hash] of Object.entries(manifest)) {
    if (!inside(ROOT, path.resolve(ROOT, file)) || !fs.existsSync(path.join(ROOT, file)) || sha(fs.readFileSync(path.join(ROOT, file))) !== hash) problems.push(`worker source drift: ${file}`);
  }
  for (const id of ['color_nine_stripes_rgb_plus_one', 'color_single_red_pixel', 'color_small_red_accent_missing']) {
    if (!data.cases.some((c) => c.id === id)) problems.push(`missing independent color control: ${id}`);
  }
  for (const side of ['baseline', 'current']) {
    for (const [id, row] of Object.entries(raw[side].cases)) if (row.status !== 'ok' || row.errors?.length) problems.push(`${side} execution failed: ${id}`);
  }
  return problems;
}

export function loadEvidence(resultsPath, evidenceBase) {
  const base = fs.realpathSync(evidenceBase);
  const files = bundleBytes(base);
  const read = (relative) => {
    if (typeof relative !== 'string' || path.isAbsolute(relative) || !inside(base, path.resolve(base, relative))) throw new Error('Evidence paths must be relative and inside the bundle.');
    const bytes = files.get(path.relative(base, path.resolve(base, relative)));
    if (!bytes) throw new Error(`Missing evidence file: ${relative}`);
    return bytes;
  };
  const readJSON = (relative) => JSON.parse(read(relative).toString('utf8'));
  const bytes = fs.readFileSync(resultsPath);
  if (!bytes.equals(read('results.json'))) throw new Error('Input results.json differs from the retained bundle.');
  const data = JSON.parse(bytes);
  if (data.schema_version !== '1.0') throw new Error(`Unsupported evidence schema: ${data.schema_version}`);
  if (typeof data.run.current_worker_dirty !== 'boolean' || !/^[a-f0-9]{40}$/.test(data.run.current_head) || !/^[a-f0-9]{40}$/.test(data.run.baseline_commit)) throw new Error('Missing exact revision or dirty-snapshot identity.');
  const sources = readJSON('raw/sources.json');
  const inputs = readJSON('raw/inputs.json');
  const raw = {};
  const rawJSON = {};
  if (new Set(data.cases.map((c) => c.id)).size !== data.cases.length || !equal(data.cases.map((c) => c.id).sort(), data.comparisons.map((c) => c.case_id).sort())) throw new Error('Case and comparison identities must match exactly, without duplicates.');
  if (!equal(inputs.cases, data.cases) || !equal(inputs.fixtures, data.fixtures)) throw new Error('Input declarations differ from retained raw inputs.');
  if (sha(read('raw/benchmark.py')) !== data.run.harness_sha256) throw new Error('Retained harness hash mismatch.');
  for (const side of ['baseline', 'current']) {
    const implementation = data.implementations[side];
    const hashes = Object.fromEntries(Object.entries(implementation.source.files).sort(([a], [b]) => a < b ? -1 : 1));
    if (sha(JSON.stringify(hashes, null, 2) + '\n') !== implementation.source.sha256) throw new Error(`${side} aggregate source hash mismatch.`);
    rawJSON[side] = read(implementation.raw).toString('utf8');
    raw[side] = JSON.parse(rawJSON[side]);
    const invocation = readJSON(`raw/${side}-invocation.json`);
    if (!equal(invocation.request.cases, data.cases)) throw new Error(`${side} did not receive the identical declared input pairs.`);
    if (invocation.request.repeats !== data.run.repeats || invocation.request.warmups !== data.run.warmups) throw new Error(`${side} invocation sample count mismatch.`);
    if (!equal(sources[side], implementation.source) || !equal(raw[side].environment.source_manifest, implementation.source)) throw new Error(`${side} source manifest mismatch.`);
    if (!equal(raw[side].environment, implementation.environment)) throw new Error(`${side} environment mismatch.`);
    for (const row of data.comparisons) {
      const measured = raw[side].cases[row.case_id];
      if (!measured || !equal(row[side].effective_params, measured.effective_params) || row[side].status !== measured.status) throw new Error(`Raw comparison mismatch: ${side}/${row.case_id}`);
    }
  }
  const verification = verifyMeasurements(bytes.toString('utf8'), rawJSON);
  if (sha(read('report.md')) !== verification.report_sha256) throw new Error('Report bytes mismatch: expected the authoritative report for verified results.');
  for (const key of ['python', 'executable', 'dependencies', 'thread_environment']) {
    if (!equal(raw.baseline.environment[key], raw.current.environment[key])) throw new Error(`Baseline/current environment differs: ${key}`);
  }
  const baselineInvocation = readJSON('raw/baseline-invocation.json');
  const currentInvocation = readJSON('raw/current-invocation.json');
  if (baselineInvocation.request.inputs !== currentInvocation.request.inputs) throw new Error('Pipeline versions did not use the same fixture directory.');
  const archiveDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dcm-verify-archive-'));
  try {
    const archive = path.join(archiveDir, 'source.zip');
    fs.writeFileSync(archive, read('raw/current-source.zip'));
    const retainedFiles = execFileSync('unzip', ['-Z1', archive], { encoding: 'utf8' }).trim().split('\n').sort();
    if (!equal(retainedFiles, Object.keys(data.implementations.current.source.files).sort())) throw new Error('Source snapshot ZIP file set mismatch.');
    for (const [file, hash] of Object.entries(data.implementations.current.source.files)) {
      if (sha(execFileSync('unzip', ['-p', archive, file], { maxBuffer: 16 * 1024 * 1024 })) !== hash) throw new Error(`Retained source ZIP hash mismatch: ${file}`);
    }
  } finally { fs.rmSync(archiveDir, { recursive: true, force: true }); }
  for (const [relative, fixture] of Object.entries(data.fixtures)) {
    if (sha(read(relative)) !== fixture.sha256) throw new Error(`Fixture bytes changed: ${relative}`);
  }
  if (sha(git('archive', data.run.baseline_commit, 'worker')) !== sources.baseline_archive_sha256) throw new Error('Baseline archive identity mismatch.');
  unchangedBundle(base, files);
  verifiedEvidence.set(data, { base, raw, verification, files, resultsPath: path.resolve(resultsPath), identity: sha(canonical({ data, raw })) });
  return Object.freeze({ data, base, raw, hash: sha(bytes), bytes: Buffer.from(bytes) });
}

// Staging copies only the private, verified buffers, never live source paths.
// Callers must remove stage.base in finally if it has not been installed.
export function stageEvidence(evidence, parent) {
  const verified = retainedVerification(evidence.data, evidence.base, evidence.raw);
  const stage = fs.mkdtempSync(path.join(parent, '.reliability-stage-'));
  try {
    for (const [relative, bytes] of verified.files) {
      const target = path.join(stage, relative);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, bytes);
    }
    unchangedBundle(stage, verified.files);
    const staged = loadEvidence(path.join(stage, 'results.json'), stage);
    retainedVerification(evidence.data, evidence.base, evidence.raw);
    stagedEvidence.add(staged);
    return staged;
  } catch (error) {
    fs.rmSync(stage, { recursive: true, force: true });
    throw error;
  }
}

export function installStagedEvidence(staged, destination) {
  if (!stagedEvidence.has(staged)) throw new Error('Installation requires a bundle returned by stageEvidence.');
  const verified = retainedVerification(staged.data, staged.base, staged.raw);
  if (fs.existsSync(destination)) {
    // Never overwrite an existing bundle, including a partial or corrupt one.
    unchangedBundle(destination, verified.files);
  } else fs.renameSync(staged.base, destination);
  return destination;
}

function atomicWrite(file, bytes) {
  const temp = fs.mkdtempSync(path.join(path.dirname(file), '.reliability-html-'));
  try {
    const staged = path.join(temp, 'index.html');
    fs.writeFileSync(staged, bytes);
    fs.renameSync(staged, file);
  } finally { fs.rmSync(temp, { recursive: true, force: true }); }
}

export function renderSection(evidence, prefix, preview, problems) {
  const { data, raw } = evidence;
  retainedVerification(data, evidence.base, raw);
  const url = (relative) => `${prefix}/${relative.split('/').map(encodeURIComponent).join('/')}`;
  const result = (id, side) => {
    const r = raw[side].cases[id]?.result;
    if (!r) throw new Error(`Required example missing: ${id}/${side}`);
    return r;
  };
  const scenario = (id) => {
    const c = data.cases.find((c) => c.id === id);
    if (!c) throw new Error(`Required fixture declaration missing: ${id}`);
    return c;
  };
  const value = (id, side, key) => at(result(id, side), key);
  const code = (v) => `<code>${escape(printed(v))}</code>`;
  const fields = (id, side, keys) => `<dl class="rel-fields">${keys.map(([label, key]) => `<div><dt>${escape(label)}</dt><dd>${code(key === 'cv_findings' ? value(id, side, key)?.map((f) => f.type) : value(id, side, key))}</dd></div>`).join('')}</dl>`;
  const snapshot = data.implementations.current.source.sha256;
  const before = `Before · ${data.run.baseline_commit.slice(0, 7)}`;
  const after = `After · ${data.run.current_worker_dirty ? 'dirty ' : ''}snapshot ${snapshot.slice(0, 12)}`;
  const pair = (id, keys) => `<div class="rel-results">${['baseline', 'current'].map((side) => `<section aria-label="${side === 'baseline' ? 'Previous pipeline' : 'Updated pipeline'}"><h4>${side === 'baseline' ? before : after}</h4>${fields(id, side, keys)}</section>`).join('')}</div>`;
  const image = (relative, alt) => {
    const fixture = data.fixtures[relative];
    if (!fixture) throw new Error(`Fixture metadata missing: ${relative}`);
    return `<a href="${escape(url(relative))}"><img src="${escape(url(relative))}" alt="${escape(alt)}" width="${fixture.shape[1]}" height="${fixture.shape[0]}" loading="lazy" /></a>`;
  };
  const fixtureAlt = (relative, side, frame) => {
    const name = path.posix.basename(relative);
    const origin = /^color-periodic-crop-(\d+)px\.png$/.exec(name)?.[1];
    return `${side === 'reference' ? 'Reference' : 'Candidate'} fixture ${name}${origin === undefined ? '' : `, crop origin y=${origin}`}${frame === undefined ? '' : `, frame ${frame}`}`;
  };
  const images = (id) => {
    const c = scenario(id);
    return `<div class="rel-inputs">${['reference', 'candidate'].map((side) => `<figure><figcaption>${side === 'reference' ? 'Reference' : 'Candidate · unchanged between pipelines'}</figcaption>${Array.isArray(c[side]) ? `<ol class="rel-strip">${c[side].map((p, i) => `<li>${image(p, fixtureAlt(p, side, i))}<span>Frame ${i}</span></li>`).join('')}</ol>` : image(c[side], fixtureAlt(c[side], side))}</figure>`).join('')}</div>`;
  };
  const provenance = (ids) => `<details class="rel-details"><summary>Inputs, settings and raw evidence</summary>${ids.map((id) => {
    const c = scenario(id);
    return `<h4>${escape(id)}</h4><p>${escape(c.description)}</p><pre>${escape(JSON.stringify({ reference: c.reference, candidate: c.candidate, params: c.params, context_manifest: c.context_manifest, fixtures: Object.fromEntries([...new Set([c.reference, c.candidate].flat())].map((p) => [p, Object.fromEntries(Object.entries(data.fixtures[p]).filter(([key]) => key !== 'rgb_histogram'))])), baseline: { effective_params: raw.baseline.cases[id].effective_params, unsupported_metadata_params: raw.baseline.cases[id].unsupported_metadata_params, alignment: result(id, 'baseline').alignment, canvas: result(id, 'baseline').canvas, provenance: result(id, 'baseline').provenance }, current: { effective_params: raw.current.cases[id].effective_params, alignment: result(id, 'current').alignment, canvas: result(id, 'current').canvas, diagnostics: result(id, 'current').diagnostics, provenance: result(id, 'current').provenance } }, null, 2))}</pre>`;
  }).join('')}<p><a href="${escape(url('raw/baseline.json'))}">Baseline raw JSON</a> · <a href="${escape(url('raw/current.json'))}">Current raw JSON</a> · <a href="${escape(url('report.md'))}">Run report</a></p></details>`;
  const table = (ids, key, label) => `<table class="rel-table"><caption>${escape(label)}</caption><thead><tr><th scope="col">Case</th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>${ids.map(([id, label]) => `<tr><th scope="row">${escape(label)}</th>${['baseline', 'current'].map((s) => `<td>${code(value(id, s, key))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const card = (n, title, body) => `<article class="rel-card rel-card-${n}" aria-labelledby="rel-title-${n}"><p class="rel-number">Example ${n} / 5</p><h3 id="rel-title-${n}">${title}</h3>${body}</article>`;
  const periodic = Array.from({ length: 5 }, (_, i) => [`color_periodic_crop_${i}px`, `Origin +${i}px`]);
  const colorKey = [['Color score', 'subscores.color.score'], ['Color status', 'subscores.color.status']];
  const issueKey = [['Diagnostic status', 'diagnostics.status'], ['Issues', 'diagnostics.issues']];
  const compactKeys = (id, side) => `<div><h4>${side === 'baseline' ? before : after}</h4>${fields(id, side, [['comparison_key', 'provenance.comparison_key'], ['run_key', 'provenance.run_key']])}</div>`;
  return `<section class="section reliability" id="reliability-examples" aria-labelledby="reliability-title" tabindex="-1">
<p class="eyebrow">${preview ? 'Provisional synthetic evidence · preview only' : 'Measured synthetic examples'}</p>
<h2 class="statement" id="reliability-title">See what changed in the comparison.</h2>
<p class="idea-note">The same generated inputs, run with the previous and updated pipelines. Before and after refer to pipeline versions, not a better-looking candidate. These cases test specific failure modes, not human ratings or whole-app fidelity.</p>
${preview ? `<aside class="rel-notice"><strong>Not for publication.</strong> This is recorded provisional evidence, not final integrated results. Independent color fixes are pending. Publication blockers at render time:<ul>${problems.map((p) => `<li>${escape(p)}</li>`).join('') || '<li>None found, but this remains an explicitly requested preview.</li>'}</ul></aside>` : ''}
<p class="rel-source">Baseline <code>${escape(data.run.baseline_commit)}</code><br />Updated ${data.run.current_worker_dirty ? 'dirty working-tree' : 'source'} snapshot <code>${escape(snapshot)}</code>. Base commit <code>${escape(data.run.current_head)}</code> is not a claim that the measured code equals HEAD.</p>
<p class="rel-links"><a href="${escape(url('results.json'))}">All results JSON</a> · <a href="${escape(url('report.md'))}">Report and checks</a> · <a href="${escape(url('raw/current-source.zip'))}">Exact updated source snapshot</a></p>
<div class="rel-cases">
${card(1, 'A tiny crop should not invent new colors.', `<p>Each 768 × 480 crop contains ten complete 48px periods and the same exact RGB histogram. Width normalization does not resample these inputs. This tests color stability only.</p>${images('color_periodic_crop_1px')}${table(periodic, 'subscores.color.score', 'Actual color scores by crop origin')}${pair('color_periodic_crop_1px', [['Layout score, +1px', 'subscores.layout.score'], ['Mode', 'alignment.mode']])}<p class="rel-reading">Read the color row separately from layout. Shifting the crop can change structure even when its color proportions stay the same. Widget mode intentionally skips registration.</p>${provenance(periodic.map(([id]) => id))}`)}
${card(2, 'A real color-mass swap must still register.', `<p>The colors stay the same. Light coverage changes from 81.25% to 18.75%. Candidate bytes are identical in both pipeline runs.</p>${images('color_mass_81_25_to_18_75')}${pair('color_mass_81_25_to_18_75', [...colorKey, ['Finding types', 'cv_findings']])}<p class="rel-reading">A lower color score on this changed input can be a useful correction. It does not establish semantic correctness or general perceptual accuracy.</p><details class="rel-details"><summary>True-change and identical-input controls</summary>${table([['color_mass_50_to_50', 'Identical 50% coverage'], ['accent_recolored', 'Accent recolored'], ['accent_missing', 'Accent removed']], 'subscores.color.score', 'Controls use the same before/after pipelines')}${images('accent_recolored')}<p>Robustness to tiny crops must not erase visible changes. These are separate generated control inputs, not improvements to the mass-swap candidate.</p></details>${provenance(['color_mass_81_25_to_18_75', 'color_mass_50_to_50', 'accent_recolored', 'accent_missing'])}`)}
${card(3, 'Equal energy can hide an opposite sampled rhythm.', `<p>The candidate reverses all nine frames. The amount of frame-to-frame change stays equal, but its sampled profile differs. No source timestamps or capture cadence are supplied.</p>${images('motion_reversed')}${pair('motion_reversed', [['motion_score', 'motion_score'], ['motion_energy_score', 'motion_energy_score'], ['Meaning', 'motion_score_meaning'], ['Energy ratio', 'energy_ratio'], ['Frame-index correlation', 'temporal_corr'], ['Timing status', 'timing_diagnostics.status'], ['Timing reason', 'timing_diagnostics.reason'], ['Timing score', 'timing_diagnostics.score']])}<p class="rel-reading">The energy score is not animation fidelity. Negative frame-index correlation describes these samples; unknown cadence leaves elapsed-time alignment inconclusive.</p><details class="rel-details"><summary>Static control and exact sampled signatures</summary>${pair('motion_both_static', [['motion_score', 'motion_score'], ['motion_status', 'motion_status'], ['Timing status', 'timing_diagnostics.status']])}${fields('motion_reversed', 'current', [['Reference signature', 'ref_signature'], ['Candidate signature', 'cand_signature'], ['Frame counts', 'frames']])}<p>A true null is shown as <code>null</code>. A field absent from the old worker is shown as <code>not returned</code>.</p></details>${provenance(['motion_reversed', 'motion_both_static'])}`)}
${card(4, 'Alignment fallback needs a review signal.', `<p>Different flat inputs make ECC undefined. Identity fallback is not successful registration, and a near-uniform observation is not proof of a failed capture.</p>${images('ecc_failure')}${pair('ecc_failure', [['Alignment method', 'alignment.method'], ['Fallback', 'alignment.fallback'], ['Outcome', 'alignment.outcome'], ['Reason', 'alignment.reason'], ...issueKey])}<p class="rel-reading">The old response already had a free-text fallback note. The updated result adds a stable outcome, reason and explicit review issue.</p><details class="rel-details"><summary>Identical flat-input control</summary>${pair('flat_identical_screen', [['Outcome', 'alignment.outcome'], ...issueKey])}<p>Inspect the control separately. Uniform content should not manufacture an unresolved-alignment warning.</p></details>${provenance(['ecc_failure', 'flat_identical_screen'])}`)}
${card(5, 'No compared pixels means inconclusive evidence.', `<p>These are the original textured inputs, before the declared full-image ignore rectangle. A legacy number can remain high or low even when no pixels remain in scope.</p>${images('scope_all_ignored')}${pair('scope_all_ignored', [['Legacy overall', 'overall'], ['Diagnostic status', 'diagnostics.status'], ['Compared fraction', 'diagnostics.scope.compared_fraction'], ['Issues', 'diagnostics.issues']])}${table([['scope_all_ignored', 'Equal modal fills'], ['scope_all_ignored_different_fill', 'Different modal fills']], 'overall', 'Legacy overall scores, not evidence of retained content')}<p class="rel-reading">Read the scope status before the number. Fill-based masks can affect metrics; they do not establish correctness of the ignored area.</p><details class="rel-details"><summary>Full image versus explicit crop, and identity keys</summary>${table([['header_omitted_full', 'Full omitted header'], ['header_omitted_scoped', 'Explicit common crop']], 'overall', 'Different scopes, not recovered content')}${images('header_omitted_full')}${images('header_omitted_scoped')}<p>The caller cropped both inputs to [0,80,384,320]. The matching crop excludes the missing header and avatar. It does not fix them. Crop and full-image scores answer different questions.</p><p>Worker identity keys for the all-ignored case are below. The baseline does not return these fields. A comparison key identifies the reference and settings; the run key also identifies the candidate. Caller context changes protocol identity, not pixel scores.</p><div class="rel-results">${compactKeys('scope_all_ignored', 'baseline')}${compactKeys('scope_all_ignored', 'current')}</div>${table([['header_omitted_full', 'No declared context'], ['settings_context_v1', 'Declared context v1'], ['settings_context_v2', 'Declared context v2']], 'provenance.comparison_key', 'Actual comparison keys; the baseline lacks this API')}</details>${provenance(['scope_all_ignored', 'scope_all_ignored_different_fill', 'header_omitted_full', 'header_omitted_scoped', 'settings_context_v1', 'settings_context_v2'])}`)}
</div>
<details class="rel-details rel-run"><summary>Run identity and reproduction</summary><p>Recorded ${escape(data.run.created_at)}. Phase <code>${escape(data.run.phase)}</code>. ${escape(data.run.qualification)}</p><p>${escape(data.run.api)}. Synthetic behavior checks do not establish perceptual accuracy, transport behavior or deployment readiness.</p><pre>${escape(data.run.command)}</pre><p>Fixture generation: ${escape(data.run.generator)}</p><p>Results SHA-256 <code>${evidence.hash}</code>. Harness SHA-256 <code>${escape(data.run.harness_sha256)}</code>.</p><pre>${escape(JSON.stringify({ baseline: data.implementations.baseline.source, current: data.implementations.current.source, environment: data.implementations.current.environment }, null, 2))}</pre><p><a href="${escape(url('raw/sources.json'))}">Source manifests</a> · <a href="${escape(url('raw/benchmark.py'))}">Exact fixture generator</a> · <a href="${escape(url('raw/inputs.json'))}">All input declarations and hashes</a></p></details>
</section>`;
}

function standalone(section, css) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Comparison reliability evidence preview</title><style>${css}\nhtml,body{background:transparent;margin:0;color:var(--foreground,var(--ink));font-family:var(--font-ui);line-height:1.5}body{overflow-x:visible}.reliability.section{max-width:1200px;margin:0 auto;padding:0;color:var(--foreground,var(--ink))}.reliability>.eyebrow,.reliability>.statement,.reliability>.idea-note,.rel-source,.rel-links,.rel-run{color:var(--foreground,var(--ink))}.rel-card,.rel-notice{color:var(--ink)}.reliability>.eyebrow{margin-top:0}.reliability>.statement{max-width:26ch}.reliability{padding-bottom:16px!important}</style></head><body><main>${section}</main></body></html>\n`;
}

export function main(argv) {
  const options = { results: 'docs/reliability/runs/final/results.json', output: 'site/index.html', preview: false };
  let positional = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--preview') options.preview = true;
    else if (['--evidence-base', '--output'].includes(arg)) {
      if (!argv[i + 1] || argv[i + 1].startsWith('--')) throw new Error(`Missing value for ${arg}`);
      options[arg === '--evidence-base' ? 'base' : 'output'] = argv[++i];
    } else if (arg === '--help') {
      console.log('node scripts/render-reliability.mjs [results.json] [--evidence-base RUN_DIRECTORY] [--preview --output /tmp/dcm-reliability-show-me.html]\nDefault: verified integrated evidence replaces the site insertion hook and retains its evidence under site/assets/reliability/. Report bytes and median deltas are verified by the current Python harness. Final rendering stages retained bytes, re-verifies the bundle, atomically installs assets without overwriting existing bundles, then atomically replaces the HTML. It also writes the self-contained scratch HTML. Preview never writes into site/.');
      return;
    } else if (!arg.startsWith('-') && !positional) { options.results = arg; positional = true; }
    else throw new Error(`Unknown argument: ${arg}`);
  }
  const resultsPath = path.resolve(ROOT, options.results);
  const output = path.resolve(ROOT, options.output);
  if (path.extname(output) !== '.html') throw new Error('Renderer output must be an .html document.');
  // Resolve the parent to reject symlink aliases into the publication directory.
  const actualOutput = path.join(fs.realpathSync(path.dirname(output)), path.basename(output));
  if (options.preview && (inside(fs.realpathSync(SITE), actualOutput) || (fs.existsSync(output) && inside(fs.realpathSync(SITE), fs.realpathSync(output))))) throw new Error('Preview output must be outside site/.');
  if (!options.preview && output !== path.join(SITE, 'index.html')) throw new Error('Final output must be site/index.html; use --preview for scratch HTML.');
  const evidence = loadEvidence(resultsPath, path.resolve(ROOT, options.base ?? path.dirname(resultsPath)));
  const problems = publicationProblems(evidence.data, evidence.base, evidence.raw);
  if (!options.preview && problems.length) throw new Error(`Publication refused:\n- ${problems.join('\n- ')}`);
  const css = fs.readFileSync(path.join(SITE, 'styles.css'), 'utf8');
  const tokens = css.slice(css.indexOf(':root {'), css.indexOf('\n* {'));
  const reliabilityCSS = css.slice(css.indexOf('/* reliability:start */'), css.indexOf('/* reliability:end */'));
  if (!reliabilityCSS || reliabilityCSS.includes('vh')) throw new Error('Missing or unsupported reliability CSS.');
  const scratch = (bundle, prefix) => standalone(renderSection(bundle, prefix, options.preview, problems), `${tokens}\n*{box-sizing:border-box}img{max-width:100%}figure{margin:0}code,pre{font-family:var(--font-mono)}\n${reliabilityCSS}`);
  if (options.preview) atomicWrite(output, scratch(evidence, evidence.base));
  else {
    const indexPath = path.join(SITE, 'index.html');
    const html = fs.readFileSync(indexPath, 'utf8');
    if (html.split(START).length !== 2 || html.split(END).length !== 2 || html.indexOf(START) > html.indexOf(END)) throw new Error('Expected one ordered insertion hook.');
    const relative = `assets/reliability/${evidence.hash.slice(0, 16)}`;
    const destination = path.join(SITE, relative);
    const section = renderSection(evidence, relative, false, []);
    let updated = html.slice(0, html.indexOf(START) + START.length) + '\n' + section + '\n    ' + html.slice(html.indexOf(END));
    for (const id of ['loop', 'try']) {
      const beginning = updated.indexOf(`id="${id}"`);
      const end = updated.indexOf('</section>', beginning);
      if (beginning < 0 || end < 0) throw new Error(`Missing link target section: ${id}`);
      if (!updated.slice(beginning, end).includes('href="#reliability-examples"')) updated = updated.slice(0, end) + '  <p class="idea-note"><a href="#reliability-examples">See measured synthetic examples</a></p>\n    ' + updated.slice(end);
    }
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    const staged = stageEvidence(evidence, path.dirname(destination));
    try {
      const scratchHTML = scratch(staged, destination);
      const lateProblems = [...publicationProblems(evidence.data, evidence.base, evidence.raw), ...publicationProblems(staged.data, staged.base, staged.raw)];
      if (lateProblems.length) throw new Error(`Publication refused after staging:\n- ${lateProblems.join('\n- ')}`);
      // A complete validated directory becomes visible in one rename. Existing
      // content-addressed assets are compared byte-for-byte, never overwritten.
      installStagedEvidence(staged, destination);
      atomicWrite(indexPath, updated);
      atomicWrite(SCRATCH, scratchHTML);
    } finally { fs.rmSync(staged.base, { recursive: true, force: true }); }
  }
  console.log(`${options.preview ? 'Preview only' : 'Verified evidence rendered'}: ${output}\nResults SHA-256: ${evidence.hash}\nSource snapshot: ${evidence.data.implementations.current.source.sha256}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(process.argv.slice(2)); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
