"use strict";

const fs = require("fs");

// Entries that don't disqualify a directory from being treated as "empty".
// Match SPEC §3.1 #5: tolerate developer-tool artifacts but reject anything
// that a user could mistake for project work (e.g. node_modules, package.json).
const ALLOWED_NOISE = new Set([".git", ".DS_Store", ".gitignore", "Thumbs.db"]);

function isEmptyDir(dir) {
  let entries;
  try {
    entries = fs.readdirSync(dir);
  } catch (e) {
    return { ok: false, reason: `cannot read directory: ${e.message}` };
  }
  const blockers = entries.filter((name) => !ALLOWED_NOISE.has(name));
  if (blockers.length === 0) return { ok: true };
  return {
    ok: false,
    reason:
      `directory is not empty — found ${blockers.length} unexpected ` +
      `entr${blockers.length === 1 ? "y" : "ies"}: ${blockers.slice(0, 5).join(", ")}` +
      (blockers.length > 5 ? `, ... (${blockers.length - 5} more)` : ""),
    blockers,
  };
}

module.exports = { isEmptyDir, ALLOWED_NOISE };
