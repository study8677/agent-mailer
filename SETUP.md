# SETUP.md: Agent 接入指南

## 概述

每个 Agent 在加入协作网络前，需要完成 **注册** 和 **工作目录配置** 两个步骤。
核心目标：让 Agent 在启动时自动知道「我是谁」以及「如何与其他 Agent 通信」。

---

## 第一步：注册 Agent

向 Broker 注册，获取唯一身份。

```bash
curl -X POST http://localhost:8000/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "coder",
    "role": "coder",
    "description": "负责根据需求编写代码",
    "system_prompt": "你是一个专业的软件开发者。你擅长 Python 和 TypeScript，负责将需求拆解为可执行的代码实现。收到任务后，你应该编写高质量的代码并附带测试，完成后将结果回复给审查者。"
  }'
```

### 关键字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | Agent 显示名，如 `coder`、`reviewer`、`planner` |
| `role` | 是 | 角色标识，用于路由和权限区分 |
| `description` | 否 | 简要职责描述 |
| **`system_prompt`** | **是** | **身份提示词 — Agent 的核心行为定义，会写入 AGENT.md** |

### `system_prompt` 示例

不同角色的身份提示词示例：

**Planner（需求拆解）：**
```
你是一个需求分析与架构设计专家。你负责将用户的原始需求拆解为清晰的技术规格说明书，
包含模块划分、接口设计和实现优先级。完成后将任务转发给 Coder。
```

**Coder（代码实现）：**
```
你是一个专业的软件开发者。你根据收到的技术规格编写高质量代码，
确保代码有充分的测试覆盖。完成后提交给 Reviewer 进行审查。
```

**Reviewer（代码审查）：**
```
你是一个严格的代码审查专家。你负责检查代码质量、安全性和性能，
发现问题时附带具体修改建议打回给 Coder，通过审查后通知发起人。
```

**管理 Agent：**
```
你是一个项目管理智能体。你负责协调各 Agent 之间的工作流，
监控任务进度，在任务卡住时进行干预和重新分配。
```

---

## 第二步：获取工作目录配置

注册成功后，调用 setup 端点获取需要放置在工作目录中的配置文件内容：

```bash
curl http://localhost:8000/agents/{agent_id}/setup
```

返回内容包含：
- `agent_md` — AGENT.md 的完整内容（身份、协议、API 地址）
- `claude_md` — CLAUDE.md 模板（适用于 Claude Code）
- `instructions` — 配置步骤说明

---

## 第三步：配置工作目录

### 文件结构

```
~/workspace/coder/          # Coder Agent 的工作目录
├── AGENT.md                # 身份定义 + 通信协议（所有 Agent 通用）
├── CLAUDE.md               # Claude Code 专用启动配置（引用 AGENT.md）
└── ... (项目代码)
```

### AGENT.md

AGENT.md 是 **所有 Agent 通用的身份文件**，包含：

1. **Agent 元信息**：name、role、Agent ID、Broker URL
2. **身份提示词**（system_prompt）：定义 Agent 的行为和职责
3. **邮箱协议**：收件、发件、标记已读等 API 说明

将 `/agents/{id}/setup` 返回的 `agent_md` 字段内容保存为工作目录下的 `AGENT.md`。

### CLAUDE.md（Claude Code 适配）

Claude Code 启动时会自动加载当前目录下的 `CLAUDE.md`。
因此需要在 CLAUDE.md 中 **引用 AGENT.md**，让 Claude 自动获取身份：

```markdown
# CLAUDE.md

请在启动时加载 AGENT.md 以获取你的身份和通信协议。

@import AGENT.md

## 行为指引

1. 启动后先通过 Inbox API 检查是否有未读消息
2. 按照 AGENT.md 中的身份提示词行事
3. 完成任务后通过 Reply 或 Forward 将结果发送给下一个环节
4. 所有通信必须经过 Mail Broker，使用你的 Agent ID
```

### 其他 Agent 适配

对于非 Claude Code 的 Agent（如 Cursor、自研 Agent），根据其配置机制：

| Agent 类型 | 配置方式 |
|-----------|---------|
| Claude Code | `CLAUDE.md` 引用 `AGENT.md` |
| Cursor | `.cursorrules` 引用 `AGENT.md` |
| 自研 Agent | 启动时读取 `AGENT.md` 解析身份和 API |

---

## 完整流程示例

```bash
# 1. 启动 Broker
cd agent-mailer && uv run python -m agent_mailer.main

# 2. 注册 Coder Agent
CODER_ID=$(curl -s -X POST http://localhost:8000/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "coder",
    "role": "coder",
    "description": "代码实现",
    "system_prompt": "你是一个专业的软件开发者，负责将需求转化为高质量代码。"
  }' | jq -r '.id')

# 3. 获取配置
SETUP=$(curl -s http://localhost:8000/agents/$CODER_ID/setup)

# 4. 写入工作目录
mkdir -p ~/workspace/coder
echo "$SETUP" | jq -r '.agent_md' > ~/workspace/coder/AGENT.md
echo "$SETUP" | jq -r '.claude_md' > ~/workspace/coder/CLAUDE.md

# 5. 在该目录启动 Claude Code
cd ~/workspace/coder && claude
# Claude 自动加载 CLAUDE.md -> 读取 AGENT.md -> 知道自己是 coder，开始查收邮件
```

---

## 设计要点

- **`system_prompt` 是注册时的必填项**：它定义了 Agent 的核心行为，不同的身份提示词让同一个底层 LLM 扮演不同角色
- **AGENT.md 是通用格式**：不绑定任何特定 Agent 实现，任何能读取 Markdown 的系统都可以解析
- **CLAUDE.md 是适配层**：针对 Claude Code 的启动机制，通过引用 AGENT.md 实现身份注入
- **一目录一身份**：不同工作目录对应不同 Agent 身份，同一个 Claude Code 在不同目录下自动切换角色
