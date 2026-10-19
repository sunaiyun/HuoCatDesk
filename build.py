#!/usr/bin/env python3
"""huocatdesk 打包脚本：用 PyInstaller 打成单文件可执行程序。

用法：
    python build.py
产物：dist/huocatdesk(.exe)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，正在安装…")
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        if rc:
            return rc
    # 清理旧产物
    for d in (ROOT / "build", ROOT / "dist"):
        if d.exists():
            shutil.rmtree(d)
    rc = subprocess.call([
        sys.executable, "-m", "PyInstaller",
        str(ROOT / "huocatdesk.spec"),
        "--noconfirm", "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
    ], cwd=str(ROOT))
    if rc == 0:
        exe = next((ROOT / "dist").glob("huocatdesk*"), None)
        print(f"\n✅ 打包完成：{exe}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
