# 全站 UI 评审原型

这是推荐入口：一套可路由导航的全站原型，保留每个工作面 A/B/C 三种布局以供比较。

在 `emiya-frontend/` 运行：`npm.cmd run prototype:ui`。

路由映射：

- `/` 首页；`/chat`、`/chat/new`、`/chat/settings`、`/chat/card-ui` 对话工作区。
- `/personas/*`、`/worldbooks/*`、`/presets/*`、`/templates/*`、`/regex-presets/*` 创作资产。
- `/memories`、`/mood`、`/relationships` 记忆与感知。
- `/settings`、`/settings/security`、`/login`、`/register`、`/forgot-password`、`/reset-password` 账户和认证。

`?variant=A|B|C` 保留在当前路由上，用于比较工作台、流程板、阅读画布三种结构。全站是只读原型，不注册到正式 SPA，也不调用后端。

顶部“月 / 日”按钮切换统一的夜间与日间基础主题。账户 → 显示偏好中的“自定义 CSS 主题”会立即注入原型页面（刷新后重置），可用来验证全局或对话工作区的主题规则。

导航采用两层顶部胶囊结构：主导航切换首页、对话、创作资产、记忆与感知、账户；进入资产、感知、对话或账户后，会出现对应的横向副导航。原有左侧导航已从原型工作区移除。
