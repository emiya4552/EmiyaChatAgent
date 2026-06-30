# EMIYA / charAgent

EMIYA 是一个面向角色卡聊天、世界书、记忆、情绪关系和 Prompt 模板编排的 AI Chat 项目。

项目采用前后端分离架构：

- 后端：FastAPI + SQLAlchemy Async + LangGraph + PostgreSQL + Redis + ChromaDB
- 前端：Vue 3 + Pinia + Naive UI + Vite
- LLM：当前以 DeepSeek API 为主要调用目标

核心目标是让用户导入或创建 AI 角色卡，并围绕角色卡进行长期对话。系统支持对话记忆、情绪记录、关系等级、世界书注入、ST 风格预设、正则后处理、Prompt 模板、CSS 主题，以及部分 MVU / Tavern 系角色卡兼容能力。

---

## 功能概览

- 用户注册、登录、JWT 鉴权
- AI 角色卡管理
- 用户人设管理
- PNG 角色卡导入 / 导出
- 对话创建、删除、消息流式生成
- SSE 流式回复与 live 旁观流
- 长期记忆提取与 ChromaDB 语义检索
- 情绪识别、情绪仪表盘
- 好感度 / 关系等级系统
- 世界书管理、导入、导出、绑定与激活
- Author's Note 注入
- ST 预设导入、绑定与 prompt 注入
- 正则预设导入与 prompt / reply 阶段处理
- Prompt 模板编辑器
- 账户设置、头像上传、改密码、注销
- 前端 Markdown / HTML iframe 渲染
- 用户级与角色级 CSS 主题注入
- MVU 兼容基础能力：变量桶、EJS 条件、MacroEngine、`<UpdateVariable>` 基础解析

---

## 目录结构

```text
charAgent/
├── emiya-backend/          FastAPI 后端
│   ├── app/
│   │   ├── api/            HTTP API 路由
│   │   ├── models/         SQLAlchemy ORM
│   │   ├── schemas/        Pydantic 请求 / 响应模型
│   │   ├── services/       业务逻辑
│   │   ├── utils/          JWT、异常、限流、token 工具
│   │   ├── config.py       配置读取
│   │   ├── database.py     数据库连接
│   │   └── main.py         FastAPI 入口
│   ├── alembic/            数据库迁移
│   ├── scripts/            开发脚本
│   ├── tests/              后端测试
│   └── requirements.txt
├── emiya-frontend/         Vue 3 前端
│   ├── src/
│   │   ├── api/            axios API 封装
│   │   ├── components/     UI 组件
│   │   ├── stores/         Pinia 状态
│   │   ├── views/          页面
│   │   ├── router/         路由
│   │   ├── utils/          Markdown、头像、正则等工具
│   │   └── types/          TypeScript 类型
│   └── package.json
├── docs/                   架构文档、ADR、调研笔记
├── docker-compose.yml      PostgreSQL / Redis / ChromaDB
├── .env.example            环境变量示例
└── README.md
```

---

## 环境要求

- Python 3.11+
- Node.js 20+
- Docker / Docker Compose
- Git

建议使用虚拟环境管理 Python 依赖。

---

## 快速启动

### 1. 启动基础服务

在项目根目录运行：

```bash
docker compose up -d
```

这会启动：

- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- ChromaDB: `localhost:8001`

### 2. 配置环境变量

复制环境变量示例：

```bash
cp .env.example .env
```

根据本地情况修改 `.env`：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

DATABASE_URL=postgresql+asyncpg://emiya:emiya_dev_2026@localhost:5432/emiya
REDIS_URL=redis://localhost:6379/0

JWT_SECRET_KEY=your_jwt_secret_key_here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
```

不要把真实 `.env` 提交到 Git。

### 3. 启动后端

进入后端目录：

```bash
cd emiya-backend
```

创建并激活虚拟环境后安装依赖：

```bash
pip install -r requirements.txt
```

执行数据库迁移：

```bash
alembic upgrade head
```

启动后端：

```bash
uvicorn app.main:app --reload --port 8000
```

健康检查：

```text
http://localhost:8000/health
```

### 4. 启动前端

进入前端目录：

```bash
cd emiya-frontend
```

安装依赖：

```bash
npm install
```

启动开发服务器：

```bash
npm run dev
```

默认访问：

```text
http://localhost:5173
```

---

## 常用开发命令

后端测试：

```bash
cd emiya-backend
pytest
```

前端构建：

```bash
cd emiya-frontend
npm run build
```

前端测试：

```bash
cd emiya-frontend
npm run test
```

数据库迁移：

```bash
cd emiya-backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

---

## 关键模块

### 聊天主流程

核心文件：

- `emiya-backend/app/api/chat.py`
- `emiya-backend/app/services/chat_service.py`
- `emiya-backend/app/services/langgraph/chat_graph.py`
- `emiya-backend/app/services/langgraph/nodes.py`
- `emiya-frontend/src/api/chat.ts`
- `emiya-frontend/src/stores/chat.ts`

大致流程：

```text
前端发送消息
→ 后端保存 user message
→ LangGraph 执行情绪 / 记忆 / 世界书 / 画像 / 关系 / Prompt 组装
→ DeepSeek 流式生成
→ assistant 文本后处理
→ 保存 assistant message
→ SSE 推送 message_done
```

### 世界书

核心文件：

- `emiya-backend/app/services/worldbook/scanner.py`
- `emiya-backend/app/services/worldbook/injector.py`
- `emiya-backend/app/services/worldbook/import_export.py`
- `emiya-backend/app/api/worldbooks.py`
- `emiya-frontend/src/views/WorldbookManageView.vue`
- `emiya-frontend/src/views/WorldbookEditorView.vue`

世界书负责按关键词或常驻规则激活设定条目，并按 ST 风格 position 注入 Prompt。

### Prompt 模板与预设

核心文件：

- `emiya-backend/app/services/prompt_renderer.py`
- `emiya-backend/app/services/preset_injector.py`
- `emiya-backend/app/services/preset_service.py`
- `emiya-backend/app/services/template_service.py`
- `emiya-frontend/src/views/TemplateEditorView.vue`
- `emiya-frontend/src/views/PresetFormView.vue`

Prompt 模板控制基础结构，预设控制 ST 风格 prompt 注入与采样配置。

### 正则与 assistant 后处理

核心文件：

- `emiya-backend/app/services/regex_processor.py`
- `emiya-backend/app/services/message_pipeline.py`
- `emiya-backend/app/services/regex_preset_service.py`

assistant 文本后处理当前包括：

```text
MacroEngine
→ reply 阶段正则
→ MVU <UpdateVariable> 基础解析
```

### MVU 兼容

核心文件：

- `emiya-backend/app/services/ejs_engine.py`
- `emiya-backend/app/services/macro_engine.py`
- `emiya-backend/app/services/message_pipeline.py`
- `emiya-backend/app/services/persona_import_service.py`
- `emiya-backend/app/services/langgraph/nodes.py`

当前 MVU 兼容属于基础兼容，不是完整复刻 ST 的 JS 运行时。更多设计说明见：

- `docs/mvu/`
- `docs/adr/0010-mvu-compat-v0.md`
- `docs/adr/0011-mvu-compat-v1-outline.md`

---

## 版本控制建议

本项目变化较快，建议：

- `main` 保持可运行
- 每个功能开独立分支
- 每个提交只做一类事情
- 改数据库模型时同时提交 Alembic migration
- 改聊天主流程、世界书、Prompt、Memory、SSE 时同步检查 `docs/CODE-MAP.md`

推荐阅读：

- `GIT_VERSION_CONTROL.md`

---

## 不要提交的内容

以下内容不应进入 Git：

- `.env`
- `.env.local`
- API Key
- JWT Secret
- 数据库密码
- `node_modules/`
- `dist/`
- `emiya-backend/uploads/`
- `.scratch/`
- 临时测试输出

---

## 文档

重要文档：

- `docs/CODE-MAP.md`：代码导航和调用链
- `docs/adr/`：架构决策记录
- `docs/mvu/`：MVU / ST 角色卡调研
- `GIT_VERSION_CONTROL.md`：Git 与 GitHub 使用手册

如果 `docs/` 被 `.gitignore` 忽略，而你希望长期维护项目架构，建议将 `docs/CODE-MAP.md` 和 `docs/adr/` 纳入版本控制。

---

## 项目状态说明

EMIYA 当前仍处于快速迭代阶段。很多模块已经具备可用能力，但 MVU 完整兼容、脚本沙箱、小应用系统、消息级变量快照等能力仍适合继续设计和演进。

在进行大重构前，建议先写 ADR 或实现计划，再分支开发。
