import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { after, test } from 'node:test';
import { installStagedEvidence, loadEvidence, main, publicationProblems, renderSection, stageEvidence } from './render-reliability.mjs';

// node scripts/render-reliability-test.mjs [retained-run-directory]
// All mutations, real boundary calls and preview outputs stay in temporary dirs.
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fixture = path.resolve(ROOT, process.argv[2] ?? 'docs/reliability/runs/final');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'dcm-renderer-regression-'));
const base = path.join(temp, 'evidence');
const python = fs.existsSync(path.join(ROOT, 'worker/.venv/bin/python')) ? path.join(ROOT, 'worker/.venv/bin/python') : 'python3';
fs.cpSync(fixture, base, { recursive: true });
after(() => fs.rmSync(temp, { recursive: true, force: true }));

function reset() {
  for (const name of ['results.json', 'report.md', 'raw/baseline.json', 'raw/current.json']) fs.copyFileSync(path.join(fixture, name), path.join(base, name));
}

function mutate(file, statement) {
  execFileSync(python, ['-c', `import json, pathlib\np = pathlib.Path(${JSON.stringify(path.join(base, file))})\nd = json.loads(p.read_text())\n${statement}\np.write_text(json.dumps(d, indent=2, sort_keys=True, allow_nan=False) + '\\n')`]);
}

function rejects(file, statement) {
  reset();
  mutate(file, statement);
  assert.throws(() => loadEvidence(path.join(base, 'results.json'), base), /mismatch|invalid|missing|duplicate|failed|incomplete|assertion|trial|sample|result|check/i);
}

test('complete retained evidence renders real values and preserves baseline failures', () => {
  reset();
  const evidence = loadEvidence(path.join(base, 'results.json'), base);
  assert.equal(evidence.raw.current.cases.scope_all_ignored.result.overall, 100);
  assert.equal(evidence.data.assertions.baseline.find(c => c.id === 'motion_reversed_semantics').passed, false);
  assert.equal(evidence.data.assertions.current.find(c => c.id === 'motion_reversed_semantics').passed, true);
  const problems = publicationProblems(evidence.data, base, evidence.raw);
  assert.equal(problems.includes('Evidence changed or was not verified by loadEvidence.'), false);
  const html = renderSection(evidence, base, true, problems);
  assert.equal((html.match(/class="rel-card rel-card-/g) ?? []).length, 5);
  assert.match(html, /Legacy overall<\/dt><dd><code>100<\/code>/);
  assert.match(html, /src="[^"]*\/color-periodic-crop-0px\.png" alt="Reference fixture color-periodic-crop-0px\.png, crop origin y=0"/);
  assert.match(html, /src="[^"]*\/color-periodic-crop-1px\.png" alt="Candidate fixture color-periodic-crop-1px\.png, crop origin y=1"/);
  assert.match(html, /src="[^"]*\/motion-reference-00\.png" alt="Reference fixture motion-reference-00\.png, frame 0"/);
  assert.match(html, /src="[^"]*\/motion-reversed-00\.png" alt="Candidate fixture motion-reversed-00\.png, frame 0"/);
  const output = path.join(temp, 'preview.html');
  main([path.join(base, 'results.json'), '--evidence-base', base, '--preview', '--output', output]);
  assert.match(fs.readFileSync(output, 'utf8'), /<strong>Not for publication\.<\/strong>/);
});

for (const side of ['baseline', 'current']) {
  test(`${side} rejects a fabricated displayed overall`, () => rejects(`raw/${side}.json`, 'd["cases"]["scope_all_ignored"]["result"]["overall"] = 987654.321'));
  for (const group of ['warmups', 'trials']) {
    for (const [id, field, value] of [
      ['scope_all_ignored', '["diagnostics"]', '{"status": "fabricated"}'],
      ['scope_all_ignored', '["provenance"]', '{"comparison_key": "fabricated"}'],
      ['motion_reversed', '["motion_score"]', '987654.321'],
      ['motion_reversed', '["timing_diagnostics"]', '{"status": "fabricated"}'],
    ]) {
      test(`${side} validates ${group} ${id}${field}`, () => rejects(`raw/${side}.json`, `d["cases"]["${id}"]["${group}"][-1]["result"]${field} = ${value}`));
    }
    test(`${side} rejects an incomplete ${group} set`, () => rejects(`raw/${side}.json`, `d["cases"]["screen_identical"]["${group}"].pop()`));
    test(`${side} rejects a forged ${group} result hash`, () => rejects(`raw/${side}.json`, `d["cases"]["screen_identical"]["${group}"][-1]["result_sha256"] = "0" * 64`));
  }
  test(`${side} binds the entire summary`, () => rejects('results.json', `next(r for r in d["comparisons"] if r["case_id"] == "motion_reversed")["${side}"]["summary"]["timing_diagnostics"] = {"status": "fabricated"}`));
  test(`${side} rejects missing assertions`, () => rejects('results.json', `d["assertions"]["${side}"] = d["assertions"]["${side}"][:1]`));
  test(`${side} rejects duplicate check IDs`, () => rejects('results.json', `d["assertions"]["${side}"][-1] = d["assertions"]["${side}"][0]`));
  test(`${side} recomputes boolean outcomes`, () => rejects('results.json', `d["assertions"]["${side}"][0]["passed"] = not d["assertions"]["${side}"][0]["passed"]`));
  test(`${side} recomputes observed outcomes`, () => rejects('results.json', `d["assertions"]["${side}"][0]["observed"] = "fabricated"`));
  test(`${side} rejects an unknown check ID`, () => rejects('results.json', `d["assertions"]["${side}"][-1]["id"] = "invented_passing_check"`));
  for (const group of ['warmups', 'trials']) {
    test(`${side} rejects a rehashed failed metric in a later ${group} sample`, () => rejects(`raw/${side}.json`, `import hashlib\nt = d["cases"]["screen_identical"]["${group}"][-1]\nt["result"]["subscores"]["color"]["status"] = "failed"\nt["result_sha256"] = hashlib.sha256((json.dumps(t["result"], indent=2, sort_keys=True, allow_nan=False) + "\\n").encode()).hexdigest()`));
  }
}

test('publication and rendering reject post-load changes', () => {
  reset();
  const evidence = loadEvidence(path.join(base, 'results.json'), base);
  evidence.data.assertions.current.splice(1);
  assert.deepEqual(publicationProblems(evidence.data, base, evidence.raw), ['Evidence changed or was not verified by loadEvidence.']);
  assert.throws(() => renderSection(evidence, base, false, []), /Evidence changed or was not verified/);
});

test('publication refuses mutated evidence before writing output', () => {
  reset();
  mutate('raw/current.json', 'd["cases"]["scope_all_ignored"]["result"]["overall"] = 987654.321');
  const output = path.join(temp, 'rejected.html');
  const child = spawnSync(process.execPath, [path.join(ROOT, 'scripts/render-reliability.mjs'), path.join(base, 'results.json'), '--evidence-base', base, '--preview', '--output', output], { encoding: 'utf8' });
  assert.equal(child.status, 1);
  assert.match(child.stderr, /result|trial|mismatch/i);
  assert.equal(fs.existsSync(output), false);
});

test('final publication refuses corrupted evidence before touching the site', () => {
  reset();
  mutate('results.json', 'd["assertions"]["current"] = d["assertions"]["current"][:1]');
  const site = path.join(ROOT, 'site/index.html');
  const before = fs.readFileSync(site);
  const child = spawnSync(process.execPath, [path.join(ROOT, 'scripts/render-reliability.mjs'), path.join(base, 'results.json'), '--evidence-base', base], { encoding: 'utf8' });
  assert.equal(child.status, 1);
  assert.match(child.stderr, /assertion|check/i);
  assert.deepEqual(fs.readFileSync(site), before);
});

test('report bytes must match the authoritative report, not merely exist', () => {
  reset();
  fs.writeFileSync(path.join(base, 'report.md'), 'fabricated987654.321\n');
  assert.throws(() => loadEvidence(path.join(base, 'results.json'), base), /Report bytes mismatch/);
  const output = path.join(temp, 'fabricated-report.html');
  assert.throws(() => main([path.join(base, 'results.json'), '--preview', '--output', output]), /Report bytes mismatch/);
  assert.equal(fs.existsSync(output), false);
  const site = fs.readFileSync(path.join(ROOT, 'site/index.html'));
  assert.throws(() => main([path.join(base, 'results.json')]), /Report bytes mismatch/);
  assert.deepEqual(fs.readFileSync(path.join(ROOT, 'site/index.html')), site);
  const child = spawnSync(python, [path.join(ROOT, 'scripts/reliability-benchmark.py'), '--verify-evidence', path.join(base, 'results.json')], { encoding: 'utf8' });
  assert.equal(child.status, 1);
  assert.match(JSON.parse(child.stdout).problems.join('\n'), /Report bytes differ/);
});

test('comparison median delta is recomputed from retained trials', () => {
  rejects('results.json', 'd["comparisons"][0]["current_minus_baseline_median_ms"] = 987654.321');
});

for (const relative of ['raw/current.json', 'report.md', 'fixtures/color-periodic-crop-0px.png']) {
  test(`post-load disk drift in ${relative} blocks rendering and staging`, () => {
    reset();
    const original = fs.readFileSync(path.join(base, relative));
    try {
      const evidence = loadEvidence(path.join(base, 'results.json'), base);
      fs.appendFileSync(path.join(base, relative), 'BROKEN AFTER LOAD');
      assert.deepEqual(publicationProblems(evidence.data, base, evidence.raw), [`Evidence changed on disk: ${relative}`]);
      assert.throws(() => renderSection(evidence, base, true, []), /Evidence changed on disk/);
      assert.throws(() => stageEvidence(evidence, temp), /Evidence changed on disk/);
      assert.equal(fs.readdirSync(temp).some(name => name.startsWith('.reliability-stage-')), false);
    } finally { fs.writeFileSync(path.join(base, relative), original); }
  });
}

test('valid staging preserves exact bytes and installs a complete renderable bundle', () => {
  reset();
  const evidence = loadEvidence(path.join(base, 'results.json'), base);
  // Public buffers must not be able to mutate the privately retained bytes.
  evidence.bytes.fill(0);
  const staged = stageEvidence(evidence, temp);
  const destination = path.join(temp, 'installed');
  try {
    assert.match(renderSection(staged, destination, true, []), /Candidate fixture color-periodic-crop-1px\.png, crop origin y=1/);
    assert.equal(installStagedEvidence(staged, destination), destination);
    assert.equal(fs.existsSync(staged.base), false);
    for (const relative of fs.readdirSync(base, { recursive: true })) {
      if (fs.statSync(path.join(base, relative)).isFile()) assert.deepEqual(fs.readFileSync(path.join(destination, relative)), fs.readFileSync(path.join(base, relative)));
    }
    const installed = loadEvidence(path.join(destination, 'results.json'), destination);
    assert.equal(installed.raw.current.cases.scope_all_ignored.result.overall, 100);
    assert.match(renderSection(installed, destination, true, []), /Legacy overall<\/dt><dd><code>100<\/code>/);
    const output = path.join(temp, 'installed-preview.html');
    main([path.join(destination, 'results.json'), '--preview', '--output', output]);
    assert.match(fs.readFileSync(output, 'utf8'), /<strong>Not for publication\.<\/strong>/);
    const repeated = stageEvidence(evidence, temp);
    try { assert.equal(installStagedEvidence(repeated, destination), destination); }
    finally { fs.rmSync(repeated.base, { recursive: true, force: true }); }
  } finally {
    fs.rmSync(staged.base, { recursive: true, force: true });
    fs.rmSync(destination, { recursive: true, force: true });
  }
});

test('source drift while staging is refused and leaves no staged bundle', () => {
  reset();
  const evidence = loadEvidence(path.join(base, 'results.json'), base);
  const write = fs.writeFileSync;
  let injected = false;
  fs.writeFileSync = (file, ...args) => {
    write(file, ...args);
    if (String(file).endsWith('/raw/current.json') && !injected) {
      injected = true;
      write(path.join(base, 'raw/current.json'), 'BROKEN AFTER LOAD', { flag: 'a' });
    }
  };
  try { assert.throws(() => stageEvidence(evidence, temp), /Evidence changed on disk: raw\/current.json/); }
  finally { fs.writeFileSync = write; reset(); }
  assert.equal(injected, true);
  assert.equal(fs.readdirSync(temp).some(name => name.startsWith('.reliability-stage-')), false);
});

test('staging corruption during writing is rejected before exposure', () => {
  reset();
  const evidence = loadEvidence(path.join(base, 'results.json'), base);
  const write = fs.writeFileSync;
  fs.writeFileSync = (file, ...args) => {
    write(file, ...args);
    if (String(file).endsWith('/raw/current.json')) write(file, 'BROKEN DURING STAGING', { flag: 'a' });
  };
  try { assert.throws(() => stageEvidence(evidence, temp), /Evidence changed on disk: raw\/current.json/); }
  finally { fs.writeFileSync = write; }
  assert.equal(fs.readdirSync(temp).some(name => name.startsWith('.reliability-stage-')), false);
});

test('post-staging corruption cannot replace existing assets or expose a new bundle', () => {
  reset();
  const staged = stageEvidence(loadEvidence(path.join(base, 'results.json'), base), temp);
  const existing = path.join(temp, 'existing-assets');
  const fresh = path.join(temp, 'never-exposed');
  fs.mkdirSync(existing);
  fs.writeFileSync(path.join(existing, 'sentinel'), 'previous assets');
  try {
    fs.appendFileSync(path.join(staged.base, 'raw/current.json'), 'BROKEN AFTER STAGING');
    assert.throws(() => installStagedEvidence(staged, existing), /Evidence changed on disk/);
    assert.throws(() => installStagedEvidence(staged, fresh), /Evidence changed on disk/);
    assert.equal(fs.readFileSync(path.join(existing, 'sentinel'), 'utf8'), 'previous assets');
    assert.deepEqual(fs.readdirSync(existing), ['sentinel']);
    assert.equal(fs.existsSync(fresh), false);
  } finally { fs.rmSync(staged.base, { recursive: true, force: true }); }
});

test('valid staged bytes never overwrite an existing partial bundle', () => {
  reset();
  const staged = stageEvidence(loadEvidence(path.join(base, 'results.json'), base), temp);
  const destination = path.join(temp, 'partial-bundle');
  fs.mkdirSync(destination);
  fs.writeFileSync(path.join(destination, 'results.json'), 'previous partial bytes');
  try {
    assert.throws(() => installStagedEvidence(staged, destination), /Evidence changed on disk: bundle file set/);
    assert.equal(fs.readFileSync(path.join(destination, 'results.json'), 'utf8'), 'previous partial bytes');
    assert.deepEqual(fs.readdirSync(destination), ['results.json']);
  } finally { fs.rmSync(staged.base, { recursive: true, force: true }); }
});

test('report roundtrip uses original Python floats for the allowed legacy preview', () => {
  const legacy = path.join(temp, 'legacy-report');
  fs.cpSync(fixture, legacy, { recursive: true });
  // Project retained measurements onto the legacy schema, not an archived run.
  execFileSync(python, ['-c', String.raw`
import json, pathlib, runpy, sys, tempfile
root, base = map(pathlib.Path, sys.argv[1:])
n = runpy.run_path(str(root / "scripts/reliability-benchmark.py"))
data = json.loads((base / "results.json").read_bytes())
data["run"].update(generator="calendar-motion-and-color-controls-v3; temporary legacy-preview regression",
                     phase="initial", qualification="Test-only v3 projection of retained measurements. Not final evidence.")
with tempfile.TemporaryDirectory(prefix="dcm-legacy-schema-") as generated:
    canonical, _ = n["generate_fixtures"](pathlib.Path(generated))
cases = n["canonical_cases_for_generator"](canonical, data["run"]["generator"])
supplied = {c["id"]: c for c in data["cases"]}
assert all(supplied[c["id"]] == c for c in cases), "Legacy cases must come unchanged from the supplied dataset"
names = {c["id"] for c in cases}
paths = {"fixtures/examples.png", "fixtures/color-controls-examples.png"}
for case in cases:
    for field in ("reference", "candidate"):
        value = case[field]
        paths.update([value] if isinstance(value, str) else value)
fixtures = {name: value for name, value in data["fixtures"].items() if name in paths}
assert paths == set(fixtures), "Legacy fixture pixels must all come from the supplied dataset"
data.update(cases=cases, fixtures=fixtures,
            comparisons=[row for row in data["comparisons"] if row["case_id"] in names])
raw = {}
for side in ("baseline", "current"):
    raw[side] = json.loads((base / f"raw/{side}.json").read_bytes())
    raw[side]["cases"] = {c["id"]: raw[side]["cases"][c["id"]] for c in cases}
    data["assertions"][side] = n["assertions_for_generator"](raw[side]["cases"], data["run"]["generator"])
    n["write_json"](base / f"raw/{side}.json", raw[side])
    invocation = json.loads((base / f"raw/{side}-invocation.json").read_bytes())
    invocation["request"]["cases"] = cases
    n["write_json"](base / f"raw/{side}-invocation.json", invocation)
n["write_json"](base / "raw/inputs.json", {"cases": cases, "fixtures": fixtures})
original_report = n["report"](data).encode("utf-8")
n["write_json"](base / "results.json", data)
assert original_report == n["report"](json.loads((base / "results.json").read_bytes())).encode("utf-8")
(base / "report.md").write_bytes(original_report)
verification = n["verify_evidence"](data, raw)
assert not verification["problems"], verification["problems"]
assert verification["report_sha256"] == n["sha"](original_report)
`, ROOT, legacy], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024, timeout: 30_000 });
  const child = spawnSync(python, [path.join(ROOT, 'scripts/reliability-benchmark.py'), '--verify-evidence', path.join(legacy, 'results.json'), '--evidence-base', legacy], { encoding: 'utf8' });
  assert.equal(child.status, 0, child.stderr || child.stdout);
  const response = JSON.parse(child.stdout);
  assert.equal(response.report_sha256, createHash('sha256').update(fs.readFileSync(path.join(legacy, 'report.md'))).digest('hex'));
  assert.deepEqual(response.problems, []);
  assert.match(response.publication_problems.join('\n'), /Legacy v3 evidence/);
  const evidence = loadEvidence(path.join(legacy, 'results.json'), legacy);
  assert.match(evidence.data.run.generator, /^calendar-motion-and-color-controls-v3;/);
  assert.equal(evidence.data.run.phase, 'initial');
  assert.match(publicationProblems(evidence.data, legacy, evidence.raw).join('\n'), /Legacy v3 evidence/);
  assert.match(renderSection(evidence, legacy, true, []), /Legacy overall<\/dt><dd><code>100<\/code>/);
  const output = path.join(temp, 'legacy-schema-preview.html');
  main([path.join(legacy, 'results.json'), '--preview', '--output', output]);
  assert.match(fs.readFileSync(output, 'utf8'), /<strong>Not for publication\.<\/strong>/);
  assert.match(fs.readFileSync(output, 'utf8'), /Legacy v3 evidence/);
});

test('current schema report roundtrips and previews initial mixed measurements, not final evidence', () => {
  // Extend a temporary copy with real calls for any missing current-schema cases.
  // This mixed historical/test run is explicitly initial, never final evidence.
  const current = path.join(temp, 'current-schema');
  fs.cpSync(fixture, current, { recursive: true });
  const expected = JSON.parse(execFileSync(python, ['-c', String.raw`
import io, json, os, pathlib, runpy, subprocess, sys, tarfile, tempfile, zipfile
root, base = map(pathlib.Path, sys.argv[1:])
script = root / "scripts/reliability-benchmark.py"
n = runpy.run_path(str(script))
data = json.loads((base / "results.json").read_bytes())
cases, fixtures = n["generate_fixtures"](base)
old_ids = {c["id"] for c in data["cases"]}
extra = [c for c in cases if c["id"] not in old_ids]
raw = {}
with tempfile.TemporaryDirectory(prefix="dcm-current-schema-sources-") as temp:
    for side in ("baseline", "current"):
        source = pathlib.Path(temp) / side
        source.mkdir()
        if side == "baseline":
            archive = subprocess.check_output(["git", "-C", str(root), "archive", data["run"]["baseline_commit"], "worker"])
            with tarfile.open(fileobj=io.BytesIO(archive)) as archive:
                archive.extractall(source, filter="data")
        else:
            with zipfile.ZipFile(base / "raw/current-source.zip") as archive:
                for file in data["implementations"][side]["source"]["files"]:
                    target = source / file
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(file))
        invocation = json.loads((base / f"raw/{side}-invocation.json").read_bytes())
        request = {**invocation["request"], "source": str(source), "inputs": str(base), "cases": extra}
        if extra:
            child = subprocess.run([sys.executable, "-I", str(script), "--internal-runner"],
                                   input=json.dumps(request), text=True, capture_output=True, check=True,
                                   env={**os.environ, **n["THREAD_ENV"]}, timeout=60)
            added = json.loads(child.stdout)
            assert added["environment"]["source_manifest"] == data["implementations"][side]["source"]
        raw[side] = json.loads((base / f"raw/{side}.json").read_bytes())
        raw[side]["cases"].update(added["cases"] if extra else {})
        raw[side]["cases"] = {c["id"]: raw[side]["cases"][c["id"]] for c in cases}
        n["write_json"](base / f"raw/{side}.json", raw[side])
        invocation["request"]["cases"] = cases
        n["write_json"](base / f"raw/{side}-invocation.json", invocation)
data["run"].update(generator=n["GENERATOR"],
                     phase="initial", qualification="Test-only initial fixture of retained and new measurements. Not final evidence.",
                     harness_sha256=n["sha"](script.read_bytes()))
(base / "raw/benchmark.py").write_bytes(script.read_bytes())
data.update(cases=cases, fixtures=fixtures, comparisons=[], assertions={})
for case in cases:
    row = {"case_id": case["id"], "kind": case["kind"], "description": case["description"]}
    for side in ("baseline", "current"):
        measured = raw[side]["cases"][case["id"]]
        row[side] = {key: measured[key] for key in ("status", "latency", "stable_results", "unsupported_metadata_params", "effective_params")}
        row[side]["summary"] = n["summarize"](measured["result"] or {})
    b, c = (row[side]["latency"]["median"] for side in ("baseline", "current"))
    row["current_minus_baseline_median_ms"] = c - b if b is not None and c is not None else None
    data["comparisons"].append(row)
data["assertions"] = {side: n["assertions_for_generator"](raw[side]["cases"], data["run"]["generator"])
                      for side in ("baseline", "current")}
n["write_json"](base / "raw/inputs.json", {"cases": cases, "fixtures": fixtures})
original_report = n["report"](data).encode("utf-8")
n["write_json"](base / "results.json", data)
assert original_report == n["report"](json.loads((base / "results.json").read_bytes())).encode("utf-8")
(base / "report.md").write_bytes(original_report)
print(json.dumps({"case_ids": [c["id"] for c in cases],
                  "generator": n["GENERATOR"],
                  "assertion_ids": {side: [c["id"] for c in n["assertions_for_generator"](raw[side]["cases"], n["GENERATOR"])]
                                    for side in ("baseline", "current")}}))
`, ROOT, current], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024, timeout: 150_000 }));
  const child = spawnSync(python, [path.join(ROOT, 'scripts/reliability-benchmark.py'), '--verify-evidence', path.join(current, 'results.json')], { encoding: 'utf8' });
  assert.equal(child.status, 0, child.stderr || child.stdout);
  const response = JSON.parse(child.stdout);
  assert.equal(response.report_sha256, createHash('sha256').update(fs.readFileSync(path.join(current, 'report.md'))).digest('hex'));
  assert.deepEqual(response.problems, []);
  assert.equal(response.publication_problems.some(problem => /Legacy v\d evidence/.test(problem)), false);
  for (const side of ['baseline', 'current']) {
    assert.deepEqual(response.expected_assertion_ids[side], expected.assertion_ids[side]);
    assert.deepEqual(response.assertions[side].map(check => check.id), expected.assertion_ids[side]);
  }
  assert.ok(response.publication_problems.includes('Publication requires an integrated run.'));
  const evidence = loadEvidence(path.join(current, 'results.json'), current);
  assert.deepEqual(evidence.data.cases.map(c => c.id), expected.case_ids);
  assert.equal(evidence.data.run.generator, expected.generator);
  assert.equal(evidence.data.run.phase, 'initial');
  assert.match(publicationProblems(evidence.data, current, evidence.raw).join('\n'), /phase is initial, not integrated/);
  assert.equal(evidence.raw.current.cases.scope_all_ignored.result.overall, 100);
  const output = path.join(temp, 'current-schema-preview.html');
  main([path.join(current, 'results.json'), '--preview', '--output', output]);
  assert.match(fs.readFileSync(output, 'utf8'), /<strong>Not for publication\.<\/strong>/);
  assert.match(fs.readFileSync(output, 'utf8'), /Test-only initial fixture of retained and new measurements\. Not final evidence\./);
});
