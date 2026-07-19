# EMIYA 界面原型

这里存放**独立、可删除的界面评审原型**。它们不属于主 SPA 的 `src/`，不注册正式路由，不调用后端，也不写入用户数据。

每个原型使用一个子目录；后续角色、对话、记忆、情绪、世界书和设置等页面的方案都应作为同级目录加入。每个目录须包含：独立入口、运行说明、评审问题，以及明确的清理/吸收说明。

**推荐从统一入口开始：**`npm run prototype:ui`。它会通过路由连接全部工作面；下表的独立入口只保留给某一个范围的集中评审。

| 原型 | 评审问题 | 启动命令 |
| --- | --- | --- |
| `immersive-home/` | 首页如何组织故事、角色、关系和上下文能力？ | `npm run prototype:home` |
| `ui-review/` | 如何在一套可导航体验中评审全站 UI？ | `npm run prototype:ui` |
| `conversation-surface/` | 聊天、开场配置、对话控制与 MVU 卡 UI 如何共存？ | `npm run prototype:conversation` |
| `creative-studio/` | 角色、世界书、预设、模板、正则如何共享创作工作台？ | `npm run prototype:studio` |
| `insight-atlas/` | 记忆治理、情绪统计与关系如何形成可读的洞察？ | `npm run prototype:insights` |
| `account-journey/` | 账户偏好、安全设备与认证页面如何组织？ | `npm run prototype:account` |

在 `emiya-frontend/` 下运行命令。首页原型可用 `?variant=A`、`?variant=B`、`?variant=C` 直接打开对应方案。

其余四个原型也使用相同的 `?variant=A|B|C` 约定；每一项均为只读展示，未接入正式 SPA 路由或后端。
