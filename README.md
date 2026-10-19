# HuoCatDesk — Pure-P2P Remote Desktop (no relay server)

[English](./README.md) | [简体中文](./README.zh-CN.md)

Establish an encrypted remote-control channel between two machines with **no relay/forwarding
server** in between: screen streaming, keyboard/mouse control, and file transfer. Depends only on
**Pillow** + the Python standard library (tkinter/ctypes/socket/hashlib). The crypto layer is a
pure-Python reference implementation (X25519/HKDF/ChaCha20-Poly1305), verified against official RFC
test vectors (see `tests/test_crypto.py`).

## How it works

```
Host (controlled)                    Controller (join)
   │ STUN: discover public address     │ STUN: discover public address
   │ invite = base32(pubkey + pub addr) │
   │ ────── invite sent out-of-band ──► │
   │                                    │ parse_invite → peer pubkey + addr
   │ ◄── bidirectional UDP hole- ─────► │
   │      punching (HELLO)             │
   │ X25519 + HKDF → session key        │
   │ ChaCha20-Poly1305 encrypted link   │
   │ ◄──── screen frames (JPEG) ──────  │ render
   │   key/mouse events ──────────────► │ capture & forward
   │   file chunks ──────────────────►  │
```

The invite code is the sole out-of-band credential exchanging public address + public key
(dictate it over phone/chat). No server is ever involved.

## Install

```bash
pip install -r requirements.txt      # only Pillow
pip install -e .                      # optional: install as the `HuoCatDesk` command
```

## Usage

```bash
# GUI (recommended)
python -m huocatdesk
# or
HuoCatDesk                          # after install

# Host (print invite code, then wait)
python -m huocatdesk host

# Controller (enter invite code to connect directly)
python -m huocatdesk join "<invite-code>"
```

GUI flow:
1. Both sides launch the app.
2. Host picks "Host" → Start → sends the invite code to the controller.
3. Controller picks "Control" → pastes the invite code → Start.
4. Once connected, the host's screen appears in the controller's window; drive it with mouse &
   keyboard. Click "Send file" to transfer files either way.

## Build a single-file executable

```bash
python build.py        # produces dist/huocatdesk(.exe) via PyInstaller
```

## NAT compatibility

- **Cone NAT** (full-cone / restricted-cone / port-restricted-cone): hole punching succeeds.
- **Symmetric NAT**: usually fails (random ports). Succeeds as long as one side is cone NAT;
  if both are symmetric, a TURN relay would be required (this project deliberately stays
  relay-free, so that case is unsupported).

## Modules

| Module | Responsibility |
|--------|----------------|
| `crypto` | X25519 + HKDF + ChaCha20-Poly1305 (pure Python, RFC-verified) |
| `protocol` | UDP framing + message types |
| `stun` | RFC 5389 STUN client + NAT keepalive |
| `p2p` | Invite-code encoding + UDP hole-punching handshake + encrypted channel |
| `screen` | Screen capture + JPEG encoding (Pillow) |
| `control` | Keyboard/mouse execution (Windows SendInput / ctypes) |
| `filexfer` | Chunked file streaming + SHA256 verification |
| `session` | Host/controller session orchestration |
| `gui` | tkinter GUI |
| `cli` | Command-line entry point |

## Mobile

Mobile architecture design and the protocol contract are in `mobile/`. Any client implementing
that contract interoperates with the desktop end.

## Android client

`android/` is a pure-Kotlin Android controller (byte-for-byte interoperable with the desktop end);
a buildable APK has been produced and verified:

- Crypto is a pure-Kotlin port (X25519/HKDF/ChaCha20-Poly1305), independent of the OS version,
  passing 7/7 RFC vector regression tests (`app/src/test/.../CryptoTest.kt`).
- Features: enter the desktop invite code → UDP hole-punch connect → render peer screen (JPEG)
  → touch control → send files.
- minSdk 17 (Android 4.2+), targetSdk 34, no AndroidX dependency.

On a machine with the Android SDK + JDK 17:

```bash
cd android
./gradlew assembleDebug     # produces app/build/outputs/apk/debug/app-debug.apk
```

Or use `build_apk.ps1` at the project root (auto-downloads cmdline-tools + Gradle and builds,
keeping everything inside the project dir — nothing on the C: drive).

## Security

- Session key derived via X25519 ECDH, expanded with HKDF-SHA256; all frames sealed with
  ChaCha20-Poly1305 AEAD.
- Per-frame random nonce (96-bit); AEAD provides confidentiality + integrity + authentication.
- Invite code carries a CRC16 and a public-key fingerprint — a mistyped code never establishes a
  session.

## Contributors

Built with AI co-development:

- **Claude** (Anthropic)
- **ChatGPT** (OpenAI)
- **DeepSeek**
- **Gemini** (Google)

Human contributors welcome — see `CONTRIBUTING.md`.
