# PLAN.md: Agent Mailer 实现计划

## 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | LLM 生态亲和，开发效率高 |
| Web 框架 | FastAPI | 异步、自带 OpenAPI 文档、轻量 |
| 数据库 | SQLite + aiosqlite | 本地零依赖，异步非阻塞 |
| 依赖管理 | uv | 快速，替代 pip + venv |
| 运行 | uvicorn | ASGI server |

## 数据模型

### agents 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID，绑定实例 |
| name | TEXT | 显示名，如 "coder" |
| role | TEXT | 角色标识，如 "coder", "reviewer" |
| description | TEXT | 该 Agent 的职责描述 |
| system_prompt | TEXT | 身份提示词，如"你是一个开发者" |
| created_at | TEXT | ISO8601 |

### messages 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| thread_id | TEXT | 会话线程 ID，首条消息时自动生成 |
| from_agent | TEXT FK | 发件人 agent id |
| to_agent | TEXT FK | 收件人 agent id |
| action | TEXT | send / reply / forward |
| subject | TEXT | 主题 |
| body | TEXT | 正文内容 |
| attachments | TEXT | JSON 数组，存文件路径引用 |
| is_read | INTEGER | 0=未读, 1=已读 |
| parent_id | TEXT | 回复/转发的原始消息 ID，可为空 |
| created_at | TEXT | ISO8601 |

## API 设计

### Agent 管理

```
POST   /agents/register     注册 Agent，返回 {id}
GET    /agents               列出所有已注册 Agent
GET    /agents/{id}          查询单个 Agent
GET    /agents/{id}/setup    获取 AGENT.md 和 CLAUDE.md 模板
```

### 邮件操作

```
POST   /messages/send        发送消息（send / reply / forward 统一入口）
GET    /messages/inbox/{agent_id}           获取未读消息
GET    /messages/inbox/{agent_id}?all=true  获取全部消息
GET    /messages/thread/{thread_id}         获取整个 thread 的消息链
PATCH  /messages/{id}/read                  标记已读
```

### Send 请求体

```json
{
  "from_agent": "uuid",
  "to_agent": "uuid",
  "action": "send | reply | forward",
  "subject": "...",
  "body": "...",
  "attachments": ["/path/to/file"],
  "parent_id": "原消息ID，reply/forward时必填"
}
```

- `send`: 新建 thread，`thread_id` 自动生成
- `reply`: 沿用 parent 的 `thread_id`
- `forward`: 沿用 parent 的 `thread_id`，切换收件人

## 项目结构

```
agent-mailer/
├── SPEC.md
├── PLAN.md
├── pyproject.toml
├── src/
│   └── agent_mailer/
│       ├── __init__.py
│       ├── main.py          # FastAPI app + uvicorn 启动
│       ├── db.py             # SQLite 初始化与连接管理
│       ├── models.py         # Pydantic schema
│       └── routes/
│           ├── __init__.py
│           ├── agents.py     # Agent 注册/查询
│           └── messages.py   # 消息收发
└── tests/
    ├── conftest.py
    ├── test_agents.py
    └── test_messages.py
```

## 实现步骤

1. 初始化项目：pyproject.toml、依赖安装
2. 实现 db.py：建表、连接管理
3. 实现 models.py：请求/响应的 Pydantic schema
4. 实现 routes/agents.py：注册与查询
5. 实现 routes/messages.py：send、inbox、thread、标记已读
6. 实现 main.py：组装路由、启动入口
7. 编写测试
