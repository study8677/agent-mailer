# Realtime chat skills — setup & install

Two skills let one agent talk to another in a near-realtime, turn-taking
channel over the broker (no websockets — short-interval polling):

- **`/agentstartchat <话题>`** — open a channel, get a join token `#<token>` to
  hand to the other operator, then auto-reply in a turn-taking loop.
- **`/agentjoinchat #<token>`** — join with that token, replay history, and
  take part in the same loop.

The channel has human guardrails: `max_turns=10` and `TTL=30min` pause it to
`pending_human`; only a human can resume it (Close / Continue from the operator
console → **Channels**).

The canonical skill source lives in this repo at
`.claude/skills/agentstartchat/SKILL.md` and `.claude/skills/agentjoinchat/SKILL.md`.
`agent-mailer team init` copies the exact same files — point installs at this
one source so manual copies never drift from what team init ships.

## New teams — nothing to do

`agent-mailer team init` already scaffolds both skills into every Claude agent
workdir (`<role>/.claude/skills/`). They're available the moment the agent
starts. Skip to [Verify](#verify).

## Existing teams — manual install

For teams provisioned before these skills existed, copy the two skill folders
into the `.claude/skills/` of **each agent workdir that should chat** (an agent
needs `agentstartchat` to start and `agentjoinchat` to join — install both
everywhere for simplicity).

```bash
# Point these at your local checkout and the agent's workdir (the dir holding
# that agent's AGENT.md / .env — e.g. <team>/dev, or agents/<name> for zudui layout).
AMP_REPO=/path/to/agent-mailer
AGENT_DIR=/path/to/your-team/dev

mkdir -p "$AGENT_DIR/.claude/skills"
cp -R "$AMP_REPO/.claude/skills/agentstartchat" "$AGENT_DIR/.claude/skills/"
cp -R "$AMP_REPO/.claude/skills/agentjoinchat"  "$AGENT_DIR/.claude/skills/"
```

Repeat the `cp` pair for every agent workdir that should be chat-capable. Claude
Code discovers skills under `<workdir>/.claude/skills/` on its next start.

## Permissions (broker allowlist)

The skills call the broker over HTTPS exactly like every other agent action —
`curl … "$BROKER/channels/..."` where `$BROKER` is your broker URL from
`AGENT.md` (e.g. `https://amp.linkyun.co`).

**Same domain, already covered — no extra config.** The Claude allowlist that
`team init` writes to each `<role>/.claude/settings.json`
(`Bash(curl:*amp.linkyun.co*)` + `WebFetch(domain:amp.linkyun.co)`), and the
broader mother-dir allowlist from `zudui` (`Bash(curl:*)`), both already permit
the `/channels/*` calls. There is **no new domain or method** to allow.

> Optional: the poll loop also runs plain shell helpers (`source ./.env`,
> `sleep`). The broker `curl` is covered; if your agent runs under a strict
> per-agent allowlist and gets prompted on those helpers, add `Bash(source:*)`
> and `Bash(sleep:*)` to that agent's `.claude/settings.json`. This is a local
> settings tweak only — no change to the shipped templates.

## Verify

After installing, confirm the files landed and the skills are discoverable:

```bash
ls "$AGENT_DIR/.claude/skills/"
# → agentjoinchat  agentstartchat   (each containing SKILL.md)
```

Then in that agent's Claude Code session, `/agentstartchat` and `/agentjoinchat`
should appear in the slash-command list. Quick smoke test:

```
/agentstartchat 测试一下 channel
```

It should return a `#<token>`; hand that token to a second agent's operator and
run `/agentjoinchat #<token>` there. Watch the live transcript and use the
**Channels** view in the operator console (`/admin/ui`) to Close or Continue.
