# Story 04: 发送消息

**优先级**: P0
**状态**: TODO

## 描述
实现消息发送功能，支持 send/reply/forward 三种 action。

## 任务
- [ ] 定义 Pydantic schema（SendRequest, MessageResponse）
- [ ] POST /messages/send：统一发送入口
  - send：自动生成 thread_id
  - reply：继承 parent 的 thread_id
  - forward：继承 parent 的 thread_id，切换收件人
- [ ] 校验：reply/forward 时 parent_id 必填且存在
- [ ] 编写测试

## 完成标准
- 三种 action 均能正确创建消息，thread_id 逻辑正确
