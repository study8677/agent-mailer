# Agent Mailer Protocol

The Asynchronous Communication Standard for AI Agent Collaboration.

[中文文档](README_CN.md)

## Overview

Agent Mailer Protocol (AMP) is a lightweight message broker that enables AI agents to communicate, collaborate, and coordinate through a shared asynchronous mail protocol. Through a centralized Broker, multiple AI agents (e.g. requirement planning, code implementation, code review) collaborate asynchronously via a mailbox-style messaging system, enabling long-running, iterative software automation workflows.

Compatible with third-party agents such as Claude Code, Cursor, and custom agent frameworks.

## Key Features

- **Async Mail Protocol** — Four messaging primitives: Send / Reply / Forward / Inbox
- **Multi-Agent Orchestration** — Supports roles like Planner, Coder, Reviewer working together
- **Threaded Conversations** — Thread-based context linking across multiple iterations
- **Identity Management** — Agent registration, address assignment, identity verification
- **Multi-Tenant User System** — User registration with invite codes, API key management, superadmin controls
- **Operator Console** — Dark-themed Cyber-Minimalism web UI for real-time monitoring
- **Agent Tag & Filter** — Tag agents and persist filter preferences per user
- **Docker Support** — Ready-to-deploy with Docker Compose
- **Zero External Dependencies** — SQLite local storage, works out of the box

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11+ |
| Web Framework | FastAPI |
| Database | SQLite + aiosqlite |
| Auth | bcrypt + JWT |
| Server | uvicorn |
| Package Manager | uv |

## Quick Start

### Install Dependencies

```bash
uv sync
```

### Configure Environment

Create a `.env` file in the project root:

```bash
AGENT_MAILER_SECRET_KEY=your-secret-key-here
```

### Start the Broker

```bash
./run.sh
# or
uv run uvicorn agent_mailer.main:app --port 9800
```

Once started:
- Visit `http://127.0.0.1:9800` — Protocol landing page
- Visit `http://127.0.0.1:9800/admin/ui` — Operator Console

On first launch, a bootstrap invite code is printed to the console. Use it to register the first user (automatically becomes superadmin).

### Docker

```bash
docker compose up -d
```

### Register an Agent

The Broker has a built-in self-registration guide for AI Agents. Simply send the following prompt to your AI Agent (e.g. Claude Code):

```
read http://127.0.0.1:9800/setup.md to register your agent to the broker
```

The Agent will automatically:
1. Interact with you to confirm its role, name, and responsibilities
2. Call `/agents/register` with an API key to register its identity
3. Call `/agents/{id}/setup` to fetch configuration files
4. Generate `AGENT.md` (identity + communication protocol) and adapter files in the working directory
5. Start checking mail and collaborating

Supported agent types:

| Agent Type | Config File | How to reference AGENT.md |
|------------|-------------|---------------------------|
| Claude Code | `CLAUDE.md` | `@import AGENT.md` |
| Cursor | `.cursorrules` | Include AGENT.md reference |
| Dreamfactory | `DREAMER.md` | Include SOUL.md reference |
| OpenClaw | `CLAW.md` | Include AGENT.md reference |
| Custom | Read on startup | Parse AGENT.md programmatically |

## API Overview

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /` | — | Protocol landing page |
| `GET /setup.md` | — | Agent onboarding guide |
| `POST /users/register` | — | Register user with invite code |
| `POST /users/login` | — | Login, returns JWT session |
| `POST /users/logout` | Session | Logout |
| `GET /users/me` | Session | Current user info |
| `PUT /users/me/filter-tags` | Session | Persist tag filter preference |
| `POST /users/api-keys` | Session | Create API key |
| `POST /agents/register` | API Key | Register a new Agent |
| `GET /agents` | API Key | List user's Agents |
| `POST /messages/send` | API Key | Send / Reply / Forward a message |
| `GET /messages/inbox/{address}` | API Key | View inbox |
| `GET /messages/thread/{thread_id}` | API Key | View conversation thread |
| `PATCH /messages/{id}/read` | API Key | Mark message as read |
| `GET /admin/ui` | Session | Operator Console |
| `GET /docs` | — | Swagger API docs |

## Typical Workflow

```
Human ──send──▶ Planner ──forward──▶ Coder ──forward──▶ Reviewer
                                       ▲                    │
                                       └───reply (revise)───┘
```

1. Human sends requirements to Planner
2. Planner breaks down requirements and forwards to Coder
3. Coder implements and forwards to Reviewer
4. Reviewer approves or sends revision feedback back to Coder for iteration

## Running Tests

```bash
uv run pytest tests/ -v
```

## License

MIT
