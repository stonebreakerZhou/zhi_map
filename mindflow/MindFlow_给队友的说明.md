# MindFlow 给队友的说明

> 作者：小学期 Python 程序与设计项目组
> 日期：2026-09-13
> 适用版本：MindFlow v0.1.0
> 面向：zhi_map 协作仓库的队友（Sean 等）
> 目的：把 MindFlow 桌面端两版作为"独立 demo + 接口示例"贡献到 zhi_map 仓库，
>       方便队友**先看说明**再读源码，能快速对接 / 测试 / 修改。

---

## 1. 一句话总结

| 目录 | 一句话 |
|---|---|
| `final_project/` | **可独立运行的 MindFlow 桌面端**（PySide6 + SQLite，一键启动） |
| `final_project_integrate/` | **接口化的 MindFlow**（同样的 UI，把"硬编码部分"换成 4 个 Protocol，靠 DI 容器装配 Mock 或 HTTP 实现） |

这两个目录**底层数据层共享**（`mindmap_repo.py` 的接口和 SQLAlchemy 模型完全一致），
**UI 层同步**（每次修改 Track 1 时会同步到 Track 2，详见 §3.5），区别只在中间层：
Track 1 直接调 `mindmap_repo.*`，Track 2 走 `Container → IMindMapStorage → SQLiteStorage` 抽象。

**演示数据**：两个 DB 默认都只塞一份 `期末复习计划`（28 节点，
高数 / 概统 / Python 三科各 8 个子节点），队友打开就能看到完整样例。

---

## 2. 为什么分两轨？

写代码时遇到一个矛盾：

- **作为"独立 demo"**：要简单，能 `python -m src.app` 直接起来，不能有"先装 FastAPI 才能跑"的依赖
- **作为"接口示例"**：要让队友能直接换掉任意一层（Mock ↔ HTTP / SQLite ↔ JSON）而不动 UI 代码

> **一句话原则**：**Track 1 满足"跑得起来"，Track 2 满足"换得了"。**

所以同一个 UI 层被复制了两份（通过 `diff -q` 保持 byte-identical），底层数据层完全复用，
中间层（DI / 服务）只在 Track 2 存在。

---

## 3. Track 1 — `final_project/`（独立版）

### 3.1 设计目标

> **最少依赖 / 最多功能**：不装 FastAPI、不连后端、不读环境变量，
> `python -m src.app` 直接起。

### 3.2 技术栈

| 层 | 选型 | 备注 |
|---|---|---|
| GUI | PySide6 (Qt 6.5+) | QGraphicsView 画布 + QGraphicsScene 节点 |
| 数据 | SQLite + SQLAlchemy 2.0 | 单文件 `data/mindflow.db` |
| AI 搜索 | duckduckgo-search + wikipedia | 节点右键 → 自动联想子主题 |
| 报告 | python-docx + python-pptx | 导出 Word / PPT |
| 打包 | PyInstaller | `mindflow.spec` |

### 3.3 启动

```bash
cd final_project
pip install -r requirements.txt
python -m src.app
```

界面起来后会自动打开「期末复习计划」导图（28 节点样例）。

### 3.4 目录结构与文件清单

```
final_project/
├── data/                    # SQLite + 用户附件（gitignore *.db，但 demo DB 一并 ship）
│   ├── mindflow.db          # 「期末复习计划」28 节点 demo（ship 给队友）
│   ├── images/              # 用户上传的图片（gitignore）
│   ├── documents/           # 用户上传的 Markdown 文档（gitignore）
│   └── attachments/         # 多附件（gitignore）
├── src/                    # ⭐ Track 1 源码
│   ├── app.py               # ⭐ 入口（python -m src.app）
│   ├── config.py            # 应用配置（窗口大小/默认色/字体）
│   ├── mindmap/             # 与 Track 2 共享（graph.py / node.py）
│   ├── storage/             # 与 Track 2 共享（mindmap_repo / db / schema）
│   ├── integrations/        # 与 Track 2 共享（zhi_map 导入桥）
│   │   └── zhishu/
│   │       ├── converter.py # workspace state → MindMap 节点
│   │       ├── importer.py  # 一键导入（含对话消息 → 节点）
│   │       ├── loader.py    # 读 /api/export JSON
│   │       └── _domain/     # 内嵌 workspace domain 子集（避免依赖队友内部包）
│   ├── ui/                  # 与 Track 2 byte-identical
│   │   ├── main_window.py   # ⭐ 主窗口
│   │   ├── mindmap_view.py  # ⭐ 画布（双模式 BROWSE / EDIT）
│   │   ├── node_item.py     # 节点图形
│   │   ├── edge_item.py     # 连线（树形边 + 附加边）
│   │   ├── note_editor.py   # 右侧 Markdown 编辑器
│   │   ├── attachment_panel.py
│   │   ├── history.py       # 撤销 / 重做（snapshot 隔离）
│   │   ├── theme.py         # ⭐ QSS / 字体 / 设计 token
│   │   └── effects/         # 星空背景 + 星云粒子
│   ├── tools/               # CLI 工具
│   │   └── import_zhishu.py # CLI 导入 zhi_map export 文件
│   └── utils/
│       ├── exporter.py      # Word / PPT 导出
│       └── logger.py        # 日志（按日期切分）
├── tests/                   # ⭐ 单元测试（pytest，24 个文件，覆盖 cut/undo/export/gui）
├── tools/                   # demo 数据生成（项目根级）
│   ├── rebuild_kaoshi_mindmap.py   # ⭐ 重建「期末复习计划」28 节点样例
│   ├── verify_kaoshi_mindmap.py    # 结构验证
│   └── setup_demo_mindmap.py       # 旧版 4 分支 demo（含图片/边演示，备选）
├── requirements.txt
├── build_exe.bat            # PyInstaller 打包脚本
├── run.py                   # Windows / 通用启动脚本
└── .gitignore
```

### 3.5 与 Track 2 的同步策略

`final_project/src/ui/` 和 `final_project_integrate/src/ui/` 必须**byte-identical**。
开发期改 UI → 同步脚本拷过去；打包前 `diff -rq` 检查（详见 §7.2）。

---

## 4. Track 2 — `final_project_integrate/`（接口版）

### 4.1 设计目标

> **零侵入换实现**：在不修改 UI 代码的前提下，能在以下三类后端间切换：
> 1. Mock（内存，无网络，演示用）
> 2. 本地 SQLite（`mindmap_repo.py`，与 Track 1 共享）
> 3. 队友 zhi_map FastAPI（HTTP，schemaVersion=2 兼容）

### 4.2 架构图

```
+--------------------+        +--------------------------+
|     UI 层          |  →     |      统一门面 (api)        |
|  (main_window.py)  |        |  MindFlowAPI             |
+--------------------+        +--------------------------+
                                      ↓
                         +--------------------------+
                         |  Container (DI 单例)      |
                         |  - chat_backend          |
                         |  - ai_provider           |
                         |  - storage               |
                         +--------------------------+
                              ↓         ↓         ↓
                +--------------+  +-------+  +-----------------+
                | IChatBackend |  |IAIProv|  |IMindMapStorage  |
                +--------------+  +-------+  +-----------------+
                    ↑      ↑           ↑           ↑
                    |      |           |           |
            MockChatBackend  |    MockProvider   SQLiteStorage
            ZhishuHttpChatBackend                 (包装 mindmap_repo)
            (HTTP → zhi_map FastAPI)

                         ↓
              +--------------------------+
              |       服务层              |
              |  ChatService             |
              |  MindMapService          |
              |  OrganizationService     |
              +--------------------------+
```

### 4.3 四个核心 Protocol

> 定义在 `final_project_integrate/src/core/interfaces/`

| 接口 | 文件 | 实现 | 用途 |
|---|---|---|---|
| `IChatBackend` | `chat.py` | `MockChatBackend` / `ZhishuHttpChatBackend` | 对话状态机（创建 / 切换 / 提问 / AI 答 / fork / expand） |
| `IAIProvider` | `ai.py` | `MockProvider`（Anthropic / OpenAI 占位） | 聊天补全 + 要点抽取 + 候选 rerank |
| `IMindMapStorage` | `storage.py` | `SQLiteStorage` | MindMap / Node / Edge CRUD |
| `IOrganizationService` | `organization.py` | `OrganizationService`（默认） | 把对话整理成 MindMap 节点 |

所有接口都是 `typing.Protocol`，**不需要继承**——只要 duck-type 满足方法签名即可。

### 4.4 Container 装配

> `final_project_integrate/src/core/container.py`

```python
# 单例懒加载
def api() -> MindFlowAPI: ...

# 选择 backend（环境变量）
MINDFLOW_CHAT_BACKEND=http   MINDFLOW_ZHI_MAP_URL=http://127.0.0.1:8000
MINDFLOW_CHAT_BACKEND=mock   # 默认
```

启动时 `app.py` 立即调 `api()` 一次，确保 DI 单例就绪（即便 UI 层绕过 service，
HTTP backend 也会被探测 / 失败也尽早暴露）。

### 4.5 MindFlowAPI 统一门面

> `final_project_integrate/src/core/api.py`（新增）

新写的代码（导入器、脚本、插件、测试）应该只用 `MindFlowAPI`：

```python
from src.core.api import api

a = api()
a.storage.create_mindmap("复习计划")
a.organize_service.organize(conversation)
a.chat.send(branch_id, "你好")
a.close()
```

便利方法 `create_mindmap_with_nodes(title, nodes, description)` 支持一次创建 MindMap + 树形节点集。

### 4.6 启动

#### 离线模式（默认）

```bash
cd final_project_integrate
pip install -r requirements.txt
python -m src.app
```

走 `MockChatBackend` + `MockProvider` + `SQLiteStorage`，零网络也能跑全套 UI。

#### 接 zhi_map FastAPI 模式

```bash
# 终端 1：起队友 zhi_map 后端
cd zhi_map/backend
py -m alembic -c backend/alembic.ini upgrade head
py -m uvicorn app.main:app --app-dir backend --port 8000

# 终端 2：起 MindFlow 并切 HTTP backend
cd final_project_integrate
MINDFLOW_CHAT_BACKEND=http MINDFLOW_ZHI_MAP_URL=http://127.0.0.1:8000 \
  python -m src.app
```

切换后 `ZhishuHttpChatBackend` 接管所有 `IChatBackend` 调用：
- `GET /api/workspace` → 加载 state
- `POST /api/workspace/actions` → 提交 action（自带乐观锁 revision）
- `POST /api/ai/chat` → 让队友后端调 LLM
- 409 Conflict → 自动重试 / 友好提示

### 4.7 目录结构

```
final_project_integrate/
├── data/                    # SQLite + 用户附件（与 Track 1 同结构）
├── src/                     # ⭐ Track 2 源码（=Track 1 + DI 层 + HTTP backend + ai_search）
│   ├── app.py               # ⭐ 入口（启动时自动调 api() 初始化 Container）
│   ├── config.py
│   ├── mindmap/             # 与 Track 1 共享
│   ├── storage/             # 与 Track 1 共享
│   ├── integrations/        # 与 Track 1 共享（zhi_map 导入桥）
│   │   └── zhishu/...
│   ├── ai_search/           # Track 2 多出来的搜索增强
│   │   └── node_suggester.py # 给节点搜候选关键词（骨架）
│   ├── core/                # ⭐ Track 2 独有的 DI 层
│   │   ├── container.py         # 装配 + 单例（环境变量切 backend）
│   │   ├── api.py               # ⭐ 统一门面（MindFlowAPI）
│   │   ├── interfaces/          # 4 个 Protocol
│   │   │   ├── chat.py          # IChatBackend
│   │   │   ├── ai.py            # IAIProvider
│   │   │   ├── storage.py       # IMindMapStorage
│   │   │   └── organization.py  # IOrganizationService
│   │   └── services/            # 业务包装
│   │       ├── chat_service.py
│   │       ├── mindmap_service.py
│   │       └── organization_service.py
│   ├── backends/            # ⭐ 接口实现（任一可换）
│   │   ├── mock_chat_backend.py            # 默认（无网络）
│   │   ├── mock_provider.py                # 占位 LLM
│   │   ├── sqlite_storage.py               # 包装 mindmap_repo
│   │   └── zhishu_http_chat_backend.py     # ⭐ HTTP → zhi_map FastAPI
│   ├── ui/                  # 与 Track 1 byte-identical
│   ├── tools/
│   │   └── import_zhishu.py # CLI 导入 zhi_map export 文件
│   └── utils/
├── tests/                   # ⭐ DI / service / smoke 测试（~25 个文件）
├── tools/                   # demo 数据生成（与 Track 1 共享 rsync）
│   ├── rebuild_kaoshi_mindmap.py
│   ├── verify_kaoshi_mindmap.py
│   └── setup_demo_mindmap.py
├── requirements.txt         # 比 Track 1 多 `httpx>=0.25`（给 HTTP backend）
├── build_exe.bat            # PyInstaller 打包脚本
├── run.py                   # 启动脚本
└── .gitignore
```

---

## 5. 与 zhi_map 集成方案（核心问题）

### 5.1 现状：两套数据模型

> 队友的 zhi_map 和我的 MindFlow 是**互补关系**，不是替代关系。

| | zhi_map（队友） | MindFlow（我的） |
|---|---|---|
| 核心对象 | sessions + branches（对话） | MindMap + nodes（导图） |
| 数据形态 | 流式对话（user / assistant / reference） | 树形结构（每个节点一个主题） |
| 状态 schema | `{version:2, sessions, branches, active}` | `MindMap{root_node_id} + Node{parent_id}` |
| AI 用途 | 回答对话 | 搜索节点关键词 |
| 后端 | FastAPI + SQLite（HTTP） | SQLite（本地）/ FastAPI（HTTP） |

**MindFlow 不会"成为 zhi_map"**。它解决的是 zhi_map 没解决的问题：
> "我想把聊天里学到的内容整理成树状笔记，配图、配附件、配可视化。"

### 5.2 三种集成路径（按侵入度排序）

#### 路径 A：HTTP 后端（已实现，最快）

> MindFlow 通过 HTTP 调队友 FastAPI，**数据不动**，只在 Track 2 切换 `chat_backend`。

```
MindFlow UI ──► ZhishuHttpChatBackend ──HTTP──► zhi_map FastAPI
                              │
                              └─ 直接用队友的 workspace state / AI / 流式回答
```

- ✅ 完全不动队友代码
- ✅ 队友跑 FastAPI 即可联调
- ⚠️ MindFlow UI 当前主要消费 SQLiteStorage；ChatService 当前是预留接入位
  （**未来 PR** 把 ChatService 接进 main_window 的对话面板，UI 就能真用上队友的对话能力）

**接入方式**：
```bash
MINDFLOW_CHAT_BACKEND=http MINDFLOW_ZHI_MAP_URL=http://127.0.0.1:8000
```

#### 路径 B：导入桥（已实现，演示用）

> 把队友 `/api/export` 导出的 workspace state 转成 MindMap 节点树，**单向**。

```
zhi_map /api/export ──► JSON ──► tools/import_zhishu.py ──► MindFlow SQLite
```

代码：`final_project_integrate/src/integrations/zhishu/converter.py`
- 把 zhi_map `sessions/branches/entries` 递归压平成 MindMap 节点
- `user` 节点 + `assistant` 节点 + `tags` + `branch 标题`
- 一键 `python tools/import_zhishu.py <export.json>` 即可

**使用方法**：
```bash
# 1. 队友导出（curl 也行，UI 里有导出按钮）
curl http://127.0.0.1:8000/api/export > workspace.json

# 2. 在 MindFlow 这边导入
cd final_project_integrate
python -m src.tools.import_zhishu workspace.json
#  → 在 MindFlow 里多了一个 MindMap，标题 = 第一个 session 的标题
```

#### 路径 C：双向同步（**未来 PR**，需要和队友对齐）

> MindFlow 节点 ↔ zhi_map session/branch（带冲突解决）。

- 需要队友在 `Repository.action` 加新 action 类型 `mindmap_sync`
- MindFlow 用 `IChatBackend` 的 `apply_action` 把节点增删改提交给 zhi_map
- 冲突解决：双方都有 revision（HTTP 409 → reload → 重试）

> ⚠️ **这一步需要和队友讨论 schema**，不能擅自改 zhi_map。
> 我已经把 `MindMapSyncService` 接口预留（`core/services/mindmap_sync_service.py`），
> 实现留空，等对齐后填。

### 5.3 schemaVersion=2 兼容

zhi_map 的 workspace state 用 `version: 2` 标识。我让：
- `MockChatBackend` 直接构造 `version: 2` 的空 state（`backend/app/domain/workspace.py::empty_state()` 一致）
- `ZhishuHttpChatBackend` 完全用队友的 schema（不做任何字段映射）
- 内嵌在 `integrations/zhishu/_domain/workspace.py` 是从队友 copy 来的子集（仅 `transition()` + `validate_state()`），
  保证离线时也能校验导入文件

**对齐点**（已确认）：
| 字段 | zhi_map | MindFlow |
|---|---|---|
| 顶层 `version` | 必须 2 | 导入时强校验 |
| `branches[i].id` | UUID str | 直接做 MindMap 节点 id |
| `branches[i].title` | str | 节点 `text` |
| `entries[i].role` | `user` / `assistant` / `reference` | 节点 `note`（拼接） |
| `branches[i].tags` | `list[str]` | 节点 `note` 末尾追加 |
| 节点定位 | 无（对话是 1D 流） | `pos_x/pos_y`（自动扇形分布） |

---

## 6. 设计 token / 视觉规范

> 全部集中在 `final_project/src/ui/theme.py`

| token | 值 | 用途 |
|---|---|---|
| `COLOR_ROOT` | `#22d3ee` | MindMap 根节点（cyan 主调） |
| `COLOR_MATH` | `#f59e0b` | 高数（琥珀） |
| `COLOR_STAT` | `#a78bfa` | 概统（紫） |
| `COLOR_PY` | `#10b981` | Python（翠绿） |
| `FONT_FAMILY` | `'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace` | 等宽，深色 IDE 风 |
| 背景 | `#0F1419`（深空蓝黑） | 与星空主题统一 |

**风格对齐**：参考了 project-graph（队友的另一个项目）深色 IDE 风格。
所有节点圆角、连线粒子、删除效果都基于这套 token 派生。

---

## 7. 测试 / 演示数据

### 7.1 演示 MindMap

两轨 DB 默认只有 `期末复习计划`（28 节点）：

```
期末复习计划 (root, #22d3ee)
├── 高等数学 (#f59e0b)
│   ├── 函数与极限
│   ├── 极限的四则运算
│   ├── 两个重要极限
│   ├── ε-δ 定义
│   ├── 函数的连续性
│   ├── 导数概念与几何意义
│   ├── 微分中值定理
│   └── 泰勒公式
├── 概率统计 (#a78bfa)
│   ├── 随机事件与样本空间
│   ├── 古典概型
│   ├── 条件概率与独立性
│   ├── 随机变量分布
│   ├── 常见分布（二项/泊松/正态）
│   ├── 大数定律与中心极限定理
│   ├── 参数估计
│   └── 假设检验
└── Python (#10b981)
    ├── 基础语法与控制流
    ├── 列表 / 字典 / 集合
    ├── 函数与 lambda
    ├── 面向对象（类 / 继承）
    ├── 异常处理
    ├── 文件 I/O 与路径
    ├── 常用标准库（os / json / collections）
    └── 综合实战：爬虫 + 报告生成
```

**重新生成**：
```bash
# 两轨都写
python final_project/tools/rebuild_kaoshi_mindmap.py
python final_project_integrate/tools/rebuild_kaoshi_mindmap.py
```

> 脚本是幂等的：先清掉所有其他 mindmap，再写入新样例。

### 7.2 双轨一致性自检

```bash
diff -rq final_project/src/ui final_project_integrate/src/ui
# 期望：无输出（byte-identical）
```

### 7.3 单元测试

```bash
cd final_project && pytest tests/ -v
cd final_project_integrate && pytest tests/ -v
```

> 部分测试因 Qt GUI 依赖可能需要 `xvfb-run`（Linux）或跳过。

### 7.4 烟雾测试

```bash
# Track 1
python -m src.app
# 应该看到：MindFlow v0.1.0 → 打开 期末复习计划 (28 nodes)

# Track 2（DI 容器在启动时初始化）
MINDFLOW_CHAT_BACKEND=mock python -m src.app
# 应该看到：DI 容器就绪：chat=MockChatBackend, ai=MockProvider, storage=SQLiteStorage

# Track 2（接 zhi_map）
MINDFLOW_CHAT_BACKEND=http MINDFLOW_ZHI_MAP_URL=http://127.0.0.1:8000 python -m src.app
# 应该看到：ChatBackend: ZhishuHttpChatBackend (http://127.0.0.1:8000)
```

---

## 8. 已知差异 / 限制（请队友知悉）

| 局限 | 现状 | 后续 |
|---|---|---|
| Track 2 UI 仍直接调 `mindmap_repo` | 38 处直接调用 | 后续 PR 把 `MindMapService` 接进 `main_window`（保留两条调用路径，不强删旧代码） |
| `ChatService` 未接到 UI 面板 | IChatBackend 已实现，UI 调用位预留 | UI 加"对话面板"后即生效 |
| AI 搜索是骨架 | `node_suggester.py` 只返回本地规则建议 | 接 `IAIProvider.complete_chat()` 即可换 LLM |
| `MindMapSyncService` 是 stub | 接口已定义 | 等和队友对齐 zhi_map `Repository.action` 新 action 类型 |
| `IOrganizationService` 朴素布局 | 同根扇形分布 | 加 LLM 自动归类后会更聪明 |

---

## 9. 我希望队友帮我看什么 / 接什么

按优先级：

1. **优先 — 看 DI 层是否对齐你们的设计**
   - `final_project_integrate/src/core/interfaces/*.py`（4 个 Protocol）
   - `final_project_integrate/src/core/container.py`
   - `final_project_integrate/src/backends/zhishu_http_chat_backend.py`（HTTP 调 FastAPI 的实现）
   - 看看**接口是否够用**？是否要加 `IMetadataBackend`（对应 `/api/ai/metadata`）等？

2. **次优 — 一起对齐 schema**
   - `integrations/zhishu/_domain/workspace.py` 是我从你们 `backend/app/domain/workspace.py` 抽的子集
   - 如果你们会加新 action 类型，告诉我，我加进 `MockChatBackend` + `ZhishuHttpChatBackend`

3. **可选 — 一起把双向同步做掉**
   - 我预留了 `MindMapSyncService`，等你们决定 `Repository.action` 加什么 action 类型

4. **已做但欢迎挑刺**
   - `rebuild_kaoshi_mindmap.py`（28 节点样例生成）
   - 双轨 `diff -rq` 自检脚本
   - MindFlowAPI 统一门面

---

## 10. 后续协作建议（PR 拆分）

| PR | 内容 | 改队友文件？ |
|---|---|---|
| **PR 1** | 加 `desktop/mindflow_standalone/`（final_project 的 rsync） | 否 |
| **PR 2** | 加 `desktop/mindflow_integrate/`（final_project_integrate 的 rsync） | 否 |
| **PR 3** | README 顶层加 `desktop/mindflow_*/` 引用 | ❓（看队友意见） |
| **PR 4** | （可选）`/api/ai/metadata` 在 MindFlow 节点右键使用 | 需要队友同意 |
| **PR 5** | （可选）双向同步 action 类型扩展 | 需要队友同意 |

**Why:** 把 MindFlow 两版作为"独立 demo + 接口示例"贡献给 zhi_map 仓库，
不动队友任何文件；UI 是 PySide6 原生桌面端，与队友已有的 `desktop/launcher.py`
（WebView2 套壳）并列而非替代。

**How to apply:** 开发期在 `final_project/` + `final_project_integrate/` 改；
交付时 `rsync` 到 `zhi_map_Sean/zhi_map/desktop/mindflow_*/`；同步规则保持
（`diff -q` 检查 + 视觉 token 一致）；任何改队友代码的 PR 都先跟队友确认。

---

## 11. 联系方式 / 反馈

请直接在本说明文件下留言（或 PR 评论），我会：
- 修 bug / 改 token：直接修在本说明 + 同步到两轨
- 接口扩展：在下一版 `INTEGRATE_给队友的说明.md` 里写"已对齐到 v0.2"

> 本文档生成于 2026-09-13，对应 MindFlow v0.1.0。
> 重大变更前会更新。

---

## 附录 A：关键文件速查

| 想看什么 | 文件 |
|---|---|
| MindFlow 整体入口 | `final_project/src/app.py` / `final_project_integrate/src/app.py` |
| 画布 | `final_project/src/ui/mindmap_view.py` |
| 主窗口 | `final_project/src/ui/main_window.py` |
| DI 容器 | `final_project_integrate/src/core/container.py` |
| 4 个接口 | `final_project_integrate/src/core/interfaces/*.py` |
| HTTP backend | `final_project_integrate/src/backends/zhishu_http_chat_backend.py` |
| Mock backend | `final_project_integrate/src/backends/mock_chat_backend.py` |
| 统一门面 | `final_project_integrate/src/core/api.py` |
| zhi_map → MindMap 导入桥 | `final_project_integrate/src/integrations/zhishu/converter.py` |
| 演示数据生成 | `final_project/tools/rebuild_kaoshi_mindmap.py` |
| 设计 token | `final_project/src/ui/theme.py` |

## 附录 B：依赖差异

| 包 | Track 1 | Track 2 |
|---|---|---|
| PySide6, SQLAlchemy, duckduckgo-search, wikipedia, requests, pyinstaller, python-docx, python-pptx, Pillow, pytest, markdown | ✅ | ✅ |
| `httpx>=0.25` | — | ✅（HTTP backend 调 zhi_map FastAPI 用） |

> Track 2 多了 `httpx` 一个依赖，用于 `ZhishuHttpChatBackend`。
> 如果只跑离线模式（默认），可以不装。