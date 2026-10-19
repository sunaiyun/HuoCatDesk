"""HuoCatDesk 命令行入口。

用法：
    python -m huocatdesk            # 启动 GUI（默认）
    python -m huocatdesk gui
    python -m huocatdesk host       # 被控端：打印邀请码后等待
    python -m huocatdesk join CODE  # 控制端：输入邀请码连接（headless，只保存屏幕帧）
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="huocatdesk", description="纯 P2P 远程桌面")
    parser.add_argument("cmd", nargs="?", default="gui",
                        choices=["gui", "host", "join"])
    parser.add_argument("code", nargs="?", help="join 模式的邀请码")
    args = parser.parse_args(argv)

    if args.cmd == "gui":
        from . import gui
        gui.main()
        return 0

    if args.cmd == "host":
        return _run_host()
    if args.cmd == "join":
        if not args.code:
            parser.error("join 模式需要邀请码参数")
        return _run_join(args.code)
    return 0


def _run_host() -> int:
    from . import session
    ses = session.HostSession(
        on_invite=lambda c: print(f"\n邀请码（发给对方）：\n{c}\n"),
        on_status=lambda s: print(f"[状态] {s}"),
        on_connected=lambda: print("[状态] 对方已连接，开始推送屏幕。"),
        on_file=lambda p: print(f"[文件] 已接收：{p}" if p else "[文件] 接收失败"),
    )
    try:
        ses.start()
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    print("按 Ctrl+C 退出。")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n退出。")
        ses.stop()
    return 0


def _run_join(code: str) -> int:
    from . import session
    ses = session.JoinSession(
        on_status=lambda s: print(f"[状态] {s}"),
        on_connected=lambda: print("[状态] 已连接，接收屏幕帧（headless 模式不渲染）。"),
        on_file=lambda p: print(f"[文件] 已接收：{p}" if p else "[文件] 接收失败"),
    )
    try:
        ses.connect(code)
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    print("按 Ctrl+C 退出。")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n退出。")
        ses.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
