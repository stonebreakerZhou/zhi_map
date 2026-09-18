# 知树

<img width="2848" height="1600" alt="image" src="https://github.com/user-attachments/assets/fb3573b3-12e3-4767-84a1-4a013cdc4f8d" />

知树是一个自托管学习工作台：从消息中的精确选区展开独立讨论，保留引用快照，并把工作区保存在服务端而不是浏览器本地存储。

[English README](README.md)

## 功能

- **从精确选区展开讨论。** 框选单条消息中的文字，选区附近出现“展开讨论”和“复制”。预览原文、选择截至选区末尾的背景，再填写追问；整条消息分叉也先进入预览，不会直接创建空讨论。
- **安静的对话流。** 每轮消息保留一行紧凑操作：复制、选择原文、从这里展开、回答未完成时重新生成、移除整条讨论；hover 或键盘焦点时出现。只有你自己的发言画成气泡并按文字收缩，回答与页面同色、按长文排版阅读。
- **整理与恢复主题。** 新建主题，按标题或标签搜索，重命名、收藏或移除。移除使用独立的十分钟服务端收据，无关草稿与问答不会使恢复失效；删除整个会话主线是单独的、不可撤销的确认。
- **联系旧知识并返回原文。** 明确选择其他主题的消息或片段加入引用快照，并随时回到原始阅读位置。主题与消息按页加载，不会一次下载整个工作区。
- **阅读排版后的回答。** 回复按 Markdown 渲染，公式由 KaTeX 排版——行内 `$...$` 或 `\(...\)`，独立成行 `$$...$$` 或 `\[...\]`，流式生成过程中同样即时渲染。公式选不中时，可在该条消息切换到“选择原文”后再框选。
- **两种视图。** 极简对话视图，以及按需进入的知识图谱视图：进入时把当前主题与直接子节点收进画面；未打开的主题只是一张写着标题与摘录的小卡片，点击打开后才展开成带正文与输入框的阅读胶囊。

## 开始使用

需要 Node.js 22.12+、npm 与 Python 3.12+。项目内置 SQLite，无需 Docker 或外部数据库。

命令均在仓库根目录执行。Python 命令使用 Windows 启动器 `py`；macOS/Linux 请替换为 `python3`。

```sh
npm install
py -m pip install -e "backend[test]"
cp .env.example .env          # Windows CMD：copy .env.example .env
py -m alembic -c backend/alembic.ini upgrade head
py -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

保持它运行，在第二个终端启动 Vite：

```sh
npm run dev:web
```

打开 `http://127.0.0.1:5173`。Vite 会把 API 请求代理到 `8000` 端口的 FastAPI。

部署单进程自托管版本时，先构建前端、执行迁移，再启动 FastAPI：

```sh
npm run build
py -m alembic -c backend/alembic.ini upgrade head
py -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

对外部署前，请设置 `APP_ENV=production`、持久化的 `DATABASE_URL` 和 `DATA_ENCRYPTION_KEY`。

## 设置模型

可以在 `.env` 设置 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL`、`AI_PROVIDER`（`openai`、`anthropic`、`gemini`）与可选的 `AI_TIMEOUT_MS`；也可以完全在应用内的设置中心完成：先选服务商，再填写地址、模型名称与 API key。

预设模型名只是填写示例，不是实时可用模型列表。**“保存并测试”会先保存表单，再发送简短请求**，并区分保存失败与连接失败。修改协议或地址需要提供对应连接的密钥。清除个人配置需要确认，清除后回退到服务器默认配置（若有）。

DeepSeek、Qwen、OpenRouter 是 OpenAI 协议地址预设，未逐家验证。测试使用不同协议的本地模拟服务，尚未用真实厂商账号验证。密钥只提交给同源 API，不包含在读取接口和导出文件中。

生产环境若要保存会话模型凭据，必须设置 `DATA_ENCRYPTION_KEY`（32 字节密钥的 base64，可用 `npm run keys:generate` 生成）。开发环境未设置时会生成只在当前进程有效的临时密钥，重启后已保存凭据无法读取。`AI_ALLOWED_HOSTS` 可限制可配置的模型服务主机名。

历史导入导出使用 NDJSON（单条 ≤ 1 MiB，文件 ≤ 2 GiB），旧 JSON 请求限制为 8 MiB。启动自动执行 Alembic 升级，原工作区 JSON 保留为迁移时备份。迁移较大工作区前请阅读[架构与当前扩展限制](docs/architecture.zh-CN.md)，其中也包含 `AI_ALLOW_PRIVATE_HOSTS`、`AI_FAKE_IP_HOSTS` 等私有地址与代理设置。

## Windows 桌面版

运行 `desktop\build.ps1` 构建便携包；具备 Inno Setup 6.3+ 时还会构建安装器。产物位于 `desktop\dist\`：

- **`Zhishu-Setup-windows-x64.exe`**（推荐）——双击安装，自动处理 WebView2 Runtime 和快捷方式，按用户安装、不需要管理员权限
- **`Zhishu-windows-x64.zip`**——便携版，解压后运行 `Zhishu\Zhishu.exe`，需保留 `_internal` 整个文件夹

两种形式都自带 Python 与全部依赖。数据统一存在 `%LOCALAPPDATA%\Zhishu`，卸载不会删除。程序需要 x64 Windows 10/11。构建细节与已知限制（尚未代码签名）见[桌面宿主文档](desktop/README.md)。

## 当前状态

图谱视图可用但尚未完成：进入概览时会把当前主题与直接子节点收进画面，但底层布局仍是插入顺序网格，而非层级星空树；完整子树展开、空间碰撞聚合、外框连续变形、访问历史与镜头往返、原生 WebView2／Windows 缩放验证仍有缺项。浏览器证据在 `test-results/`；Headless RAF 采样不代表已实测桌面 60fps。

## 验证

```sh
npm test              # 后端 pytest
npm run typecheck
npm run build
npm run test:browser  # 构建前端、以临时 SQLite 启动 FastAPI 并驱动 Chrome
```

需要安装 Chrome，或将 `CHROME_PATH` 指向 Chrome/Chromium 可执行文件。浏览器测试覆盖对话流程、设置失败恢复、未保存修改、主题操作、鼠标与键盘选区、窄屏布局和图谱视图；截图输出到 `test-results/`。窄屏浏览器验证不能替代真机移动端测试。没有 `py` 启动器时，可直接执行 `python3 -m pytest backend/tests -q` 和 `python3 backend/tests/browser_smoke.py`。

## 延伸阅读

- [迭代规范](docs/standards/README.md)
- [架构](docs/architecture.zh-CN.md)
- [Python 后端](backend/README.md)
- [Web 客户端](apps/web/README.md)
- [Windows 桌面宿主](desktop/README.md)
