# StockAI

本地优先的 A 股公告 AI 研究提醒工具。

## 当前流程

1. 选择日期，点击“抓取并初筛”。
2. 后端通过 AKShare 抓取当天公告元数据，并同步按标题和公告类型完成 AI 关注筛选。
3. 可按公告类型、关键词、“只看AI关注”过滤列表。
4. 点击“自动分析”，后台会依次分析每篇 AI 关注公告。
5. 自动分析运行时不影响查看公告；需要停止时点击“取消分析”。
6. 选择任意公告后，右侧依次显示公告基本信息、AI 分析结果、AI 对话框。

## 功能

- 抓取沪深京 A 股公告元数据，默认使用 AKShare `stock_notice_report`
- 按标题和公告类型筛出需要关注的公告
- 后台自动分析所有 AI 关注公告
- 每条公告显示分析状态：`pending`、`running`、`succeeded`、`failed`
- 分析结果包含摘要、风险点、机会点、关注信号、置信度和行动建议
- AI 对话框可以继续追问当前公告
- 数据库作为临时工作台，默认只保留最近 3 天公告，并提供清空数据库功能

## 快速开始

### 后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

后端默认使用 `data/stockai.db`。

### 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 Vite 输出的本地地址。

## 部署：Vercel 前端 + Render 后端

### Render 后端

仓库根目录已经提供 `render.yaml`。

在 Render 新建 Blueprint 或 Web Service：

- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/api/health`

建议挂载 Persistent Disk：

- Mount Path: `/var/data`
- 环境变量：`STOCKAI_DB_PATH=/var/data/stockai.db`

Render 环境变量：

```text
STOCKAI_DB_PATH=/var/data/stockai.db
CORS_ORIGINS=https://你的前端域名.vercel.app
CORS_ORIGIN_REGEX=https://.*\.vercel\.app
```

`CORS_ORIGIN_REGEX` 用于允许 Vercel Preview URL。正式上线后可以只保留 `CORS_ORIGINS`。

### Vercel 前端

在 Vercel 新建项目：

- Root Directory: `frontend`
- Framework Preset: `Vite`
- Build Command: `npm run build`
- Output Directory: `dist`

Vercel 环境变量：

```text
VITE_API_BASE_URL=https://你的-render后端.onrender.com
```

部署后，回到 Render 更新 `CORS_ORIGINS` 为真实 Vercel 域名。

### 客户测试注意

当前项目没有登录系统。给客户测试时，建议先使用 Vercel/Render 的访问保护，或只把链接发给可信客户。多个客户同时测试前，应先增加账号和数据隔离。

## 模型配置

支持三种 provider：

- `mock`：本地测试用，不调用外部 API
- `openai`：使用 OpenAI API
- `openai-compatible`：使用兼容 OpenAI Chat Completions 的接口，例如本地 Ollama

API key 只保存在本地 SQLite 数据库，不提交到仓库。

### Ollama 示例

```powershell
ollama pull qwen2.5:7b
ollama serve
```

然后在网页“设置”里填写：

- Provider: `OpenAI-compatible`
- Model: `qwen2.5:7b`
- Base URL: `http://127.0.0.1:11434/v1`
- API Key: `ollama`

## 分析说明

初筛只读取公告标题、公告类型和关键词规则，不下载正文、不调用大模型，所以应该很快完成。

自动分析只处理 AI 关注公告。分析时会尝试抓取公告正文或 PDF 文本，再调用模型生成结构化结果。行动建议会给出“继续关注”或“不需要继续关注”的结论，但不会输出买入、卖出等交易指令。

## 数据库策略

数据库只作为临时工作台：

- 启动后默认只保留最近 3 天公告
- 删除公告时会级联删除对应分析结果和对话记录
- 网页提供清理动作：删除未关注、清原文、删 3 天前、清空库

## 免责声明

本项目输出仅用于个人研究提醒，不构成投资建议。
