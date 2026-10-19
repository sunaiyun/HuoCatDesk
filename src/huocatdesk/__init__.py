"""HuoCatDesk — 纯 P2P 直连的远程桌面（无中转服务器）。

设计目标：两台机器之间不经过任何中转/转发服务器即可建立加密的远程控制通道，
包括屏幕画面、键鼠控制与文件传输。

模块划分：
    crypto    加密层（X25519 + HKDF + ChaCha20-Poly1305，纯 Python 回退）
    protocol  消息分帧与类型定义
    stun      STUN 客户端与 NAT 类型探测
    p2p       NAT 打洞握手与可靠数据通道
    session   会话编排（被控端 / 控制端）
    screen    屏幕采集与 JPEG 编码
    control   键鼠事件的采集与执行
    filexfer  文件传输
    cli       命令行入口
    gui       tkinter 图形界面
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
