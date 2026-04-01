# Story 05: 收件箱与消息线程

**优先级**: P0
**状态**: TODO

## 描述
实现 Agent 收件箱查询、线程查询和标记已读功能。

## 任务
- [ ] GET /messages/inbox/{agent_id}：默认返回未读消息
- [ ] GET /messages/inbox/{agent_id}?all=true：返回全部消息
- [ ] GET /messages/thread/{thread_id}：按时间序返回整个 thread
- [ ] PATCH /messages/{id}/read：标记已读
- [ ] 编写测试

## 完成标准
- 收件箱过滤正确，thread 链路完整，已读状态可切换
