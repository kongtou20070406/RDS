import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { fileURLToPath } from "node:url";
import { setImmediate as tick } from "node:timers/promises";
import { createHelperRunner, createRdsStatusExtension } from "../integrations/omp/rds-status.mjs";

const running = "RDS | advise: running";
const done = "RDS | advise: returned";
function deferred() { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; }
function harness(runHelper, install = createRdsStatusExtension({ runHelper })) {
  const handlers = new Map(), statuses = [];
  const ctx = { cwd: "/project", hasUI: true, ui: { setStatus: (key, text) => { assert.equal(key, "rds"); statuses.push(text); } } };
  install({ on: (name, callback) => handlers.set(name, callback) });
  return { ctx, statuses, emit: (name, event = {}, context = ctx) => handlers.get(name)(event, context),
    current: () => statuses.at(-1) };
}
const start = (id = "a", extra = {}) => ({ toolCallId: id, toolName: "bash", args: { command: "python scripts/rds_cli.py advise" }, ...extra });
const end = (id = "a", extra = {}) => ({ toolCallId: id, toolName: "bash", result: { details: { exitCode: 0 } }, isError: false, ...extra });
const normalHelper = async (payload) => ({ status: payload.hook_event_name === "PreToolUse" ? running
  : payload.tool_response.isError ? "RDS | advise: error" : done });

test("only recognized exact helper calls produce a footer; unrelated tools never spawn", async () => {
  const payloads = []; const h = harness(async (payload) => { payloads.push(payload); return undefined; });
  await h.emit("tool_execution_start", start("a", { toolName: "read" }));
  await h.emit("tool_execution_start", start("b", { args: { command: "echo hello" } }));
  assert.equal(payloads.length, 0);
  await h.emit("tool_execution_start", start("c", { args: { command: "echo rds_cli.py" } }));
  assert.equal(payloads.length, 1);
  assert.equal(h.current(), undefined);
  await h.emit("tool_execution_end", end("c"));
  assert.equal(payloads.length, 1);
});

test("normalizes cwd and only structured result metadata, never content or error text", async () => {
  const payloads = []; const h = harness(async (payload) => { payloads.push(payload); return normalHelper(payload); });
  await h.emit("tool_execution_start", start("a", { args: { command: "python scripts/rds_cli.py advise", cwd: "/scope", secret: "private" } }));
  assert.equal(h.current(), running);
  await h.emit("tool_execution_end", end("a", { result: { content: [{ text: "private logs exitCode: 0" }],
    details: { exitCode: 3, interrupted: true, error: "private failure" } }, isError: true }));
  assert.equal(h.current(), "RDS | advise: error");
  assert.deepEqual(payloads[0], { cwd: "/scope", tool_name: "Bash", tool_use_id: "a",
    tool_input: { command: "python scripts/rds_cli.py advise", cwd: "/scope" }, hook_event_name: "PreToolUse" });
  assert.deepEqual(payloads[1].tool_response, { exitCode: 3, interrupted: true, error: "tool error", isError: true });
  assert.ok(!JSON.stringify(payloads).includes("private"));
});

test("concurrent calls finish independently and never overwrite a still-running call", async () => {
  const h = harness(normalHelper);
  await h.emit("tool_execution_start", start("a"));
  await h.emit("tool_execution_start", start("b"));
  assert.equal(h.current(), running + " (2 active)");
  await h.emit("tool_execution_end", end("b", { isError: true }));
  assert.equal(h.current(), running);
  await h.emit("tool_execution_end", end("a"));
  assert.equal(h.current(), done);
  await h.emit("agent_end");
  assert.equal(h.current(), undefined);
});

test("end before recognition cannot flash a stale running status", async () => {
  const pre = deferred(); const h = harness((payload) => payload.hook_event_name === "PreToolUse" ? pre.promise : normalHelper(payload));
  const pending = h.emit("tool_execution_start", start());
  const ending = h.emit("tool_execution_end", end());
  pre.resolve({ status: running });
  await Promise.all([pending, ending]);
  assert.equal(h.current(), done);
  assert.ok(!h.statuses.includes(running));
});

for (const name of ["session_start", "session_switch", "session_shutdown", "agent_end"]) {
  test(`${name} clears state and rejects late pre/post callbacks`, async () => {
    const pre = deferred(), post = deferred(); let phase = "pre";
    const h = harness(() => phase === "pre" ? pre.promise : post.promise);
    const pending = h.emit("tool_execution_start", start());
    await h.emit(name);
    pre.resolve({ status: running }); await pending;
    assert.equal(h.current(), undefined);
    phase = "post"; // New call recognizes immediately; its post callback is delayed.
    const h2 = harness((p) => p.hook_event_name === "PreToolUse" ? { status: running } : post.promise);
    await h2.emit("tool_execution_start", start());
    const ending = h2.emit("tool_execution_end", end());
    await tick(); // The post helper must already be in flight when the session ends.
    await h2.emit(name); post.resolve({ status: done }); await ending;
    assert.equal(h2.current(), undefined);
  });
}

test("factory invocations isolate sub-session state and headless mode stays silent", async () => {
  const install = createRdsStatusExtension({ runHelper: normalHelper });
  const a = harness(undefined, install), b = harness(undefined, install);
  await a.emit("tool_execution_start", start());
  await b.emit("tool_execution_end", end());
  await b.emit("session_switch");
  assert.equal(a.current(), running);
  assert.equal(b.current(), undefined);
  const headless = harness(undefined, install); headless.ctx.hasUI = false;
  await headless.emit("tool_execution_start", start());
  await headless.emit("tool_execution_end", end());
  await headless.emit("agent_end");
  assert.equal(headless.statuses.length, 0);
});

test("helper failures and UI exceptions never reject original tool events", async () => {
  let count = 0;
  const h = harness(async () => { if (++count === 1) return { status: running }; throw new Error("missing python"); });
  await h.emit("tool_execution_start", start());
  await h.emit("tool_execution_end", end());
  assert.equal(h.current(), undefined);
  await h.emit("tool_execution_start", start("b"));
  await h.emit("agent_end", {}, { ...h.ctx, ui: { setStatus() { throw new Error("closed UI"); } } });
});

test("older end helper cannot overwrite a newer completion", async () => {
  const delayed = deferred();
  const h = harness((p) => p.hook_event_name === "PostToolUse" && p.tool_use_id === "a" ? delayed.promise : normalHelper(p));
  await h.emit("tool_execution_start", start("a")); await h.emit("tool_execution_start", start("b"));
  const old = h.emit("tool_execution_end", end("a"));
  await h.emit("tool_execution_end", end("b", { isError: true }));
  delayed.resolve({ status: done }); await old;
  assert.equal(h.current(), "RDS | advise: error");
});

function fakeProcess() {
  const child = new EventEmitter(); child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
  child.killed = false; child.kill = () => { child.killed = true; }; return child;
}
test("subprocess uses UTF-8, bounded output, timeout and no shell", async () => {
  let args; let child = fakeProcess();
  const run = createHelperRunner({ helperPath: "/plugin helper.py", python: "/custom python", timeoutMs: 10,
    spawnProcess: (...values) => { args = values; return child; } });
  let pending = run({ example: "中文" });
  child.stdout.write(JSON.stringify({ status: done })); child.emit("close", 0);
  assert.deepEqual(await pending, { status: done });
  assert.equal(args[0], "/custom python"); assert.deepEqual(args[1], ["-B", "/plugin helper.py", "--host", "omp"]);
  assert.equal(args[2].shell, false); assert.equal(args[2].windowsHide, true); assert.equal(args[2].env.PYTHONIOENCODING, "utf-8");
  child = fakeProcess(); pending = run({}); child.stdout.write("x".repeat(16 * 1024 + 1));
  assert.equal(await pending, undefined); assert.equal(child.killed, true);
  child = fakeProcess(); assert.equal(await run({}), undefined); assert.equal(child.killed, true);
});

test("malformed/nonzero helper output is ignored and input is bounded", async () => {
  const children = [];
  const run = createHelperRunner({ spawnProcess: () => { const child = fakeProcess(); children.push(child); return child; } });
  for (const [body, code] of [["not json", 0], [JSON.stringify({ status: done }), 1], [JSON.stringify({ status: "RDS | bad\nline" }), 0]]) {
    const pending = run({}); const child = children.at(-1); child.stdout.write(body); child.emit("close", code);
    assert.equal(await pending, undefined);
  }
  assert.equal(await run({ large: "x".repeat(65536) }), undefined); assert.equal(children.length, 3);
});

test("real shared helper recognizes its CLI and never infers success from stdout", async () => {
  const helperPath = fileURLToPath(new URL("../scripts/rds_conversation_hook.py", import.meta.url));
  const cli = fileURLToPath(new URL("../scripts/rds_cli.py", import.meta.url));
  const cwd = fileURLToPath(new URL("../", import.meta.url));
  const h = harness(createHelperRunner({ helperPath, timeoutMs: 2000 }));
  h.ctx.cwd = cwd;
  await h.emit("tool_execution_start", start("real", { args: { command: `python -B "${cli}" status` } }));
  assert.equal(h.current(), "RDS | status: running");
  await h.emit("tool_execution_end", end("real", { result: { content: [{ text: "exitCode: 0 PASS" }] } }));
  assert.equal(h.current(), "RDS | status: result unknown");
});

test("relative bash cwd resolves against the session for actual CLI recognition", async () => {
  const helperPath = fileURLToPath(new URL("../scripts/rds_conversation_hook.py", import.meta.url));
  const cwd = fileURLToPath(new URL("../", import.meta.url));
  const h = harness(createHelperRunner({ helperPath, timeoutMs: 2000 }));
  h.ctx.cwd = cwd;
  for (const [directory, command] of [[".", "python -B scripts/rds_cli.py status"],
    ["scripts", "python -B rds_cli.py status"]]) {
    await h.emit("tool_execution_start", start(directory, { args: { cwd: directory, command } }));
    assert.equal(h.current(), "RDS | status: running");
    await h.emit("tool_execution_end", end(directory));
    assert.equal(h.current(), "RDS | status: returned");
  }
});
