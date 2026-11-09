# 课伴 CampusFlow

面向人工智能课程汇报的个人学习任务管家。应用包含任务管理、周历和项目进度。连接 DeepSeek 后，可以用自然语言查询或修改任务，也可以生成可编辑的学习计划。

## 克隆并运行

先安装 Git、Python 3.11 或更新版本、Node.js 22 或更新版本。在 GitHub 仓库的「Code」菜单复制克隆地址，运行 `git clone <仓库地址>`，再进入克隆得到的项目目录。也可以通过「Download ZIP」下载后解压。

### Windows

1. 首次运行时双击 `setup-windows.cmd`。脚本在项目目录创建 Python 虚拟环境、安装依赖、构建界面，并创建空白的 `.env` 配置。
2. 双击 `start-campusflow.cmd`，然后打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。在启动窗口按 Ctrl+C 可停止服务。

拉取更新后，可重新运行 `setup-windows.cmd`。安装脚本会保留已有的 `.env`。只修改前端时也可以直接运行 `npm.cmd run build`，然后重启服务。

### macOS 或 Linux

在项目目录运行以下命令：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm ci
npm run build
test -f .env || cp .env.example .env
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

构建成功后打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。首次运行时，在首页点击「导入演示示例」即可获得一组课程任务。

## 配置 AI 助手

每位组员都在自己电脑的项目目录编辑 `.env`。如果该文件尚未创建，先将 `.env.example` 复制为 `.env`。填入自己的 `DEEPSEEK_API_KEY`，保持 `AI_BASE_URL=https://api.deepseek.com` 和 `AI_MODEL=deepseek-flash`。保存后重启服务，在「课伴 AI」发送「查看今天有哪些待办」验证连接。[DeepSeek API 密钥创建入口](https://platform.deepseek.com/api_keys) · [工具调用文档](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)

密钥由后端读取。使用 AI 时，模型服务会收到对话和工具所需的任务信息。任务和聊天记录保存在各自本机的 `data/campusflow.db`。暂时没有密钥时，手动任务、周历和示例数据仍可使用。

## 课程演示与开发

- [课堂汇报提纲、演示指令与手工验收表](docs/课堂演示.md)
- 开发前端时可同时启动后端和 `npm run dev`。Vite 会把 `/api` 请求转发到本机 8000 端口。
- `src/` 是 React 界面，`backend/` 是 FastAPI 接口、工具调用和 SQLite 存储。
- 后端启动时如果遇到 8000 端口被占用，可以用虚拟环境的 Python 执行 `-m uvicorn backend.main:app --host 127.0.0.1 --port 8001`，再访问对应端口。

Windows 验收命令：

```powershell
npm.cmd run build
New-Item -ItemType Directory -Path '.test-output' -Force | Out-Null
$testPath = '.test-output\run-' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m pytest -q --basetemp $testPath
```

在 macOS 或 Linux 可以执行 `.venv/bin/python -m pytest -q`。测试通过模拟模型响应检查工具执行和落库。正式演示前，请使用自己的密钥跑一遍演示指令并记录实际结果。
