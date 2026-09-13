"""MindFlow 主入口。

负责：
- 启动 QApplication
- 创建主窗口
- 初始化日志、配置
- 进入 Qt 事件循环

P1 负责维护。
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from src.config import APP_NAME, APP_VERSION, ORG_NAME
from src.utils.logger import get_logger, setup_logger


def main() -> int:
    """程序主入口。

    Returns:
        int: Qt 事件循环退出码
    """
    # 1. 初始化日志
    setup_logger()
    logger = get_logger("mindflow.app")
    logger.info(f"启动 {APP_NAME} v{APP_VERSION}")

    # 2. 创建 Qt 应用
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)

    # 3. 创建主窗口
    from src.ui.main_window import MindFlowWindow

    window = MindFlowWindow()
    window.show()

    logger.info("窗口已显示，进入事件循环")

    # 4. 进入事件循环
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
