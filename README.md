# EMIYA

EMIYA 是一个面向**角色扮演与情感陪伴**的 AI 对话平台。你可以导入或创建 AI 角色卡，围绕它进行长期对话——系统会记住聊过的事、感知情绪的起伏、积累好感与关系，并兼容 SillyTavern 生态的角色卡、世界书、预设与正则。

**特点一览**

- 🎭 **兼容 SillyTavern 生态**：导入 / 导出 PNG·JSON 角色卡（v1/v2/v3），世界书、ST 预设、正则脚本、MVU 变量卡开箱即用。
- 🧠 **长期记忆**：自动提取对话中的长期记忆并做语义检索，越聊越懂你。
- ❤️ **情绪与关系**：识别情绪、记录心情、积累好感度与关系等级，带情绪仪表盘与里程碑。
- 🌍 **世界书 + 预设 + 模板**：按关键词/常驻规则注入设定，ST 风格 prompt 编排，可视化编辑器。
- 🎨 **前端可自定义**：内置日/夜暖色主题，支持用户级全站 CSS 换肤（令牌契约 + 起手预设 + 逃生模式）。
- ⚡ **流式对话**：SSE 流式回复，前端支持 Markdown 与整页 HTML 状态栏渲染。

**技术栈**

- 后端：FastAPI · SQLAlchemy(Async) · LangGraph · PostgreSQL · Redis · ChromaDB
- 前端：Vue 3 · TypeScript · Pinia · Naive UI · Vite
- LLM：DeepSeek API

---

## 快速启动

**环境要求**：Python 3.11+ · Node.js 20+ · Docker（含 Compose）

### 1. 启动基础服务

在仓库根目录：

```bash
docker compose up -d
```

会拉起 PostgreSQL(`5432`)、Redis(`6379`)、ChromaDB(`8001`)，端口已与 `.env.example` 默认值对齐。

### 2. 配置环境变量

```bash
cp .env.example .env
```

**最少只需填一项** `DEEPSEEK_API_KEY`（数据库 / Redis / JWT 的默认值已与 docker-compose 对齐，可直接跑）。生产环境记得把 `JWT_SECRET_KEY` 换成长随机串。

### 3. 启动后端

```bash
cd emiya-backend
pip install -r requirements.txt      # 建议先建虚拟环境
alembic upgrade head                 # 数据库迁移
uvicorn app.main:app --reload --port 8000
```

健康检查：<http://localhost:8000/health>

### 4. 启动前端

```bash
cd emiya-frontend
npm install
npm run dev
```

访问 <http://localhost:5173>，注册账号即可开始。

---

## 项目结构

```text
charAgent/
├── emiya-backend/          FastAPI 后端
│   ├── app/
│   │   ├── api/            HTTP / SSE 路由
│   │   ├── models/         SQLAlchemy ORM
│   │   ├── schemas/        Pydantic 请求 / 响应模型
│   │   ├── services/       业务逻辑（聊天流程、记忆、情绪、世界书、MVU…）
│   │   ├── utils/          JWT、限流、token 计数等工具
│   │   ├── config.py       环境变量配置
│   │   └── main.py         应用入口
│   ├── alembic/            数据库迁移
│   └── tests/              后端测试
├── emiya-frontend/         Vue 3 前端
│   └── src/
│       ├── api/            接口封装
│       ├── components/     UI 组件
│       ├── views/          页面
│       ├── stores/         Pinia 状态
│       ├── composables/    组合式逻辑（CSS 注入、iframe 渲染等）
│       └── styles/         主题令牌与全局样式
├── docs/                   架构文档、ADR、调研笔记（未纳入版本库）
├── docker-compose.yml      PostgreSQL / Redis / ChromaDB
└── .env.example            环境变量示例
```

---

## 功能特点详述

### 角色卡生态（兼容 SillyTavern）

角色卡是一切的核心。你可以手动创建，也可以直接导入社区流行的 ST 角色卡——支持 PNG 内嵌与 JSON，兼容 v1/v2/v3 格式，连带卡自带的世界书、正则脚本、CSS 美化样式一并识别。导出同样回填为标准格式，可带回 ST 生态使用。围绕角色卡还有三套配套系统：

- **世界书**：按关键词触发或常驻注入设定条目，遵循 ST 风格的 position / depth 语义，支持 EJS 条件动态裁剪内容。
- **预设**：导入 ST 风格预设，控制 prompt 各段的注入顺序、开关与采样参数。
- **Prompt 模板**：可视化编辑对话 prompt 的基础骨架结构。
- **正则预设**：在 prompt 阶段与回复阶段对文本做正则后处理（隐藏标签、美化状态栏等）。

### 长期陪伴（记忆 · 情绪 · 关系）

让对话「有连续性、有温度」是 EMIYA 的立身之本：

- **记忆系统**：对话中自动提取值得记住的长期信息，分门别类存入向量库；后续对话按语义相似度 + 时间衰减检索回注，并做去重与矛盾检测。提取频率随记忆量自适应（记得少时密集、记得多时稀疏）。
- **情绪感知**：识别每轮对话的情绪标签，沉淀为可视化的情绪仪表盘与日历。
- **关系系统**：随互动积累好感度、推进关系等级，触发「第一次深聊」「连续 7 天」等里程碑。

### MVU 变量卡兼容

面向重逻辑的「游戏化」角色卡，EMIYA 兼容 MVU（Model Variable Update）体系：变量桶持久化、EJS 真 JS 求值、宏引擎、`<UpdateVariable>` 状态写回，并提供浏览器侧 MVU 运行时来渲染卡自带的可交互 UI（状态栏、面板等）。

### 渲染与前端自定义

- **富渲染**：AI 回复经 Markdown 管线渲染，自定义标签受控放行；整页 HTML 状态栏放进沙箱 iframe 隔离渲染，高度自适应。
- **主题与换肤**：内置暖色「故事纸」日/夜双主题。用户可写全站 CSS 自定义前端——以稳定的设计令牌为受支持接口，配合起手预设与 `?safe` 逃生模式，改坏了也能一键复原。角色卡自带样式与用户主题通过 CSS `@layer` 分层，互不打架。

### 输出契约

对需要稳定结构化输出的场景（如固定格式的状态栏 / 面板），提供「可见输出格式执行」能力：从注入约束、到确定性修复、到缺失片段续写等多档模式，尽量保证 AI 输出符合声明的结构。

### 账户与配置

- **认证**：注册 / 登录 / JWT 鉴权、多设备会话管理、邮箱找回密码。
- **账户设置**：昵称、头像、改密码、注销，以及记忆 / token 预算等偏好。
- **三层配置**：全局默认 → 账户级 → 单对话覆盖，多数参数可在对话内即时调整而不影响他人默认。
