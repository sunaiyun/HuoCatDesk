# HuoCatDesk 移动端架构设计

本文档定义 HuoCatDesk 在 **Android / iOS / HarmonyOS** 三端的实现架构，使移动端能
与桌面端互通（同一协议契约，见 `PROTOCOL.md`）。移动端典型场景是**控制端**（手机看
电脑屏幕、触控操作），也可作为**被控端**（投屏手机给电脑）。

## 1. 总体架构

```
┌─────────────────────────────────────────────────┐
│  UI 层（平台原生）                                │
│   Android: Jetpack Compose / iOS: SwiftUI /      │
│   HarmonyOS: ArkTS declarative UI               │
├─────────────────────────────────────────────────┤
│  会话编排层（移植自桌面 session.py，语义一致）     │
│   HostSession / JoinSession                      │
├─────────────────────────────────────────────────┤
│  传输层（平台原生 socket + 线程/协程）             │
│   UDP 打洞 + 加密帧（协议契约）                   │
├─────────────────────────────────────────────────┤
│  密码学层（平台原生或纯实现，算法一致）            │
│   X25519 + HKDF-SHA256 + ChaCha20-Poly1305       │
├─────────────────────────────────────────────────┤
│  平台能力层                                       │
│   屏幕采集 / 触控注入 / 文件系统                   │
└─────────────────────────────────────────────────┘
```

## 2. Android（Kotlin）

| 关注点 | 方案 |
|--------|------|
| 语言 | Kotlin |
| UI | Jetpack Compose |
| 网络 | `java.net.DatagramSocket`（UDP），协程 `Dispatchers.IO` 收发 |
| 密码学 | `javax.crypto` + BoringSSL（Conscrypt）：X25519 用 `KeyAgreement("X25519")`，HKDF/ChaCha20-Poly1305 用 `Cipher("ChaCha20-Poly1305")`；或直接移植桌面纯 Python 算法为 Kotlin（无原生依赖路线） |
| 屏幕采集（被控） | `MediaProjection` + `VirtualDisplay` → `Surface` → JPEG（`android.graphics.Bitmap` + compress） |
| 屏幕渲染（控制） | `ImageView`/`Image` Composable，从 JPEG 解码 `Bitmap` |
| 触控（控制→被控） | `onTouchEvent` → 归一化坐标 → MOUSE 帧 |
| 触控注入（被控） | 无障碍服务 `AccessibilityService` 手势 `dispatchGesture`（系统限制，非 root 无法注入任意键鼠，仅手势） |
| 文件 | `Storage Access Framework`（`DocumentFile`），分块读/写 |
| 打洞 | STUN 库或移植 `stun.py`；邀请码编解码移植 `p2p.py` 的 CRC16+base32 |

**约束**：Android 非 root 无法全局注入键鼠事件，被控端需借助无障碍服务做手势映射，
或仅在投屏（只看不控）场景使用。控制端功能完整。

## 3. iOS（Swift）

| 关注点 | 方案 |
|--------|------|
| 语言 | Swift |
| UI | SwiftUI |
| 网络 | `Network.framework` `NWConnection`（UDP），或 `BSD socket` |
| 密码学 | CryptoKit：`Curve25519.KeyAgreement`（X25519）、`HKDF<SHA256>`、`ChaChaPoly`（ChaCha20-Poly1305）——与桌面算法逐字节一致 |
| 屏幕采集（被控） | `ReplayKit` broadcast extension → `CMSampleBuffer` → JPEG（`UIImage` jpegData） |
| 屏幕渲染（控制） | SwiftUI `Image`，JPEG 解码 `UIImage(data:)` |
| 触控（控制） | `DragGesture` / `TapGesture` → MOUSE 帧；键盘需外接或 `UITextField` 代理 |
| 触控注入（被控） | iOS 不开放（沙箱），仅投屏场景可行；控制端完整 |
| 文件 | `UIDocumentPickerViewController`，`FileManager` 分块读写 |

**约束**：iOS 沙箱禁止注入输入，移动端作为**被控端**仅支持投屏（只看不控）；作为
**控制端**功能完整。后台 UDP 受系统限制，需保持前台。

## 4. HarmonyOS（ArkTS）

| 关注点 | 方案 |
|--------|------|
| 语言 | ArkTS |
| UI | ArkUI 声明式 |
| 网络 | `@ohos.net.socket`（UDP `UDPSocket`），`@ohos.multithreading` 或异步收发 |
| 密码学 | `@ohos.security.huks`：X25519 keyAgreement、HKDF-SHA256、ChaCha20-Poly1305（Huks 支持该算法集）；或移植纯实现 |
| 屏幕采集（被控） | `@ohos.screenCapture`（屏幕录制 Kit）→ JPEG |
| 屏幕渲染（控制） | ArkUI `Image` 组件 |
| 触控（控制） | `onTouch` 事件 → MOUSE 帧 |
| 触控注入（被控） | 受限，需系统级权限 |
| 文件 | `@ohos.file.fs` / `@ohos.file.picker` |

## 5. 跨端互通矩阵

| 控制端 \ 被控端 | Windows | macOS | Linux | Android | iOS | HarmonyOS |
|----------------|:--:|:--:|:--:|:--:|:--:|:--:|
| Windows | ✅ | ✅ | ✅ | ✅ 投屏 | ✅ 投屏 | ✅ 投屏 |
| Android | ✅ | ✅ | ✅ | 投屏 | — | 投屏 |
| iOS | ✅ | ✅ | ✅ | — | 投屏 | — |

✅ = 完整控制；投屏 = 只看不控（移动被控端场景，平台限制无法注入输入）。

## 6. 移动网络与 NAT

移动网络（4G/5G）多为 CGNAT / 对称 NAT，纯 UDP 打洞常失败。移动端应：
1. 优先 Wi-Fi（家庭 NAT 多为锥形，可打洞）。
2. 检测打洞失败后提示「对方网络不支持直连」。
3. 作为可选扩展：引入 TURN 中转（违反「无中转」原则，默认不启用，仅在双方明确同意时使用）。

## 7. 移植清单（每个平台必须实现的最小集）

- [ ] STUN 客户端（RFC 5389 Binding Request + XOR-MAPPED-ADDRESS 解析）
- [ ] 邀请码编解码（CRC16 + base32，格式见 `PROTOCOL.md` §4）
- [ ] UDP 打洞握手（HELLO / HELLO_ACK）
- [ ] X25519 + HKDF-SHA256 + ChaCha20-Poly1305（算法参数见 `PROTOCOL.md` §3）
- [ ] 帧分帧/解析（`PROTOCOL.md` §2）
- [ ] SCREEN / KEY / MOUSE / FILE_* 消息处理
- [ ] 屏幕 JPEG 采集与渲染
- [ ] 触控事件归一化与 MOUSE 帧映射
- [ ] 文件分块传输 + SHA256 校验

满足以上即与桌面端完全互通。
