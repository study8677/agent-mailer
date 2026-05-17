"use strict";

// Convert a free-form team string into a broker-acceptable local-part.
// Server regex: ^[a-z0-9]([a-z0-9._-]{0,61}[a-z0-9])?$
function slugifyTeam(raw) {
  const lower = String(raw || "").toLowerCase();
  // Replace any disallowed char with '-'; collapse runs of '-'; trim non-alnum edges.
  let slug = lower.replace(/[^a-z0-9._-]+/g, "-").replace(/-+/g, "-");
  slug = slug.replace(/^[^a-z0-9]+/, "").replace(/[^a-z0-9]+$/, "");
  if (slug.length === 0) return "";
  // Leave room for "-support" (longest role suffix, 8 chars) within the 63-char local-part budget.
  const MAX = 63 - "-reviewer".length;
  if (slug.length > MAX) slug = slug.slice(0, MAX).replace(/[^a-z0-9]+$/, "");
  return slug;
}

function isValidTeamSlug(slug) {
  return /^[a-z0-9]([a-z0-9._-]{0,53}[a-z0-9])?$/.test(slug);
}

module.exports = { slugifyTeam, isValidTeamSlug };
