# EMIYA Next（迁移中的新前端）

这是与旧 `emiya-frontend/src/` 并列的新代码库。它不导入旧前端源代码，也不要求修改后端；通过同一组 `/api/v1/*` 接口逐项迁移功能。

当前切片：独立认证、顶部双层导航、真实会话/角色列表、创建对话、历史消息读取，以及通过 SSE 发送聊天消息。角色与世界书支持核心 CRUD 和导入导出；预设、Prompt 模板、正则预设支持真实 CRUD 和 JSON 高级配置，预设与正则支持导入导出；记忆支持读取、编辑、删除；情绪与关系支持真实数据读取；账户资料、CSS 主题、密码与设备会话管理均可用。对话设置支持预设、模板、正则、世界书、Author's Note、情感分析与 MVU 危险能力。系统模板保持只读。未迁移路由会明确显示为占位，不会误导为已可用。

在 `emiya-frontend/` 目录运行：

```powershell
npm.cmd --prefix new-ui run dev
```

新前端运行在 `http://localhost:5174`，旧前端仍可照常使用 `npm.cmd run dev`（5173）。

独立构建验证：

```powershell
npm.cmd --prefix new-ui run build
```

它使用 Vite 将 `/api` 和 `/static` 代理到现有后端 `http://127.0.0.1:8000`。登录状态使用独立的
`emiya-next-token` / `emiya-next-user` 本地存储键，因此不会覆盖旧前端的登录状态。
