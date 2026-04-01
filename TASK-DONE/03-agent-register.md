# Story 03: Agent 注册与查询

**优先级**: P0
**状态**: TODO

## 描述
实现 Agent 的注册和查询 API。

## 任务
- [ ] 定义 Pydantic schema（AgentRegisterRequest, AgentResponse）
- [ ] POST /agents/register：注册 Agent，返回 uuid
- [ ] GET /agents：列出所有 Agent
- [ ] GET /agents/{id}：查询单个 Agent
- [ ] 编写测试

## 完成标准
- 能注册 Agent 并查询，重复注册返回合理响应
