# Story 01: 项目初始化

**优先级**: P0
**状态**: TODO

## 描述
初始化 Python 项目结构，配置依赖管理和开发工具。

## 任务
- [ ] 创建 pyproject.toml，声明依赖（fastapi, uvicorn, aiosqlite）
- [ ] 创建 src/agent_mailer/ 包结构
- [ ] 用 uv 初始化虚拟环境并安装依赖
- [ ] 验证 `uvicorn` 能启动空的 FastAPI app

## 完成标准
- `uv run uvicorn agent_mailer.main:app` 能启动并返回 404
