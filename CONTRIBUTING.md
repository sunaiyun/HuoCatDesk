# 贡献指南

欢迎为 HuoCatDesk 贡献代码。请遵循以下流程：

1. Fork 仓库并拉取特性分支（`feat/xxx`、`fix/xxx`）。
2. 改动前先跑一遍加密层已知答案测试：
   ```bash
   pip install -r requirements.txt
   python tests/test_crypto.py      # 应 21/21 通过
   ```
3. 提交前确保：
   - 新增/修改的密码学逻辑有对应的 RFC 官方向量回归（见 `tests/test_crypto.py`）。
   - 不引入第三方原生依赖（密码学层保持纯 Python；UI 用 tkinter；屏幕用 Pillow；键鼠用 ctypes）。
   - 不提交 `vendor/`、`dist/`、`build/`、`.rfcs/`、`.tmp/`（已在 `.gitignore`）。
4. 提交清晰 commit message，发起 PR 并描述改动与测试结果。

## 移动端

移动端实现请遵循 `mobile/PROTOCOL.md` 的 wire 协议契约，确保与桌面端互通。
