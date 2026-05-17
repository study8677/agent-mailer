"use strict";

const fs = require("fs");
const path = require("path");
const os = require("os");
const prompts = require("prompts");
const chalk = require("chalk");

const { isEmptyDir } = require("./empty-dir");
const { slugifyTeam, isValidTeamSlug } = require("./slug");
const {
  DEFAULT_BROKER_URL,
  BrokerError,
  InvalidCredentialsError,
  login,
  createAgent,
  getAgentSetup,
} = require("./broker");
const { FRAMEWORK_CMD, writeStartScripts } = require("./scripts");

const ROLES = [
  { key: "pm", title: "Product Manager", systemPrompt: pmSystemPrompt },
  { key: "dev", title: "Developer", systemPrompt: devSystemPrompt },
  { key: "reviewer", title: "Reviewer", systemPrompt: reviewerSystemPrompt },
  { key: "support", title: "Support", systemPrompt: supportSystemPrompt },
];

const SUPPORTED_FRAMEWORKS = ["claude", "infiniti"];

const FRAMEWORK_CHOICES = [
  { title: "Claude Code", value: "claude" },
  { title: "Infiniti-Agent", value: "infiniti" },
  { title: "Codex (即将支持)", value: "codex", disabled: true },
  { title: "OpenClaw (即将支持)", value: "openclaw", disabled: true },
  { title: "Dreamfactory (即将支持)", value: "dreamfactory", disabled: true },
];

async function runInit(cwd) {
  const check = isEmptyDir(cwd);
  if (!check.ok) {
    process.stderr.write(`${chalk.red("✖")} ${check.reason}\n`);
    process.stderr.write(
      `  amp-team only runs in an empty directory (developer noise like .git is fine).\n`,
    );
    return 1;
  }

  process.stdout.write(chalk.cyan.bold("amp-team — register an agent team\n"));
  process.stdout.write(chalk.dim(`workdir: ${cwd}\n\n`));

  const defaults = {
    team: slugifyTeam(path.basename(cwd)) || "team",
    brokerUrl: process.env.AMP_TEAM_BROKER_URL || DEFAULT_BROKER_URL,
  };

  const setup = await collectSetupAnswers(defaults);
  if (!setup) {
    process.stderr.write(`${chalk.red("✖")} aborted — incomplete answers\n`);
    return 1;
  }

  const auth = await loginInteractive(setup.brokerUrl);
  if (!auth) return 1;

  process.stdout.write(
    `\n${chalk.green("✓")} logged in as ${chalk.bold(auth.user.username)}\n`,
  );
  process.stdout.write(chalk.dim(`broker: ${setup.brokerUrl}\n\n`));

  const teamMeta = {
    team_name: setup.team,
    username: auth.user.username,
    broker_url: setup.brokerUrl,
    created_at: new Date().toISOString(),
    partial: false,
    agents: [],
  };

  const created = [];
  for (const role of ROLES) {
    const framework = setup.frameworks[role.key];
    process.stdout.write(
      `→ creating ${chalk.bold(role.key)} agent ` +
        chalk.dim(`(${FRAMEWORK_CMD[framework].label})...\n`),
    );
    let agent;
    try {
      agent = await createAgent(setup.brokerUrl, auth.token, {
        name: `${setup.team}-${role.key}`,
        role: role.key,
        description: `${role.title} for team ${setup.team}`,
        system_prompt: role.systemPrompt(setup.team),
      });
    } catch (e) {
      teamMeta.partial = true;
      teamMeta.failure = {
        role: role.key,
        error: e.message,
        completed_roles: created.map((c) => c.role),
      };
      writeTeamMeta(cwd, teamMeta);
      process.stderr.write(
        `${chalk.red("✖")} broker rejected agent creation for ${role.key}: ${e.message}\n`,
      );
      process.stderr.write(
        chalk.dim(
          `  ${created.length} of ${ROLES.length} agents were created before this. ` +
            `See .amp-team/team.json for the partial state; re-run amp-team in a fresh dir after fixing the issue.\n`,
        ),
      );
      return 2;
    }

    let setupResp;
    try {
      setupResp = await getAgentSetup(setup.brokerUrl, agent.id, agent.api_key_plaintext);
    } catch (e) {
      teamMeta.partial = true;
      teamMeta.failure = {
        role: role.key,
        error: `setup fetch failed: ${e.message}`,
        completed_roles: created.map((c) => c.role),
      };
      // Still record the agent we did create so the user has its credentials.
      teamMeta.agents.push({ role: role.key, id: agent.id, address: agent.address });
      writeTeamMeta(cwd, teamMeta);
      process.stderr.write(
        `${chalk.red("✖")} could not fetch /agents/${agent.id}/setup: ${e.message}\n`,
      );
      return 2;
    }

    materializeRoleDir({
      rootDir: cwd,
      role: role.key,
      framework,
      agent,
      setupResp,
      brokerUrl: setup.brokerUrl,
    });
    writeStartScripts(cwd, role.key, framework);

    teamMeta.agents.push({
      role: role.key,
      id: agent.id,
      address: agent.address,
      framework,
    });
    created.push({ role: role.key, id: agent.id, address: agent.address, framework });

    process.stdout.write(
      `  ${chalk.green("✓")} ${agent.address} ${chalk.dim(`(id ${agent.id.slice(0, 8)}…)`)}\n`,
    );
  }

  writeTeamMeta(cwd, teamMeta);

  process.stdout.write(
    `\n${chalk.green.bold("done.")} 4 agents registered, 4 workdirs ready.\n\n`,
  );
  process.stdout.write("Next:\n");
  for (const c of created) {
    process.stdout.write(
      `  ${chalk.cyan(`./start-${c.role}.sh`)}` +
        `  ${chalk.dim(`# launch ${FRAMEWORK_CMD[c.framework].label} as ${c.address}`)}\n`,
    );
  }
  process.stdout.write(
    `  ${chalk.cyan(`node pm/.amp-team/inbox.js`)}  ${chalk.dim("# live inbox view (2s refresh)")}\n`,
  );
  return 0;
}

async function collectSetupAnswers(defaults) {
  const answers = await prompts(
    [
      {
        type: "text",
        name: "team",
        message: "Team name (used as agent address prefix)",
        initial: defaults.team,
        validate: (v) => {
          const slug = slugifyTeam(v);
          if (!isValidTeamSlug(slug)) {
            return "must start and end with a letter or digit; allowed middle: . _ -";
          }
          return true;
        },
        format: (v) => slugifyTeam(v),
      },
      {
        type: "text",
        name: "brokerUrl",
        message: "Broker URL",
        initial: defaults.brokerUrl,
      },
    ],
    { onCancel: () => false },
  );
  if (!answers.team || !answers.brokerUrl) return null;

  const frameworks = {};
  for (const role of ROLES) {
    while (true) {
      const resp = await prompts(
        {
          type: "select",
          name: "framework",
          message: `Agent framework for ${chalk.bold(role.key)} (${role.title})`,
          choices: FRAMEWORK_CHOICES,
          initial: 0,
        },
        { onCancel: () => false },
      );
      if (!resp.framework) return null;
      if (SUPPORTED_FRAMEWORKS.includes(resp.framework)) {
        frameworks[role.key] = resp.framework;
        break;
      }
      // Coming-soon frameworks: refuse and re-prompt. No silent fallback —
      // a fallback would leave the user with a CLAUDE.md when they thought
      // they had picked a different runtime.
      process.stderr.write(
        chalk.red(`  ✖ ${resp.framework} 即将支持，请选 Claude Code 或 Infiniti-Agent。\n`),
      );
    }
  }

  return { team: answers.team, brokerUrl: answers.brokerUrl, frameworks };
}

async function loginInteractive(brokerUrl) {
  const maxAttempts = 3;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const creds = await prompts(
      [
        { type: "text", name: "username", message: "amp.linkyun.co username" },
        { type: "password", name: "password", message: "password" },
      ],
      { onCancel: () => false },
    );
    if (!creds.username || !creds.password) return null;
    try {
      return await login(brokerUrl, creds.username, creds.password);
    } catch (e) {
      if (e instanceof InvalidCredentialsError) {
        process.stdout.write(
          chalk.yellow(`  ! invalid username or password (${attempt}/${maxAttempts})\n`),
        );
        continue;
      }
      if (e instanceof BrokerError) {
        process.stderr.write(`${chalk.red("✖")} broker error: ${e.message}\n`);
        return null;
      }
      throw e;
    }
  }
  process.stderr.write(`${chalk.red("✖")} too many invalid login attempts; aborting.\n`);
  return null;
}

function materializeRoleDir({ rootDir, role, framework, agent, setupResp, brokerUrl }) {
  const roleDir = path.join(rootDir, role);
  const ampTeamDir = path.join(roleDir, ".amp-team");
  fs.mkdirSync(ampTeamDir, { recursive: true });

  // Identity file: AGENT.md for Claude, SOUL.md for Infiniti (per broker /setup
  // instructions: "Linkyun Infiniti Agent → INFINITI.md（引用 SOUL.md）").
  const identityFile = framework === "infiniti" ? "SOUL.md" : "AGENT.md";
  fs.writeFileSync(path.join(roleDir, identityFile), setupResp.agent_md);

  if (framework === "infiniti") {
    fs.writeFileSync(path.join(roleDir, "INFINITI.md"), setupResp.infiniti_md);
  } else {
    fs.writeFileSync(path.join(roleDir, "CLAUDE.md"), setupResp.claude_md);
  }

  const credentials = {
    agent_id: agent.id,
    address: agent.address,
    api_key: agent.api_key_plaintext,
    broker_url: brokerUrl,
    role,
    framework,
    created_at: new Date().toISOString(),
  };
  const credPath = path.join(ampTeamDir, "credentials.json");
  writeSecretFile(credPath, JSON.stringify(credentials, null, 2) + "\n");

  // Copy the inbox template verbatim (zero amp-team-package deps at runtime).
  const inboxSrc = path.join(__dirname, "templates", "inbox.js");
  fs.copyFileSync(inboxSrc, path.join(ampTeamDir, "inbox.js"));
  // Make it executable on POSIX so `./pm/.amp-team/inbox.js` works too.
  if (process.platform !== "win32") {
    fs.chmodSync(path.join(ampTeamDir, "inbox.js"), 0o755);
  }
}

function writeSecretFile(filePath, contents) {
  // Open with 0600 from the start so there's no readable window. On Windows,
  // POSIX permissions are advisory; we still pass the mode (ignored) and rely
  // on the parent .amp-team/ directory being inside the team workdir.
  const fd = fs.openSync(filePath, "w", 0o600);
  try {
    fs.writeFileSync(fd, contents);
  } finally {
    fs.closeSync(fd);
  }
  if (process.platform !== "win32") {
    try {
      fs.chmodSync(filePath, 0o600);
    } catch {
      /* best-effort */
    }
  }
}

function writeTeamMeta(rootDir, teamMeta) {
  const dir = path.join(rootDir, ".amp-team");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, "team.json"),
    JSON.stringify(teamMeta, null, 2) + "\n",
  );
}

function pmSystemPrompt(team) {
  return (
    `你是 ${team} 团队的产品经理 (PM)。你的核心职责：1) 接收 human 需求，澄清边界条件、` +
    `范围、优先级；2) 把需求拆为可执行任务，派给 Dev / Reviewer / Support；3) 在 thread ` +
    `中保持决策可追溯（每个拍板附 message_id 引用）；4) 暴露 trade-off 给 human 拍板，` +
    `不替决策权属于上层的事项做决定。沟通简洁，输出关键路径 + 风险 + 下一步。`
  );
}

function devSystemPrompt(team) {
  return (
    `你是 ${team} 团队的开发工程师 (Dev)。核心职责：1) 根据 PM 派单实现代码；` +
    `2) 遵循既有技术栈与编码规范，改动聚焦；3) 主动暴露技术债、边界情况、依赖阻塞；` +
    `4) 交付时给出关键文件路径、变更摘要、commit hash、自审 grep。`
  );
}

function reviewerSystemPrompt(team) {
  return (
    `你是 ${team} 团队的代码审核者 (Reviewer)。核心职责：1) 审 Dev 交付的实现是否满足 SPEC ` +
    `和 PRD；2) 找 lock-in test、勿绕过的不变量、prompt injection 等高危反模式；` +
    `3) 主动撤回误判（先怀疑再验证再认错）；4) 给出 P0-P3 分级的具体可执行修复建议。`
  );
}

function supportSystemPrompt(team) {
  return (
    `你是 ${team} 团队的客户支持 (Support)。核心职责：1) 接收 user / customer 工单；` +
    `2) 复述问题以确认理解，必要时升级给 Dev / PM；3) 答复时给可操作的下一步，` +
    `不只是「我们正在跟进」；4) 把 recurring issue 抽象为 FAQ 或 bug 报告。`
  );
}

module.exports = { runInit };
