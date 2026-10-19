"""HuoCatDesk 安装/卸载逻辑（由 PyInstaller 冻结成 huocatdesk-setup.exe）。

无参运行：安装到 %LocalAppData%\\Programs\\huocatdesk，建快捷方式，注册卸载项。
--uninstall：反向卸载。

不依赖 Inno Setup / NSIS，纯 PyInstaller + 标准库 + Windows COM（WScript.Shell 建快捷方式）。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

APP_NAME = "HuoCatDesk"
VERSION = "0.1.0"
PUBLISHER = "HuoCatDesk"


def resource_path(name: str) -> str:
    """PyInstaller 冻结后从 _MEIPASS 取资源；脚本态从同目录取。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def install_dir() -> str:
    return os.path.join(os.environ["LOCALAPPDATA"], "Programs", APP_NAME)


def app_exe() -> str:
    return os.path.join(install_dir(), "huocatdesk.exe")


def uninstall_exe() -> str:
    return os.path.join(install_dir(), "uninstall_huocatdesk.exe")


def start_menu_dir() -> str:
    return os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                        "Start Menu", "Programs")


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def create_shortcut(lnk: str, target: str, desc: str = "") -> None:
    """用 WScript.Shell COM 建 .lnk（无需额外依赖）。"""
    ps = (
        "$ws=New-Object -ComObject WScript.Shell;"
        f"$s=$ws.CreateShortcut({_ps_quote(lnk)});"
        f"$s.TargetPath={_ps_quote(target)};"
        f"$s.Description={_ps_quote(desc)};"
        f"$s.WorkingDirectory={_ps_quote(os.path.dirname(target))};"
        "$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   check=True, capture_output=True)


def install() -> None:
    d = install_dir()
    os.makedirs(d, exist_ok=True)
    # 1. 应用本体
    src = resource_path("huocatdesk.exe")
    if os.path.exists(src):
        shutil.copy2(src, app_exe())
    else:
        print(f"警告：未找到内嵌 huocatdesk.exe（{src}）", file=sys.stderr)
    # 2. 自身副本作为卸载器
    shutil.copy2(sys.executable, uninstall_exe())
    # 3. 快捷方式
    sm = start_menu_dir()
    os.makedirs(sm, exist_ok=True)
    try:
        create_shortcut(os.path.join(sm, APP_NAME + ".lnk"), app_exe(),
                        "HuoCatDesk 纯 P2P 远程桌面")
    except Exception as e:
        print(f"开始菜单快捷方式失败：{e}", file=sys.stderr)
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop",
                            APP_NAME + ".lnk")
    try:
        create_shortcut(desktop, app_exe(), "HuoCatDesk 纯 P2P 远程桌面")
    except Exception:
        pass
    # 4. 注册卸载信息（控制面板→程序）
    import winreg
    key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, d)
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,
                          f'"{uninstall_exe()}" --uninstall')
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
    print(f"✅ 已安装到 {d}")
    print(f"   开始菜单 / 桌面已建快捷方式")
    print(f"   卸载：控制面板→程序→卸载 huocatdesk，或运行 {uninstall_exe()} --uninstall")


def uninstall() -> None:
    import winreg
    # 1. 快捷方式
    for p in (os.path.join(start_menu_dir(), APP_NAME + ".lnk"),
              os.path.join(os.environ["USERPROFILE"], "Desktop", APP_NAME + ".lnk")):
        try:
            os.remove(p)
        except OSError:
            pass
    # 2. 注册表
    key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
    except OSError:
        pass
    # 3. 应用本体
    try:
        os.remove(app_exe())
    except OSError:
        pass
    # 4. 自身+目录延迟删除（运行中 exe 无法直接删）
    self = uninstall_exe()
    d = install_dir()
    subprocess.Popen([
        "cmd", "/c",
        f'timeout /t 2 /nobreak >nul & del "{self}" & rmdir "{d}"'
    ])
    print("✅ 已卸载 huocatdesk（残留的卸载器进程将在 2 秒后自删）")


def main() -> int:
    p = argparse.ArgumentParser(description="HuoCatDesk 安装/卸载器")
    p.add_argument("--uninstall", action="store_true", help="卸载 huocatdesk")
    args = p.parse_args()
    try:
        if args.uninstall:
            uninstall()
        else:
            install()
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
