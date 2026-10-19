# HuoCatDesk — 纯 P2P 远程桌面（无中转服务器）

两台机器之间不经过任何中转/转发服务器即可建立加密的远程控制通道：屏幕画面、键鼠
控制、文件传输。仅依赖 **Pillow** + Python 标准库（tkinter/ctypes/socket/hashlib），
密码学层为纯 Python 参考实现（X25519/HKDF/ChaCha20-Poly1305），已被 RFC 官方向量
逐条验证（见 `tests/test_crypto.py`）。

## 工作原理

```
被控端(host)                          控制端(join)
   │ STUN 探测公网地址                    │ STUN 探测公网地址
   │ 生成邀请码 = base32(公钥+公网地址)   │
   │ ────── 邀请码带外发给对方 ──────►    │
   │                                     │ parse_invite → 对端公钥+公网地址
   │ ◄──── 双向 UDP 打洞(HELLO) ────►    │
   │ X25519 + HKDF 协商会话密钥           │
   │ ChaCha20-Poly1305 加密通道           │
   │ ◄──── 屏幕帧(JPEG) ──────────────   │ 渲染
   │   键鼠事件 ─────────────────────►    │ 采集并转发
   │   文件分块 ─────────────────────►    │
```

邀请码是双方交换公网地址与公钥的唯一带外凭证（电话/聊天软件口述），全程无服务器。

## 安装

```bash
pip install -r requirements.txt      # 仅 Pillow
pip install -e .                     # 可选：安装为命令 HuoCatDesk
```

## 使用

```bash
# GUI（推荐）
python -m huocatdesk
# 或
HuoCatDesk                          # 安装后

# 被控端（打印邀请码后等待）
python -m huocatdesk host

# 控制端（输入邀请码直连）
python -m huocatdesk join "<邀请码>"
```

GUI 操作：
1. 双方都启动程序。
2. 被控方选「被控」→ 开始 → 把邀请码发给控制方。
3. 控制方选「控制」→ 粘贴邀请码 → 开始。
4. 连上后被控方屏幕显示在控制方窗口，鼠标键盘直接控制；点「发送文件」互传。

## 打包成单文件可执行

```bash
python build.py        # 产物 dist/huocatdesk(.exe)，用 PyInstaller
```

## NAT 兼容性

- **锥形 NAT**（full-cone / restricted-cone / port-restricted-cone）：打洞成功。
- **对称 NAT**：通常打洞失败（端口随机）。两端中只要有一方是锥形 NAT 即可成功；
  双方皆对称 NAT 需另部署 TURN 中转（本项目坚持无中转，故该情形不支持）。

## 模块

| 模块 | 职责 |
|------|------|
| `crypto` | X25519 + HKDF + ChaCha20-Poly1305（纯 Python，RFC 验证） |
| `protocol` | UDP 分帧 + 消息类型 |
| `stun` | RFC 5389 STUN 客户端 + NAT 端口保活 |
| `p2p` | 邀请码编码 + UDP 打洞握手 + 加密通道 |
| `screen` | 屏幕采集 + JPEG 编码（Pillow） |
| `control` | 键鼠执行（Windows SendInput / ctypes） |
| `filexfer` | 文件分块流式传输 + SHA256 校验 |
| `session` | 被控/控制会话编排 |
| `gui` | tkinter 图形界面 |
| `cli` | 命令行入口 |

## 移动端

移动端架构设计与协议契约见 `mobile/`。移动端按同一协议契约实现即可与本桌面端互通。

## 安全

- 会话密钥由 X25519 ECDH 派生，HKDF-SHA256 扩展，ChaCha20-Poly1305 AEAD 加密所有帧。
- 每帧独立随机 nonce（96 位），AEAD 提供机密性 + 完整性 + 认证。
- 邀请码含 CRC16 校验，携带公钥指纹——输入错误码不会建立会话。
