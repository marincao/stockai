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

## 部署：Vercel 前端 + Railway 后端

### Railway 后端

仓库根目录已经提供：

- `Dockerfile`
- `railway.json`

在 Railway 新建服务并连接 GitHub 仓库后，Railway 会使用根目录 Dockerfile 构建后端。

Railway 环境变量：

```text
STOCKAI_DB_PATH=/app/data/stockai.db
CORS_ORIGINS=https://你的前端域名.vercel.app
CORS_ORIGIN_REGEX=https://.*\.vercel\.app
OPENAI_TIMEOUT_SECONDS=60
OPENAI_MAX_RETRIES=1
```

如果使用 SQLite 保存数据，需要在 Railway 添加 Volume：

```text
Mount Path: /app/data
```

如果只是临时测试，也可以不挂 Volume，但服务重启或重新部署后 SQLite 数据可能丢失。

后端健康检查地址：

```text
/api/health
```

部署成功后，Railway 会给出类似下面的后端域名：

```text
https://your-stockai-api.up.railway.app
```

### Vercel 前端

在 Vercel 新建项目：

- Root Directory: `frontend`
- Framework Preset: `Vite`
- Build Command: `npm run build`
- Output Directory: `dist`

Vercel 环境变量：

```text
VITE_API_BASE_URL=https://你的-railway后端.up.railway.app
```

部署后，回到 Railway 更新 `CORS_ORIGINS` 为真实 Vercel 域名。

### 客户测试注意

当前项目没有登录系统。给客户测试时，建议先只发给可信客户，或启用 Vercel/Railway 的访问保护。多个客户同时测试前，应先增加账号和数据隔离。

## 模型配置

支持三种 provider：

- `mock`：本地测试用，不调用外部 API
- `openai`：使用 OpenAI API
- `openai-compatible`：使用兼容 OpenAI Chat Completions 的接口，例如本地 Ollama

API key 只保存在 SQLite 数据库，不提交到仓库。部署到 Railway 后，如果没有挂 Volume，API key 配置也可能随重启丢失。

### OpenAI API

客户测试推荐使用 OpenAI API：

```text
Provider: OpenAI API
Model: gpt-4.1-mini
Base URL: 留空
API Key: sk-...
```

### Ollama 示例

本地开发时可用 Ollama：

```powershell
ollama pull qwen2.5:7b
ollama serve
```

然后在网页“模型”里填写：

- Provider: `OpenAI-compatible`
- Model: `qwen2.5:7b`
- Base URL: `http://127.0.0.1:11434/v1`
- API Key: `ollama`

云端部署后，`127.0.0.1` 指的是云服务器，不是你的电脑。因此客户测试建议使用 OpenAI API。

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
