import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { CompareInput } from "../dist/schema.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fixture = (name) => path.join(ROOT, "test", "fixtures", name);
const context = { scopeId: "reviewed-card-v1", protocolKey: "a".repeat(64) };
const transport = new StdioClientTransport({
  command: process.execPath,
  args: [path.join(ROOT, "dist", "index.js")],
  cwd: ROOT,
  stderr: "inherit",
});
const client = new Client({ name: "reliability-smoke", version: "1" });
const base = {
  reference: fixture("reference.png"), candidate: fixture("identical.png"),
  mode: "widget", returnVisuals: false,
  ignoreRegions: [[0, 0, 20, 20], [10, 10, 20, 20]],
  comparisonContext: context,
};

async function call(overrides = {}, omit = []) {
  const args = { ...base, ...overrides };
  for (const key of omit) delete args[key];
  const response = await client.callTool({ name: "compare_designs", arguments: args });
  assert.ok(!response.isError, JSON.stringify(response));
  const output = JSON.parse(response.content.find((block) => block.type === "text").text);
  assert.deepEqual(Object.keys(output).slice(0, 3), ["overall", "diagnostics", "provenance"]);
  assert.equal(output.diagnostics.version, 1);
  assert.equal(output.provenance.version, 1);
  assert.match(output.provenance.comparison_key, /^[0-9a-f]{64}$/);
  assert.match(output.provenance.run_key, /^[0-9a-f]{64}$/);
  assert.match(output.provenance.settings.engine_revision, /^sha256:[0-9a-f]{64}$/);
  assert.ok(output.provenance.settings.runtime_versions.python);
  assert.ok(Object.values(output.subscores).every((sub) => typeof sub.status === "string"));
  return output;
}

try {
  await client.connect(transport);
  const tools = await client.listTools();
  const tool = tools.tools.find((entry) => entry.name === "compare_designs");
  assert.ok(tool.inputSchema.properties.comparisonContext, "MCP exposes context input");
  const first = await call();
  assert.deepEqual(first.provenance.settings.comparison_context, context);
  assert.equal(first.alignment.outcome, "not_requested");
  assert.equal(first.alignment.reason, "widget_identity");
  assert.ok(first.diagnostics.issues.some((issue) => issue.code === "mask_fill_semantics"));
  assert.ok(first.diagnostics.scope.ignored_fraction > 0);
  assert.equal(first.diagnostics.layout_identity_score, 100);
  assert.deepEqual(first.visuals, []);

  const repeated = await call();
  assert.deepEqual(first.provenance, repeated.provenance);
  assert.deepEqual(first.diagnostics, repeated.diagnostics);
  const candidate = await call({ candidate: fixture("recolored.png") });
  assert.equal(first.provenance.comparison_key, candidate.provenance.comparison_key);
  assert.notEqual(first.provenance.run_key, candidate.provenance.run_key);

  const reordered = await call({
    ignoreRegions: [[10, 10, 20, 20], [-0, 0, 20, 20], [0, 0, 20, 20]],
    comparisonContext: { protocolKey: context.protocolKey, scopeId: context.scopeId },
  });
  assert.deepEqual(first.provenance, reordered.provenance);
  assert.deepEqual(first.diagnostics, reordered.diagnostics);
  assert.deepEqual(first.subscores, reordered.subscores);
  assert.equal(first.overall, reordered.overall);
  const visuals = await call({ returnVisuals: true });
  assert.deepEqual(first.provenance, visuals.provenance);
  assert.deepEqual(first.diagnostics, visuals.diagnostics);

  for (const override of [
    { reference: fixture("recolored.png") },
    { ignoreRegions: [[0, 0, 21, 20]] },
    { mode: "screen" },
    { preset: "dark-ui" },
    { comparisonContext: { ...context, protocolKey: "b".repeat(64) } },
    { comparisonContext: { ...context, scopeId: "another-reviewed-scope" } },
  ]) {
    const changed = await call(override);
    assert.notEqual(first.provenance.comparison_key, changed.provenance.comparison_key);
    assert.notEqual(first.provenance.run_key, changed.provenance.run_key);
  }
  const preciseA = await call({ weights: { layout: 0.3500000001 } });
  const preciseB = await call({ weights: { layout: 0.3500000002 } });
  assert.deepEqual(preciseA.weights, preciseB.weights, "presentation weights deliberately round");
  assert.notEqual(preciseA.provenance.comparison_key, preciseB.provenance.comparison_key);
  const legacy = await call({}, ["comparisonContext", "ignoreRegions", "mode"]);
  const explicit = await call({ mode: "screen", preset: "default", ignoreRegions: [] }, ["comparisonContext"]);
  assert.equal(legacy.provenance.settings.comparison_context, null);
  assert.deepEqual(legacy.provenance, explicit.provenance);
  assert.match(legacy.critique_rubric, /never verified capture proof/);

  const fullMask = await call({ ignoreRegions: [[0, 0, 100000, 100000]] });
  assert.equal(fullMask.diagnostics.status, "inconclusive");
  assert.equal(fullMask.diagnostics.scope.compared_fraction, 0);
  assert.equal(typeof fullMask.overall, "number", "legacy aggregate is retained");
  assert.ok(fullMask.diagnostics.issues.some((issue) => issue.code === "empty_compare_scope"));

  for (const bad of [
    null, {}, { ...context, extra: true }, { ...context, scopeId: "" },
    { ...context, scopeId: "x".repeat(129) }, { ...context, scopeId: "😀".repeat(65) },
    ...["\ud800", "\udc00", "a\ud800b", "\ud800\ud800", "\udc00\ud800", "😀\ud800", "\ud800😀"]
      .map(scopeId => ({ ...context, scopeId })),
    { ...context, protocolKey: "A".repeat(64) },
    { ...context, protocolKey: "a".repeat(63) },
    { ...context, protocolKey: "a".repeat(64) + "\n" },
  ]) {
    assert.equal(CompareInput.safeParse({ ...base, comparisonContext: bad }).success, false);
    const response = await client.callTool({ name: "compare_designs", arguments: { ...base, comparisonContext: bad } });
    assert.equal(response.isError, true, "MCP rejects malformed context");
    const errorText = response.content.filter(block => block.type === "text").map(block => block.text).join("\n");
    assert.match(errorText, /Input validation error/, "invalid contexts fail at the MCP boundary");
    assert.doesNotMatch(errorText, /UnicodeEncodeError|Worker error/);
  }
  const astral = await call({ comparisonContext: { ...context, scopeId: "😀".repeat(64) } });
  const paired = await call({ comparisonContext: { ...context, scopeId: "\ud83d\ude00".repeat(64) } });
  assert.equal(astral.provenance.settings.comparison_context.scopeId, "😀".repeat(64));
  assert.deepEqual(astral, paired, "valid surrogate pairs and emoji have identical accepted semantics");
  for (const scopeId of ["x".repeat(128), "x".repeat(126) + "😀"]) {
    assert.equal(CompareInput.safeParse({ ...base, comparisonContext: { ...context, scopeId } }).success, true);
    const output = await call({ comparisonContext: { ...context, scopeId } });
    assert.equal(output.provenance.settings.comparison_context.scopeId, scopeId);
  }
  console.log("Reliability MCP smoke passed: diagnostics, context, exact keys and settings survive transport.");
} finally {
  await client.close();
  await transport.close();
}
