#!/usr/bin/env python3
"""构建 huocatdesk Windows 安装包（onedir + PowerShell 安装脚本，zip 分发）。

为什么不用 onefile：本构建/运行环境的 onefile bootloader 无法创建 _MEI 临时目录
（沙箱限制）。onedir 从自身目录运行，无需临时解压，可在此环境真正验证安装/卸载。

产物：dist/huocatdesk-setup.zip
  解压后得到 huocatdesk-setup/ 文件夹，内含：
    huocatdesk/            应用（huocatdesk.exe + _internal/）
    install.ps1         安装/卸载脚本
    Install HuoCatDesk.bat 双击安装
    Uninstall HuoCatDesk.bat 双击卸载
用法：python packaging/build_installer.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # HuoCatDesk/
PY = sys.executable
PKG = ROOT / "packaging"


def run(cmd: list[str]) -> int:
    print(">", " ".join(str(c) for c in cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)
    # 1. 应用（onedir）→ dist/huocatdesk/
    rc = run([PY, "-m", "PyInstaller", "huocatdesk.spec", "--noconfirm",
              "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build")])
    if rc:
        return rc
    app_dir = ROOT / "dist" / "HuoCatDesk"
    if not app_dir.exists():
        print(f"错误：未生成 {app_dir}", file=sys.stderr)
        return 1
    app_exe = app_dir / "huocatdesk.exe"
    print(f"  应用已生成：{app_exe}（{app_exe.stat().st_size // 1024} KB）")

    # 2. 组装安装包文件夹 dist/huocatdesk-setup/
    setup_dir = ROOT / "dist" / "huocatdesk-setup"
    if setup_dir.exists():
        shutil.rmtree(setup_dir)
    setup_dir.mkdir(parents=True)
    shutil.move(str(app_dir), str(setup_dir / "HuoCatDesk"))
    for f in ("install.ps1", "Install HuoCatDesk.bat", "Uninstall HuoCatDesk.bat"):
        shutil.copy2(str(PKG / f), str(setup_dir / f))

    # 3. 压缩成 zip
    zip_path = ROOT / "dist" / "huocatdesk-setup.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in setup_dir.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(ROOT / "dist"))

    # 统计大小
    total = sum(f.stat().st_size for f in setup_dir.rglob("*") if f.is_file())
    print(f"\n✅ 安装包已生成：{zip_path}")
    print(f"   解压后大小：{total / 1024 / 1024:.1f} MB")
    print(f"   zip 大小：{zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"   分发：把 huocatdesk-setup.zip 发给用户，解压后双击“Install HuoCatDesk.bat”。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
