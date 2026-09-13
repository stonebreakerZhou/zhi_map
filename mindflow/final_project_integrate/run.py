# -*- coding: utf-8 -*-
"""开发模式启动入口。

用法：
    python run.py

等价于：
    python -m src.app
"""
import sys
from pathlib import Path

# 把项目根目录加到 sys.path，确保模块导入正常
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.app import main

if __name__ == "__main__":
    main()
