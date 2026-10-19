"""python -m huocatdesk 入口（用绝对导入，兼容 PyInstaller 冻结）。"""
from huocatdesk.cli import main

raise SystemExit(main())
