# 知树迭代规范

本目录是知树后续设计、开发与交付的共同约定。目标是将像素级视觉还原、可预测交互和可维护实现落实为可引用、可复核的规则。本文档参考腾讯公开设计与工程资料的组织方式，结合本仓库独立制定；不是腾讯内部外包验收规范，也不代表腾讯全公司强制标准。

## 产品方向与确认边界

- **用户已确认方向**：以极简美术呈现能联想到星空与树的原生图结构。对话时胶囊接近占满可用工作区；鼠标移出并表达探索意图时，同一画布连续缩小当前对话、显露主题邻域。内容从完整对话逐级收敛为主题与前几段原文、再到主题标题，比例可控，轮数增加不把文字越缩越小。
- **核心鼠标路径**：除文字录入外，学习、探索、整理和恢复均可用鼠标完成；长按框选后关联、拖线、右键划删与浮窗恢复是图形交付的必须项，同时提供具名按钮／菜单及键盘等价入口。
- **设计建议待验证**：Focus／Peek／Overview 状态机、主题节点粒度、单活动分支、手势阈值、占比、动效与细节预算是依据上述方向提出的实施目标，数值须实测校准。主线轮次、子节点临时预览与点击提交行为见同目录[交互规范](interaction.md) INT-016；其余行为唯一见 INT-005、INT-011～INT-015；界面值见[视觉规范](visual.md) VIS-011～VIS-014；投影与恢复契约见[编码规范](coding.md) CODE-011～CODE-012；验证见[验收规范](acceptance.md) QA-010。
- **当前实现**：原生 React 图已接入有界 SQL 投影、稳定输入、镜头按钮、框选联系、右键预览移除及独立收据恢复，菜单移除也已迁移；原有消息／选区／引用／模型流程通过浏览器回归。完整层级布局、胶囊外框连续变形、碰撞聚合与原生桌面矩阵仍未完成，不能按 QA-010 整体放行。历史 MindFlow 演示不是本次实现。

本目录五份文件是唯一权威规范，直接在对应条目维护目标，不另设覆盖版或重定向。现有规则 ID 保持稳定，仅新增 CODE-012 承载手势与逐操作恢复契约；学习、设置、草稿保护和模型流规则继续适用。同画布空间骨架按 VIS-012，胶囊正文排版及普通阅读布局按 VIS-005。

## 阅读导航与唯一责任

| 文档 | 主要读者 | 唯一负责的内容 |
| --- | --- | --- |
| 本页 | 所有人 | 适用范围、等级、现状差距、来源与落地顺序 |
| [视觉规范](visual.md) | 设计、前端、视觉验收 | 所有界面尺寸、字体、颜色、布局、组件度量、层级与动效 token |
| [交互规范](interaction.md) | 产品、前端、后端、测试 | 用户操作、状态转换、反馈、取消与恢复语义 |
| [编码规范](coding.md) | 开发、代码审查者 | 模块边界、代码质量、协议、数据库、安全、依赖与测试代码 |
| [验收规范](acceptance.md) | 开发、测试、发布负责人 | 执行环境、验证矩阵、命令、量化通过条件与发布门禁 |

跨文档使用规则 ID 引用，不复制另一文档的数值表。视觉值只改 VIS 规则；数据预算只改 CODE 规则；测试环境和容差只改 QA 规则。需求中写“按规范”时，必须补充适用 ID 和任务状态。

## 等级与使用方法

- **MUST（必须）**：新功能、重做组件及本次修改触及的行为必须符合；不符合时按 QA-009 判断阻断，不以“截图大致相似”替代。
- **SHOULD（应当）**：默认采用；例外须在当前任务或 PR 中写明理由、影响、替代验证及恢复条件。
- **MAY（可以）**：按任务需要选择；采用后仍须满足相关 MUST。
- ID 稳定保留：`VIS-xxx`、`INT-xxx`、`CODE-xxx`、`QA-xxx`。删除规则保留废止说明；不要把旧 ID 分配给新含义。
- 各页采用“原则／规则／理由／正反例／验收引用”的格式；表格每行可承担一条规则，不要求重复长模板。
- 本目录描述未来迭代目标，不等于全仓库已经达标。已有差距按下表分批治理；记录例外不意味着风险已消除。
- 现有事实以源代码、实际构建结果和测试证据为准；规则与事实不一致时标出差距，不通过修改事实描述掩盖缺陷。
- 文档变更本身不授权修改代码、安装依赖、改 lint 配置或提交 Git。具体实施由对应迭代承接。

## 当前实现与目标差距

以下已有实现记录沿用前次源码核对，本次规范修订未重新执行源码与应用验证，不宣称未执行的测试已经通过。数值对照统一见 VIS-010。

| 范围 | 已有实现／证据入口 | 目标或待补项 |
| --- | --- | --- |
| 界面基础 | `apps/web/src/style.css`、`components/UI.tsx`；暖白与靛蓝、两档布局、原生控件 | 建立完整语义 token；统一文字、按钮、输入框、卡片与焦点样式 |
| 弹窗 | `components/Dialog.tsx`；原生模态、Escape、dirty 保护、提交防重与焦点返回 | 确认框独立规格；头尾稳定、正文独立滚动；危险确认视觉区分 |
| 模型配置 | `components/ProviderSettings.tsx`；自动加载、预设、自定义、清密钥、先保存再测试 | 完整字段错误关联和加载竞态回归；不把预设当实时可用模型目录 |
| 主题导航 | `components/TopicNavigator.tsx`、`TopicSettings.tsx`；指定对象整理、创建防重、删除范围说明 | 新建后输入焦点、各操作恢复路径持续回归 |
| 消息与选区 | `MessageViewport.tsx`、`selection.ts`、`SelectionDialog.tsx`、`ReferencesDialog.tsx` | 完整分页加载／重试反馈、粗指针目标、边缘工具栏与键盘路径统一 |
| 数据导入 | `DataSettings.tsx` 有上传状态、NDJSON AbortController 与卸载清理 | 显式取消入口、覆盖前确认、取消／提交竞态与部分成功反馈仍需实现；旧 JSON 路径不能据此声称可取消 |
| 状态与持久化 | `controller.ts`、`backend/app/domain/`、`repository.py`；有界查询缓存、revision、服务端撤销 | 保持边界；统一 typed contract；部分 metadata 仍读全量元数据，分叉／最终导入事务仍可能较长 |
| 模型流 | `services/chat-stream.ts`、`backend/app/chat_stream.py`、`providers/gateway.py`；协议注册与终态处理 | 补强运行时事件校验；厂商本地模拟与真实账号验收分开记录 |
| 代码风格 | TS／TSX、CSS 和部分 Python 仍有压缩单行、多声明写法 | 按触及模块渐进整理；不以全仓格式化混入功能改动 |
| 工程检查 | `package.json`、`backend/pyproject.toml`、`backend/tests/`、`desktop/tests/` | 已有类型／构建／测试入口；ESLint、Prettier、mypy 和截图差异门禁尚未接入 |
| 桌面分发 | `desktop/launcher.py`、`build.ps1`、`tests/packaged_smoke.py` | 按实际构建 ID 验证 ZIP 与安装器；历史目录存在产物不代表本次生成了新安装器 |
| 原生星空树 | `apps/web/src/graph/`、`backend/app/graph.py`、新增迁移 0005；浏览器已验证框选联系、右键预览／释放、IME 保护及编辑器身份；服务器万节点投影有界 | 初始网格尚非层级星空树；外框连续变形、完整祖先／子树展开、LOD 回差及碰撞聚合、镜头历史、触摸与只读矩阵未完成 |
| 主线轮次与临时预览 | 本次需求已确认语义并写入 `interaction.md` INT-016；当前图投影已有 `parent` 边、节点摘要和主题切换能力 | 尚未完成主线轮次节点的明确服务端生命周期、子节点完整对话的可取消临时加载、5ms 悬停状态机、离开恢复与点击提交的完整浏览器验收 |
| 移除与恢复 | 菜单和划删已接 `graph/removals`；逐操作 8 MiB／600 秒记录、子分支脱离、无关草稿／回答后恢复、依赖冲突及独立根恢复、幂等／期限／owner 已有测试 | 仍需补完整联系依赖补偿、所有异常网络／取消交错、浮窗所有遮挡／缩放变体；旧 next-mutation undo 端点保持独立 |

现阶段是亮色界面，未实现暗色主题；窄屏样式和浏览器检查不等于移动真机支持承诺。扩展限制详见[架构](../architecture.zh-CN.md)、[Web](../../apps/web/README.md)、[后端](../../backend/README.md)和[桌面](../../desktop/README.md)。

### 本轮执行证据（2026-09-14）

- `npm run typecheck`、Web build、`npm run test:gestures` 通过；`npm test` 为 48 passed，`py -m pytest desktop/tests -q` 为 10 passed。
- `npm run test:browser` 通过原有学习／三协议模拟／设置／选区／分页流程及新增鼠标图路径；普通响应实测最大 9,899 字节，未请求全量 workspace snapshot。
- 服务端 10000 节点 fixture 首轮查询 25.72ms、28,287 字节、199 节点；浏览器万节点 fixture 仍为多根网格，尚未覆盖深链／高扇出／跨边环的完整性能矩阵。最新浏览器冷 reload 989.2ms，图响应最大 3,082 字节；Headless RAF p95 4.30ms 仅是该采样环境结果，不能证明原生 60Hz 呈现达标，也没有完成 QA-006 全套冷启动／预热／30 次导航及指针反馈分项统计。
- 截图已读取检查：`test-results/graph-erase-preview.png`、`graph-overview.png`、`graph-10k.png`；原始 RAF 样本、引擎与机器信息在 `graph-measurements.json`。已有 UX 桌面／窄屏选区截图继续生成。
- 本轮未生成桌面包，未执行本次构建的原生 WebView2 手势、Windows 缩放及安装器验证；标准阈值保持不变，QA-010 整体仍为未完成。

## 星空树设计来源与提取范围

连续胶囊、鼠标手势与恢复体验直接来自用户最新要求及产品推导；具体参数为知树自定目标，不归因于腾讯或历史 MindFlow 实现。

固定历史来源：[zhi_map / a76041b](https://github.com/wwaawwaaee/zhi_map/tree/a76041b)。以下路径均相对于该历史提交，供参考文件不在当前工作树时追溯；表中保留前次定点源码核读记录，未运行 demo，也未验证说明中的联调或性能承诺。

| 历史来源路径（均在 `mindflow/` 下） | 核读得到的事实与采用边界 |
| --- | --- |
| `MindFlow_给队友的说明.md` | 将两版定义为独立 demo／接口示例；说明 UI 主要消费 SQLiteStorage，ChatService 尚未接入面板，双向同步为预留。其“附属整理导图”的定位不作为知树新方向 |
| `final_project_integrate/src/ui/mindmap_view.py`：`wheelEvent`、`set_focus_mode`、`set_nebula_mode`、`_on_nebula_label_toggle`、`fit_to_content` | 实际有 ScrollHandDrag、Ctrl+滚轮缩放、选中及一跳邻居聚焦、圆点视图、点击互斥持久标签、自适应视野。标签探索不等于展开子树；本次核读的画布／节点入口未见子树展开收起实现 |
| `final_project_integrate/src/ui/main_window.py`：`_open_mindmap`；`mindmap_view.py`：`apply_browse_starfield_layout` | 径向／扇区布局函数存在，但当前打开路径沿用 EDIT 手工位置，仅主动打开时自动适配视野。旧布局函数临时把多个根挂到主根的做法不采纳；知树须如实展示森林 |
| `final_project_integrate/src/ui/node_item.py`：鼠标事件；`main_window.py`：`_on_connect_nodes`、`_on_node_moved`、`_refresh_detail_panel` | 有连接端口拖线、位置保存、选中节点笔记面板同步。拖线直接建附加边并非引用确认；笔记面板并非知树消息原文 range 返回。连续阅读与返回出处是知树的新目标 |
| `final_project_integrate/src/mindmap/graph.py`：`EdgeData`、`add_edge`、`detach_parent_link`、`remove_node`、`detach_node` | 父子骨架与附加边分开；附加边无业务类型、按无向对去重、拒绝自环，但未限制跨边多节点成环。断父边可保留节点；同时存在递归删后代与仅删本节点两种方法。知树须遵守 INT-005，不能照搬级联删除 |
| `final_project_integrate/src/ui/theme.py`；`mindmap_view.py` 场景初始化 | 深色主题 token、星空／星云层、沿边粒子和根光晕确有代码。采用点线层次与空间探索思想；动画装饰、深色配色及 Qt 字号不作为核心或知树视觉数值来源 |

只提取交互思想，独立实现遵循 CODE-010、CODE-011；不复制 MindFlow 的领域模型、数据库或内嵌 domain。

## 腾讯公开来源与采用边界

以下为公开网页或源码路径；`main`、`develop` 是可变分支，不冒称固定版本。后续调整外部依据时，在对应任务记录实际查阅版本或 commit；不可臆造发布日期。

| 来源 | 借鉴内容 | 知树的处理 |
| --- | --- | --- |
| [TDesign 布局源码](https://github.com/Tencent/tdesign/blob/main/site/src/pages/design/layout_zh-CN.vue) | 概述→规范→分类→栅格→响应式；网格、安全边距、画板与固定区域 | 采用有节奏的间距和内容分区方法；侧栏和断点沿用知树产品选择，差值见 VIS-010 |
| [TDesign 字体源码](https://github.com/Tencent/tdesign/blob/main/site/src/pages/design/fonts_zh-CN.vue) | 字体回退、字阶、行高、字重、像素对齐 | 表单与辅助文字采用明确字阶；长文另设阅读字阶，不机械套用所有行高 |
| [TDesign 色彩](https://tdesign.tencent.com/design/color)／[源码](https://github.com/Tencent/tdesign/blob/main/site/src/pages/design/color_zh-CN.vue) | 主题色、功能色、中性色、全局与组件语义 token | 保留知树品牌，不改用腾讯蓝；不继承来源页面的对比度结论 |
| [TDesign 按钮](https://github.com/Tencent/tdesign-common/blob/develop/docs/web/design/button.md) | 使用场景、布局关系、推荐／慎用示例、主次操作 | 主操作原则按独立任务上下文应用，见 INT-001 |
| [TDesign 对话框](https://github.com/Tencent/tdesign-common/blob/develop/docs/web/design/dialog.md) | 明确目的、后果和按钮动作词 | 用于 dirty、删除、清配置和导入等真实流程 |
| [AlloyTeam ESLint 配置](https://github.com/AlloyTeam/eslint-config-alloy) | ESLint 关注逻辑质量，格式交给 Prettier；React／TypeScript 工程规范 | 借鉴职责分离，不宣称已安装或自动执行 |
| [AlloyTeam CodeGuide](https://alloyteam.github.io/CodeGuide/) | 一致命名、可读排版、语义 HTML、正反例表达 | 其中 JSHint、Grunt、旧编辑器与历史 JS 习惯不直接搬用 |

TDesign 上述源码及 CodeGuide 已在本次编写时查阅；Alloy ESLint 仓库本次在线读取受限，工具接入前须复核其当前说明与版本。来源仅用于方法与原则参考。实现须独立编写；源码、资源、字体的复制或依赖引入按 CODE-010 核对许可，不能把“参考腾讯”当作复制授权。

## 落地顺序

1. **原生图形闭环与界面基线**：按 INT-011～INT-015 打通主题定位→胶囊阅读→连续邻域探索→框选关联→返回原文，按 CODE-011 保持唯一领域投影；以 VIS-010 的差距及 VIS-011～VIS-014 建立组件、密度与镜头基线。
2. **任务与恢复闭环**：按 INT-005、CODE-012 同步实施划删与逐操作恢复，再验证加载、取消、焦点和竞态；设置→提问→选区展开→引用返回继续回归。不能以现有 revision 撤销充当新的恢复能力。
3. **工程治理**：按 CODE 规则整理本次触及的模块；新增格式／检查工具须单独说明规则、兼容性和执行入口。
4. **交付证据**：按 QA 规则建立可重复截图、操作矩阵和桌面分发验证，再将已验证步骤接入自动门禁。

每次迭代在原任务或 PR 内记录：适用 ID、当前差距、改动范围、证据位置、未通过项、负责人。无需为每次迭代新增一套过程文档。
