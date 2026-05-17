#!/usr/bin/env node
"use strict";

const { runInit } = require("../src/init");

async function main() {
  const argv = process.argv.slice(2);
  if (argv.includes("--help") || argv.includes("-h")) {
    process.stdout.write(
      [
        "amp-team — register a 4-role agent team and scaffold workdirs.",
        "",
        "Usage:",
        "  amp-team              run init flow in the current empty directory",
        "  amp-team --help       show this help",
        "  amp-team --version    show package version",
        "",
        "After init, each role has its own `start-<role>.sh` / `.cmd` to launch",
        "the chosen agent framework, and `node <role>/.amp-team/inbox.js` polls",
        "that role's broker inbox with 2s TUI refresh.",
        "",
      ].join("\n"),
    );
    return 0;
  }
  if (argv.includes("--version") || argv.includes("-V")) {
    const pkg = require("../package.json");
    process.stdout.write(`${pkg.version}\n`);
    return 0;
  }
  return runInit(process.cwd());
}

main().then(
  (code) => process.exit(code || 0),
  (err) => {
    process.stderr.write(`\n✖ ${err && err.message ? err.message : err}\n`);
    if (process.env.AMP_TEAM_DEBUG && err && err.stack) {
      process.stderr.write(`${err.stack}\n`);
    }
    process.exit(1);
  },
);
