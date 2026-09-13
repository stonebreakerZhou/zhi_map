"""MindFlow 核心抽象层。

设计原则：
- 依赖倒置（DIP）：UI / Service 依赖抽象接口（Protocol），不依赖具体实现
- 可替换：换后端（zhi_map / Mock / Web / Zhishu.exe）只需换 backend 实现
- 可测试：用 Mock 接口测 UI / Service，无需启动真实状态机

层次结构：
- interfaces/   ← 抽象接口（Protocol）
- services/     ← 编排层（ChatService / MindMapService / OrganizationService）
- container.py  ← 依赖注入容器

P3 负责维护。
"""

from src.core.container import Container

__all__ = ["Container"]
