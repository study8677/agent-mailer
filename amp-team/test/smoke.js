#!/usr/bin/env node
"use strict";

// Smoke test: exercise the deterministic, network-free pieces, plus the init
// flow under a stubbed broker. This proves filesystem layout + secret-file
// permissions + start-script generation without needing real user creds.

const fs = require("fs");
const os = require("os");
const path = require("path");
const assert = require("assert/strict");

const { slugifyTeam, isValidTeamSlug } = require("../src/slug");
const { isEmptyDir } = require("../src/empty-dir");
const { writeStartScripts, FRAMEWORK_CMD } = require("../src/scripts");

let failed = 0;

async function test(name, fn) {
  try {
    await fn();
    process.stdout.write(`✓ ${name}\n`);
  } catch (e) {
    failed += 1;
    process.stderr.write(`✖ ${name}\n  ${(e && e.stack) || e}\n`);
  }
}

async function main() {
  // ---- slug ----

  await test("slugifyTeam normalizes spaces and uppercase", () => {
    assert.equal(slugifyTeam("My Team"), "my-team");
    assert.equal(slugifyTeam("Foo_Bar.42"), "foo_bar.42");
    assert.equal(slugifyTeam("   leading---and-trailing!!!  "), "leading-and-trailing");
  });

  await test("slugifyTeam drops leading/trailing non-alnum", () => {
    assert.equal(slugifyTeam("-myteam-"), "myteam");
    assert.equal(slugifyTeam(".."), "");
  });

  await test("isValidTeamSlug accepts broker-acceptable shapes", () => {
    assert.equal(isValidTeamSlug("myteam"), true);
    assert.equal(isValidTeamSlug("a"), true);
    assert.equal(isValidTeamSlug("my-team_42.alpha"), true);
  });

  await test("isValidTeamSlug rejects edge violations", () => {
    assert.equal(isValidTeamSlug(""), false);
    assert.equal(isValidTeamSlug("-myteam"), false);
    assert.equal(isValidTeamSlug("myteam-"), false);
    assert.equal(isValidTeamSlug("MyTeam"), false);
  });

  // ---- empty-dir ----

  await test("isEmptyDir tolerates allowed-noise entries", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "amp-team-test-empty-"));
    try {
      fs.writeFileSync(path.join(dir, ".DS_Store"), "");
      fs.mkdirSync(path.join(dir, ".git"));
      const r = isEmptyDir(dir);
      assert.equal(r.ok, true, `unexpectedly rejected: ${r.reason}`);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  await test("isEmptyDir rejects node_modules and project artifacts", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "amp-team-test-nonempty-"));
    try {
      fs.mkdirSync(path.join(dir, "node_modules"));
      const r = isEmptyDir(dir);
      assert.equal(r.ok, false);
      assert.ok(r.reason.includes("node_modules"));
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  await test("isEmptyDir rejects user files like README.md", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "amp-team-test-userfile-"));
    try {
      fs.writeFileSync(path.join(dir, "README.md"), "");
      const r = isEmptyDir(dir);
      assert.equal(r.ok, false);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  // ---- scripts ----

  await test("writeStartScripts produces sh + cmd with right content", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "amp-team-test-scripts-"));
    try {
      fs.mkdirSync(path.join(dir, "dev"));
      const { shPath, cmdPath, label } = writeStartScripts(dir, "dev", "claude");
      const sh = fs.readFileSync(shPath, "utf8");
      const cmd = fs.readFileSync(cmdPath, "utf8");
      assert.ok(sh.startsWith("#!/bin/sh"));
      assert.ok(sh.includes('cd "$DIR/dev"'));
      assert.ok(sh.includes("exec claude"));
      assert.ok(cmd.startsWith("@echo off"));
      assert.ok(cmd.includes('cd /d "%~dp0dev"'));
      assert.ok(cmd.includes("claude"));
      assert.ok(cmd.includes("\r\n"), "cmd script must use CRLF");
      assert.equal(label, FRAMEWORK_CMD.claude.label);
      if (process.platform !== "win32") {
        const mode = fs.statSync(shPath).mode & 0o777;
        assert.equal(mode, 0o755);
      }
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  await test("writeStartScripts rejects unknown framework", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "amp-team-test-bad-fw-"));
    try {
      assert.throws(
        () => writeStartScripts(dir, "dev", "codex"),
        /unknown framework/,
      );
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  // ---- end-to-end init under stubbed broker ----

  await test("init writes the full team layout under a stubbed broker", async () => {
    const calls = [];
    const originalFetch = global.fetch;
    let agentCounter = 0;
    global.fetch = async (url, opts = {}) => {
      calls.push({ url, method: opts.method || "GET", headers: opts.headers });
      if (url.endsWith("/users/login")) {
        return jsonResponse(200, {
          token: "stub-token",
          user: {
            id: "u1",
            username: "stub-user",
            is_superadmin: false,
            created_at: "2026-01-01T00:00:00Z",
          },
        });
      }
      if (url.endsWith("/users/me/agents") && opts.method === "POST") {
        const body = JSON.parse(opts.body);
        agentCounter += 1;
        return jsonResponse(201, {
          id: `aid-${agentCounter}`,
          name: body.name,
          address: `${body.name}@stub-user.amp.linkyun.co`,
          role: body.role,
          description: body.description || "",
          system_prompt: body.system_prompt || "",
          tags: [],
          team_id: null,
          status: "active",
          created_at: "2026-01-01T00:00:00Z",
          last_seen: null,
          api_key_masked: "******",
          api_key_plaintext: `key-plain-${agentCounter}`,
        });
      }
      if (/\/agents\/[^/]+\/setup$/.test(url)) {
        return jsonResponse(200, {
          agent_md: "# Agent Identity (stub)\n",
          claude_md: "# CLAUDE.md (stub)\n",
          infiniti_md: "# INFINITI.md (stub)\n",
          instructions: "(stub)",
        });
      }
      return jsonResponse(404, { detail: "not stubbed" });
    };

    const promptStub = createPromptStub({
      team: "smoke",
      brokerUrl: "https://stub.example",
      pm: "claude",
      dev: "claude",
      reviewer: "claude",
      support: "infiniti",
      username: "stub-user",
      password: "p@ss",
    });
    const promptsCacheKey = require.resolve("prompts");
    require("prompts"); // force the cache entry to exist before we overwrite it
    const origPromptsExports = require.cache[promptsCacheKey].exports;
    require.cache[promptsCacheKey].exports = promptStub;
    delete require.cache[require.resolve("../src/init")];
    const { runInit } = require("../src/init");

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "amp-team-test-init-"));
    try {
      const code = await runInit(dir);
      assert.equal(code, 0, `runInit exited ${code}`);

      for (const role of ["pm", "dev", "reviewer", "support"]) {
        assert.ok(fs.existsSync(path.join(dir, role)), `${role}/ missing`);
        assert.ok(
          fs.existsSync(path.join(dir, role, ".amp-team", "credentials.json")),
          `${role}/.amp-team/credentials.json missing`,
        );
        assert.ok(
          fs.existsSync(path.join(dir, role, ".amp-team", "inbox.js")),
          `${role}/.amp-team/inbox.js missing`,
        );
        assert.ok(fs.existsSync(path.join(dir, `start-${role}.sh`)));
        assert.ok(fs.existsSync(path.join(dir, `start-${role}.cmd`)));

        if (process.platform !== "win32") {
          const mode = fs.statSync(path.join(dir, role, ".amp-team", "credentials.json")).mode & 0o777;
          assert.equal(mode, 0o600, `${role} credentials must be 0600, got ${mode.toString(8)}`);
        }

        const creds = JSON.parse(
          fs.readFileSync(path.join(dir, role, ".amp-team", "credentials.json"), "utf8"),
        );
        assert.equal(creds.role, role);
        assert.equal(creds.broker_url, "https://stub.example");
        assert.ok(creds.api_key.startsWith("key-plain-"));
      }

      for (const role of ["pm", "dev", "reviewer"]) {
        assert.ok(fs.existsSync(path.join(dir, role, "AGENT.md")));
        assert.ok(fs.existsSync(path.join(dir, role, "CLAUDE.md")));
      }
      assert.ok(fs.existsSync(path.join(dir, "support", "SOUL.md")));
      assert.ok(fs.existsSync(path.join(dir, "support", "INFINITI.md")));

      const team = JSON.parse(
        fs.readFileSync(path.join(dir, ".amp-team", "team.json"), "utf8"),
      );
      assert.equal(team.team_name, "smoke");
      assert.equal(team.partial, false);
      assert.equal(team.agents.length, 4);

      const createCalls = calls.filter(
        (c) => c.url.endsWith("/users/me/agents") && c.method === "POST",
      );
      assert.equal(createCalls.length, 4);
      for (const c of createCalls) {
        assert.equal(c.headers.Authorization, "Bearer stub-token");
      }
      const setupCalls = calls.filter((c) => c.url.includes("/setup"));
      assert.equal(setupCalls.length, 4);
      for (const c of setupCalls) {
        assert.ok(c.headers["X-API-Key"].startsWith("key-plain-"));
      }
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
      global.fetch = originalFetch;
      require.cache[promptsCacheKey].exports = origPromptsExports;
    }
  });

  await test("init aborts when broker rejects the first agent and writes partial marker", async () => {
    const originalFetch = global.fetch;
    global.fetch = async (url, opts = {}) => {
      if (url.endsWith("/users/login")) {
        return jsonResponse(200, {
          token: "stub-token",
          user: {
            id: "u1",
            username: "stub-user",
            is_superadmin: false,
            created_at: "2026-01-01T00:00:00Z",
          },
        });
      }
      if (url.endsWith("/users/me/agents") && opts.method === "POST") {
        return jsonResponse(409, { detail: "address already taken" });
      }
      return jsonResponse(404, { detail: "not stubbed" });
    };

    const promptStub = createPromptStub({
      team: "smoke2",
      brokerUrl: "https://stub.example",
      pm: "claude",
      dev: "claude",
      reviewer: "claude",
      support: "claude",
      username: "stub-user",
      password: "p@ss",
    });
    const promptsCacheKey = require.resolve("prompts");
    require("prompts"); // force the cache entry to exist before we overwrite it
    const origPromptsExports = require.cache[promptsCacheKey].exports;
    require.cache[promptsCacheKey].exports = promptStub;
    delete require.cache[require.resolve("../src/init")];
    const { runInit } = require("../src/init");

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "amp-team-test-init-fail-"));
    try {
      const code = await runInit(dir);
      assert.equal(code, 2, `expected exit 2 on broker failure, got ${code}`);
      const meta = JSON.parse(
        fs.readFileSync(path.join(dir, ".amp-team", "team.json"), "utf8"),
      );
      assert.equal(meta.partial, true);
      assert.equal(meta.failure.role, "pm");
      assert.ok(meta.failure.error.includes("409"));
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
      global.fetch = originalFetch;
      require.cache[promptsCacheKey].exports = origPromptsExports;
    }
  });

  await test(
    "framework: coming-soon picks (codex/openclaw/dreamfactory) hard-fail with retry",
    async () => {
      // Stateful prompt: pm gets asked twice (codex → claude), others claude.
      const pmAnswers = ["codex", "claude"];
      const stubbed = async function (questions) {
        const qs = Array.isArray(questions) ? questions : [questions];
        const out = {};
        for (const q of qs) {
          if (q.name === "team") out.team = "smoke3";
          else if (q.name === "brokerUrl") out.brokerUrl = "https://stub.example";
          else if (q.name === "username") out.username = "stub-user";
          else if (q.name === "password") out.password = "p@ss";
          else if (q.name === "framework") {
            const m = /for \S*?(\w+)\S*? \(/.exec(q.message);
            const role = m ? m[1] : null;
            if (role === "pm") {
              out.framework = pmAnswers.shift() || "claude";
            } else {
              out.framework = "claude";
            }
          }
        }
        return out;
      };

      const createAgentCalls = [];
      const originalFetch = global.fetch;
      let agentCounter = 0;
      global.fetch = async (url, opts = {}) => {
        if (url.endsWith("/users/login")) {
          return jsonResponse(200, {
            token: "stub-token",
            user: {
              id: "u1",
              username: "stub-user",
              is_superadmin: false,
              created_at: "2026-01-01T00:00:00Z",
            },
          });
        }
        if (url.endsWith("/users/me/agents") && opts.method === "POST") {
          const body = JSON.parse(opts.body);
          createAgentCalls.push(body);
          agentCounter += 1;
          return jsonResponse(201, {
            id: `aid-${agentCounter}`,
            name: body.name,
            address: `${body.name}@stub-user.amp.linkyun.co`,
            role: body.role,
            description: body.description || "",
            system_prompt: body.system_prompt || "",
            tags: [],
            team_id: null,
            status: "active",
            created_at: "2026-01-01T00:00:00Z",
            last_seen: null,
            api_key_masked: "******",
            api_key_plaintext: `key-plain-${agentCounter}`,
          });
        }
        if (/\/agents\/[^/]+\/setup$/.test(url)) {
          return jsonResponse(200, {
            agent_md: "# Agent Identity (stub)\n",
            claude_md: "# CLAUDE.md (stub)\n",
            infiniti_md: "# INFINITI.md (stub)\n",
            instructions: "(stub)",
          });
        }
        return jsonResponse(404, { detail: "not stubbed" });
      };

      const promptsCacheKey = require.resolve("prompts");
      require("prompts");
      const origPromptsExports = require.cache[promptsCacheKey].exports;
      require.cache[promptsCacheKey].exports = stubbed;
      delete require.cache[require.resolve("../src/init")];
      const { runInit } = require("../src/init");

      const dir = fs.mkdtempSync(path.join(os.tmpdir(), "amp-team-test-codex-"));
      try {
        const code = await runInit(dir);
        assert.equal(code, 0, `runInit exited ${code}`);

        // The codex pick MUST have triggered a retry — the second answer was
        // consumed. If silent fallback regressed, the second pick would be
        // ignored and the array would still have one entry.
        assert.equal(
          pmAnswers.length,
          0,
          "coming-soon pick must re-prompt; second answer not consumed",
        );

        // createAgent was called exactly 4× (one per role). Codex never reached
        // the broker — selecting a coming-soon framework does not register
        // anything.
        assert.equal(
          createAgentCalls.length,
          4,
          `expected 4 createAgent calls, got ${createAgentCalls.length}`,
        );
        for (const body of createAgentCalls) {
          assert.notEqual(body.role, "codex", "no agent should carry codex role");
        }

        // On-disk effect reflects the retry pick (claude), not codex.
        const pmCreds = JSON.parse(
          fs.readFileSync(path.join(dir, "pm", ".amp-team", "credentials.json"), "utf8"),
        );
        assert.equal(pmCreds.framework, "claude");
        assert.ok(fs.existsSync(path.join(dir, "pm", "CLAUDE.md")));
        assert.ok(!fs.existsSync(path.join(dir, "pm", "INFINITI.md")));
      } finally {
        fs.rmSync(dir, { recursive: true, force: true });
        global.fetch = originalFetch;
        require.cache[promptsCacheKey].exports = origPromptsExports;
      }
    },
  );

  if (failed > 0) {
    process.stderr.write(`\n${failed} test(s) failed.\n`);
    process.exit(1);
  }
  process.stdout.write("\nall tests passed.\n");
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Map(),
    async json() {
      return body;
    },
    async text() {
      return JSON.stringify(body);
    },
  };
}

function createPromptStub(answers) {
  return async function stubbed(questions /* opts ignored */) {
    const qs = Array.isArray(questions) ? questions : [questions];
    const out = {};
    for (const q of qs) {
      if (q.name === "team") out.team = answers.team;
      else if (q.name === "brokerUrl") out.brokerUrl = answers.brokerUrl;
      else if (q.name === "username") out.username = answers.username;
      else if (q.name === "password") out.password = answers.password;
      else if (q.name === "framework") {
        const m = /for \S*?(\w+)\S*? \(/.exec(q.message);
        const role = m ? m[1] : null;
        out.framework = answers[role] || "claude";
      }
    }
    return out;
  };
}

main().catch((e) => {
  process.stderr.write(`fatal: ${(e && e.stack) || e}\n`);
  process.exit(1);
});
