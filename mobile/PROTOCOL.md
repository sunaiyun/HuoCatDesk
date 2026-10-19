# HuoCatDesk 协议契约（wire protocol）

本文档是 HuoCatDesk 跨端互通的权威协议定义。任何平台实现只要遵循本契约即可与桌面端
互通。所有多字节整数 **大端（big-endian）**，除非注明 little-endian。

## 1. 传输层

- **传输**：UDP（`AF_INET` / `SOCK_DGRAM`），单个报文 ≤ 65535 字节。
- **公网地址发现**：RFC 5389 STUN Binding Request，解析 `XOR-MAPPED-ADDRESS`
  （type=0x0020）得到 NAT 公网映射 `(ip, port)`。
- **NAT 保活**：每 25 秒发一次空 Binding Request 维持映射。
- **打洞**：双方互向对方公网 `(ip, port)` 发送 HELLO 帧，收到即建立会话。

## 2. 帧格式（分帧）

每个 UDP 报文是一帧：

```
偏移  长度  字段       说明
0     4     MAGIC     b"P2PD"（0x50325044）
4     1     TYPE      消息类型（见 §5）
5     1     FLAGS     bit0 = body 已加密
6     4     LEN       body 字节数（BE）
10    LEN   BODY      载荷
```

- `LEN` 上限 65000（大块由上层分片，每片一帧）。
- 握手帧（HELLO / HELLO_ACK）`FLAGS.bit0 = 0`，body 明文。
- 会话建立后所有帧 `FLAGS.bit0 = 1`，`BODY = nonce(12) || ciphertext || tag(16)`，
  其中 `ciphertext = ChaCha20-Poly1305_Encrypt(session_key, nonce, plaintext, aad)`。
  `aad = bytes([TYPE])`（单字节类型，提供类型完整性）。
  `nonce` 每帧随机 12 字节（96 位，碰撞概率可忽略）。

## 3. 加密层（算法参数）

| 算法 | 参数 | 来源 |
|------|------|------|
| X25519 | RFC 7748 §5 Montgomery ladder；接收 u 坐标最高位屏蔽；输出最高位屏蔽 | `crypto.py` `_x25519_ref` |
| HKDF-SHA256 | RFC 5869；salt = b""，info = b"huocatdesk-session-v1"，L = 32 | `crypto.derive_key` |
| ChaCha20-Poly1305 | RFC 8439；AEAD；一次性密钥 = ChaCha20 块(key, counter=0, nonce) 的前 32 字节（r‖s 全用）；加密从 counter=1 起 | `crypto.Aead` |
| 标签长度 | 16 字节 | — |

会话密钥派生：
```
shared = X25519(my_private, peer_public)
session_key = HKDF-SHA256(ikm=shared, salt=b"", info=b"huocatdesk-session-v1", L=32)
```

## 4. 邀请码格式

邀请码是带外交换公钥与公网地址的可读字符串。

```
raw  = pubkey(32) || ip(4) || port(2, BE) || timestamp(4, BE, unix 秒低 32 位)
blob = crc16(raw, BE) || raw          # crc16 = Modbus 多项式 0xA001
code = base32(blob).rstrip("=")        # RFC 4648 base32，无填充
display = 每 4 字符一组用 "-" 连接
```

解析时：去 `-`/空格 → 大写 → 补 `=` 到 8 的倍数 → base32 解码 → 校验 CRC16 → 取
pubkey/ip/port。CRC 失败表示输入错误。

## 5. 消息类型

| 值 | 名称 | BODY（明文部分） | 阶段 |
|----|------|------------------|------|
| 1  | HELLO | `pubkey(32) || ts_ms(8, BE)` | 握手，明文 |
| 2  | HELLO_ACK | `pubkey(32) || ts_ms(8, BE)` | 握手，明文 |
| 3  | SCREEN | `seq(4, BE) || ts_ms(8, BE) || width(2, BE) || height(2, BE) || JPEG_DATA` | 加密 |
| 4  | KEY | `vk_code(4, BE) || state(1)` state: 1=down 0=up | 加密 |
| 5  | MOUSE | `x(2, BE) || y(2, BE) || buttons(1) || wheel(1, signed)` | 加密 |
| 6  | FILE_META | `file_id(1) || name_len(2, BE) || name(utf-8) || size(8, BE)` | 加密 |
| 7  | FILE_DATA | `file_id(1) || offset(8, BE) || data` | 加密 |
| 8  | FILE_END | `file_id(1) || sha256(32)` | 加密 |
| 9  | HEARTBEAT | `ts_ms(8, BE)` | 加密 |
| 10 | BYE | 空 | 加密 |
| 11 | ACK | `what_type(1) || seq(4, BE)` | 加密 |

### 坐标约定（MOOSE 帧）
- `x`, `y` 是归一化绝对坐标乘以 65535，即 `x = int(x_norm * 65535)`，`x_norm ∈ [0,1]`。
  执行端还原：`x_norm = x / 65535`，再映射到本地屏幕像素。
- `buttons` 位掩码：bit0=左键，bit1=右键，bit2=中键。执行端与上次状态比较发 down/up。
- `wheel` 有符号字节：+1=上滚一档，-1=下滚一档，0=无。

### 键码约定（KEY 帧）
- `vk_code` 为 Windows 虚拟键码（VK_*）。跨平台执行端按本平台键码映射表转换。
  桌面端 Windows 直接用 SendInput 的 wVk。

## 6. 握手状态机

```
双方各自:  bind UDP socket
           STUN discover → public_ep
host:  make_invite(pubkey, public_ep) → 带外发给 join
join:  parse_invite(code) → peer_pubkey, peer_ep
双方:  反复向 peer_ep 发 HELLO(my_pubkey, ts)        [每 100ms]
           ↓ 收到 HELLO
           记 peer_pubkey = body[:32], peer_ep = 报文来源地址（应对 NAT 重绑定）
           派生 session_key（§3）
           回 HELLO_ACK(my_pubkey, ts)
           ↓ 收到 HELLO_ACK
           记 peer_pubkey, 派生 session_key
           → connected，后续帧全部加密
```

握手是**对称**的：任一方先收到对方的 HELLO 即派生密钥并回 ACK；收到 ACK 的一方
也派生密钥。双方派生出同一 `session_key`（X25519 对称性保证）。

## 7. 可靠性

- **SCREEN 帧**：不可靠，丢帧不重传，按 `seq` 丢弃乱序旧帧。
- **KEY/MOUSE**：尽力发（`send_reliable` 重发 5 次），乱序由执行端按时间戳丢弃旧帧。
- **FILE**：`FILE_DATA` 带 `offset`，接收端按偏移写入；`FILE_END` 携带 SHA256 全文
  校验。丢失分片会导致校验失败，由应用层重传整个文件。

## 8. 安全属性

- **机密性**：所有会话帧 ChaCha20-Poly1305 加密。
- **完整性 + 认证**：AEAD tag 校验，篡改帧被丢弃（`InvalidTag`）。
- **前向保密**：每次会话独立 X25519 临时密钥对，会话密钥不落盘。
- **重放**：当前版本未实现序号防重放窗口；SCREEN 容忍重放，控制/文件建议应用层
  幂等或加序号窗口（未来扩展点）。
