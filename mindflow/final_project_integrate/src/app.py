"""MindFlow 主入口。

负责：
- 启动 QApplication
- 初始化日志、配置、依赖注入容器
- 创建主窗口
- 进入 Qt 事件循环

P1 负责维护。
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from src.config import APP_NAME, APP_VERSION, ORG_NAME
from src.core.api import api
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

    # 2. ⭐ 初始化依赖注入容器（ChatBackend / AIProvider / Storage 一并 ready）
    #    UI 层即便绕过 service 直接调 mindmap_repo，DI 单例也得先建好
    #    这样 HTTP backend 才会在 app 启动时就被探测 / 失败也尽早知道
    mindflow_api = api()
    logger.info(
        f"DI 容器就绪：chat={type(mindflow_api.container.chat_backend).__name__}, "
        f"ai={type(mindflow_api.container.ai_provider).__name__}, "
        f"storage={type(mindflow_api.container.storage).__name__}"
    )

    # 3. 创建 Qt 应用
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)

    # 4. 创建主窗口
    from src.ui.main_window import MindFlowWindow

    window = MindFlowWindow()
    window.show()

    logger.info("窗口已显示，进入事件循环")

    # 5. 进入事件循环
    exit_code = app.exec()

    # 6. ⭐ 释放资源（关 HTTP client 等）
    mindflow_api.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
