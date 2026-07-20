// End-to-end smoke test: launches the built MCP server over stdio using the
// official MCP client, then exercises the tools. Proves the full
// host -> TS -> Python worker -> TS -> host path.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");

const transport = new StdioClientTransport({
  command: process.execPath, // node
  args: [path.join(ROOT, "dist", "index.js")],
  cwd: ROOT,
  stderr: "inherit",
});

const client = new Client({ name: "smoke", version: "0.0.1" });

function assert(cond, msg) {
  if (!cond) throw new Error("ASSERT FAILED: " + msg);
}

try {
  await client.connect(transport);
  console.log("connected.");

  const tools = await client.listTools();
  const names = tools.tools.map((t) => t.name).sort();
  console.log("tools:", names.join(", "));
  assert(names.includes("ping"), "ping tool registered");
  assert(names.includes("compare_designs"), "compare_designs tool registered");
  assert(names.includes("compare_motion"), "compare_motion tool registered");

  const ping = await client.callTool({
    name: "ping",
    arguments: { message: "round-trip" },
  });
  const pingText = ping.content?.[0]?.text ?? "";
  console.log("ping ->", pingText.replace(/\s+/g, " ").slice(0, 200));
  const pingObj = JSON.parse(pingText);
  assert(pingObj.pong === true, "worker replied pong");
  assert(pingObj.echo?.message === "round-trip", "worker echoed our message");

  const refPath = path.join(ROOT, "test", "fixtures", "reference.png");
  const candPath = path.join(ROOT, "test", "fixtures", "identical.png");
  const cmp = await client.callTool({
    name: "compare_designs",
    arguments: { reference: refPath, candidate: candPath, mode: "screen" },
  });
  const textBlock = cmp.content.find((c) => c.type === "text");
  const imageBlocks = cmp.content.filter((c) => c.type === "image");
  const cmpObj = JSON.parse(textBlock.text);
  console.log(
    "compare_designs ->",
    JSON.stringify({
      overall: cmpObj.overall,
      layout: cmpObj.subscores.layout.score,
      alignmentMode: cmpObj.alignment?.mode,
      images: imageBlocks.length,
      stub: cmpObj.stub,
    }),
  );
  assert(cmpObj.stub === false, "compare_designs returned a real (non-stub) result");
  assert(typeof cmpObj.overall === "number", "overall is numeric");
  assert(cmpObj.overall >= 90, "identical images score high");
  assert(cmpObj.alignment?.mode === "screen", "mode threaded through to worker");
  assert(
    Object.keys(cmpObj.subscores).length === 5,
    "five sub-score dimensions present",
  );
  assert(imageBlocks.length === 4, "returns four diagnostic images");
  assert(
    imageBlocks.every((b) => typeof b.data === "string" && b.mimeType === "image/png"),
    "image blocks are PNG data",
  );
  assert(cmpObj.subscores.color.score !== null, "color dimension is scored");
  assert(cmpObj.subscores.content.score !== null, "content dimension is scored");

  // Recolor path: color should drop while layout stays high (grayscale-blind SSIM).
  const recolor = await client.callTool({
    name: "compare_designs",
    arguments: {
      reference: refPath,
      candidate: path.join(ROOT, "test", "fixtures", "recolored.png"),
      mode: "screen",
    },
  });
  const rObj = JSON.parse(recolor.content.find((c) => c.type === "text").text);
  console.log(
    "recolored ->",
    JSON.stringify({
      overall: rObj.overall,
      layout: rObj.subscores.layout.score,
      color: rObj.subscores.color.score,
    }),
  );
  assert(rObj.subscores.color.score < rObj.subscores.layout.score - 20, "color caught the recolor");

  // compare_motion over the full MCP path: feed fixture images as a frame sequence.
  const fx = (n) => path.join(ROOT, "test", "fixtures", n);
  const seq = [fx("reference.png"), fx("shifted.png"), fx("different.png")];
  const motion = await client.callTool({
    name: "compare_motion",
    arguments: { reference: seq, candidate: seq },
  });
  const mText = motion.content.find((c) => c.type === "text");
  const mImages = motion.content.filter((c) => c.type === "image");
  const mObj = JSON.parse(mText.text);
  console.log("compare_motion ->", JSON.stringify({ motion_score: mObj.motion_score, images: mImages.length }));
  assert(typeof mObj.motion_score === "number", "motion_score is numeric");
  assert(mObj.motion_score === 100, "identical sequences -> motion 100");
  assert(mImages.length === 1, "returns a motion-signature chart");

  console.log("\nALL CHECKS PASSED ✅");
  await client.close();
  process.exit(0);
} catch (err) {
  console.error("\nSMOKE TEST FAILED ❌\n", err);
  await client.close().catch(() => {});
  process.exit(1);
}
