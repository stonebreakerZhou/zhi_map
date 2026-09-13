"""日志工具。

统一日志格式，同时输出到：
- 控制台（带颜色，stderr）
- logs/mindflow.log（带轮转）

P1 负责维护。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import LOGS_DIR

# 日志格式
_CONSOLE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_FILE_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 防止重复调用 setup_logger
_initialized = False


def setup_logger(level: str = "INFO") -> None:
    """初始化全局日志。

    Args:
        level: 日志级别，DEBUG / INFO / WARNING / ERROR
    """
    global _initialized
    if _initialized:
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清空已有 handler（避免重复输出）
    root_logger.handlers.clear()

    # ---- 控制台 handler ----
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, _DATE_FORMAT))
    root_logger.addHandler(console_handler)

    # ---- 文件 handler（带轮转，单文件最大 1MB，保留 5 个） ----
    log_file: Path = LOGS_DIR / "mindflow.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, _DATE_FORMAT))
    root_logger.addHandler(file_handler)

    # 抑制第三方库的啰嗦日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取 logger 实例。

    Args:
        name: 一般传 __name__ 或模块名

    Returns:
        logging.Logger 实例
    """
    if not _initialized:
        setup_logger()
    return logging.getLogger(name)
