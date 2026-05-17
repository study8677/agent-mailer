"use strict";

const DEFAULT_BROKER_URL = "https://amp.linkyun.co";

class BrokerError extends Error {
  constructor(message, { status, body } = {}) {
    super(message);
    this.name = "BrokerError";
    this.status = status;
    this.body = body;
  }
}

class InvalidCredentialsError extends BrokerError {
  constructor(message = "Invalid username or password") {
    super(message, { status: 401 });
    this.name = "InvalidCredentialsError";
  }
}

async function readErrorBody(resp) {
  try {
    const text = await resp.text();
    try {
      const j = JSON.parse(text);
      if (j && typeof j.detail === "string") return j.detail;
      return text;
    } catch {
      return text;
    }
  } catch {
    return "";
  }
}

// POST /users/login → { token, user }
// Auth scheme verified by source-of-truth (dependencies.get_current_user):
// downstream calls use `Authorization: Bearer <token>` (cookie fallback exists).
async function login(brokerUrl, username, password) {
  const r = await fetch(`${brokerUrl}/users/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (r.status === 401) throw new InvalidCredentialsError();
  if (!r.ok) {
    const body = await readErrorBody(r);
    throw new BrokerError(`POST /users/login failed (HTTP ${r.status}): ${body}`, {
      status: r.status,
      body,
    });
  }
  const data = await r.json();
  if (!data || typeof data.token !== "string" || !data.token) {
    throw new BrokerError("login response missing 'token'");
  }
  return data;
}

// POST /users/me/agents (Bearer) → UserAgentCreateResponse
// One-time api_key_plaintext is in the response. Caller MUST persist it.
async function createAgent(brokerUrl, token, agentBody) {
  const r = await fetch(`${brokerUrl}/users/me/agents`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(agentBody),
  });
  if (!r.ok) {
    const body = await readErrorBody(r);
    throw new BrokerError(`POST /users/me/agents failed (HTTP ${r.status}): ${body}`, {
      status: r.status,
      body,
    });
  }
  const data = await r.json();
  for (const k of ["id", "address", "api_key_plaintext"]) {
    if (!data || typeof data[k] !== "string" || !data[k]) {
      throw new BrokerError(`create-agent response missing '${k}'`);
    }
  }
  return data;
}

// GET /agents/{id}/setup (X-API-Key — agent's own key) → { agent_md, claude_md, infiniti_md, instructions }
async function getAgentSetup(brokerUrl, agentId, apiKey) {
  const r = await fetch(`${brokerUrl}/agents/${encodeURIComponent(agentId)}/setup`, {
    headers: { "X-API-Key": apiKey },
  });
  if (!r.ok) {
    const body = await readErrorBody(r);
    throw new BrokerError(`GET /agents/${agentId}/setup failed (HTTP ${r.status}): ${body}`, {
      status: r.status,
      body,
    });
  }
  return r.json();
}

module.exports = {
  DEFAULT_BROKER_URL,
  BrokerError,
  InvalidCredentialsError,
  login,
  createAgent,
  getAgentSetup,
};
