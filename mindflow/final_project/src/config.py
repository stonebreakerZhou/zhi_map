"""全局配置。

所有路径、版本号、UI 参数都集中在这里。
便于：
- 一处修改，全局生效
- 打包后通过 .env 覆盖
- 测试时方便切换 mock

P1 负责维护。
"""

from __future__ import annotations

import os
from pathlib import Path

# ==================== 应用元信息 ====================

APP_NAME = "MindFlow"
APP_VERSION = "0.1.0"
ORG_NAME = "MindFlow Team"

# ==================== 路径 ====================

# 项目根目录（src/config.py 上两级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 资源目录（图标、QSS 样式）
ASSETS_DIR = PROJECT_ROOT / "assets"

# 数据目录（SQLite 数据库）
DATA_DIR = PROJECT_ROOT / "data"

# 日志目录
LOGS_DIR = PROJECT_ROOT / "logs"

# 数据库文件路径
DATABASE_PATH = DATA_DIR / "mindflow.db"

# 图片存储目录（⭐ 新增：节点挂图用）
IMAGES_DIR = DATA_DIR / "images"

# 文档存储目录（⭐ 新增：节点文档附件用，.txt/.md）
DOCUMENTS_DIR = DATA_DIR / "documents"

# 确保目录存在
for d in (ASSETS_DIR, DATA_DIR, LOGS_DIR, IMAGES_DIR, DOCUMENTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def get_database_url() -> str:
    """返回 SQLAlchemy 用的 SQLite URL。

    兼容 PyInstaller 打包后的临时目录。
    """
    return f"sqlite:///{DATABASE_PATH}"


# ==================== UI 配置 ====================

# ⭐ 默认窗口尺寸调大（2026-09-13）：星空沉浸感需要更大的画布
# 借鉴 project-graph 默认值范围（≈ 1440×900 ~ 1600×1000）
WINDOW_DEFAULT_WIDTH = 1480
WINDOW_DEFAULT_HEIGHT = 920
WINDOW_MIN_WIDTH = 1024
WINDOW_MIN_HEIGHT = 700

# 默认主题："light" 或 "dark"
DEFAULT_THEME = "light"

# 节点默认尺寸
NODE_DEFAULT_WIDTH = 180
NODE_DEFAULT_HEIGHT = 80
# ⭐ 节点默认色 — project-graph 深色 IDE 风主色 cyan（src/ui/theme.py: NODE_DEFAULT_COLOR）
NODE_DEFAULT_COLOR = "#22d3ee"

# 网格尺寸（思维导图布局）
NODE_HORIZONTAL_SPACING = 60
NODE_VERTICAL_SPACING = 30


# ==================== 开发 / 打包环境检测 ====================


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包后的 .exe 中。"""
    return getattr(sys, "frozen", False)


def is_dev_mode() -> bool:
    """是否开发模式（有源码、未打包）。"""
    return not is_frozen()


# ==================== 环境变量覆盖 ====================


# 允许通过环境变量覆盖关键配置（便于测试和部署）
def _env_override(key: str, default):
    """读取环境变量，若未设置返回默认值。"""
    return os.environ.get(key, default)


# 用法示例：MINDFLOW_DEBUG=1 python run.py
DEBUG_MODE = _env_override("MINDFLOW_DEBUG", "0") == "1"


import sys
