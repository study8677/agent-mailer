# Story 06: 端到端集成测试

**优先级**: P1
**状态**: TODO

## 描述
模拟完整的协作工作流，验证系统端到端可用。

## 任务
- [ ] 模拟流程：注册 planner/coder/reviewer 三个 Agent
- [ ] planner send 任务给 coder
- [ ] coder reply 结果给 reviewer
- [ ] reviewer reply 打回给 coder
- [ ] coder 修复后 reply 给 reviewer
- [ ] 验证每个节点的 inbox 和 thread 状态正确

## 完成标准
- 完整工作流跑通，所有断言通过
