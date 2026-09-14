"""从仓库根目录的 Zhishu.svg 生成 Windows 多尺寸透明图标。"""
from pathlib import Path
import struct

import resvg_py


DESKTOP = Path(__file__).resolve().parent
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def build_icon() -> Path:
    source = DESKTOP.parent / "Zhishu.svg"
    frames = [resvg_py.svg_to_bytes(svg_path=str(source), width=size, height=size) for size in SIZES]
    # ICO 目录指向各尺寸的 PNG；Windows 10/11 原生支持透明 PNG 图层。
    offset = 6 + 16 * len(frames)
    entries = []
    for size, frame in zip(SIZES, frames):
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(frame), offset))
        offset += len(frame)
    target = DESKTOP / "zhishu.ico"
    target.write_bytes(struct.pack("<HHH", 0, 1, len(frames)) + b"".join(entries) + b"".join(frames))
    return target


if __name__ == "__main__":
    print(build_icon())
