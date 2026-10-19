"""HuoCatDesk 图形界面（tkinter，无需第三方 UI 依赖）。

两种模式：
  - 被控(host)：显示邀请码、等待连接、后台抓屏推送、执行对方键鼠、收文件。
  - 控制(join)：输入邀请码、打洞直连、显示对方屏幕、转发键鼠、发文件。

屏幕帧在 Channel 接收线程到达，通过 queue 投递到主线程渲染（tkinter 非线程安全）。
"""
from __future__ import annotations

import io
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from . import session


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("HuoCatDesk — 纯 P2P 远程桌面")
        self.root.geometry("900x620")
        self.ses = None
        self._frame_q: queue.Queue = queue.Queue()
        self._photo = None
        self._btn = 0  # 当前鼠标按键状态位掩码
        self._build()

    # ---- 布局 ----
    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)
        ttk.Label(top, text="模式：", font=("", 11)).pack(side=tk.LEFT)
        self._mode = tk.StringVar(value="host")
        ttk.Radiobutton(top, text="被控（分享我的屏幕）", value="host",
                        variable=self._mode, command=self._switch).pack(side=tk.LEFT)
        ttk.Radiobutton(top, text="控制（连接对方）", value="join",
                        variable=self._mode, command=self._switch).pack(side=tk.LEFT, padx=10)
        self._btn_run = ttk.Button(top, text="开始", command=self._run)
        self._btn_run.pack(side=tk.RIGHT)
        self._btn_stop = ttk.Button(top, text="停止", command=self._stop, state=tk.DISABLED)
        self._btn_stop.pack(side=tk.RIGHT, padx=6)

        self._container = ttk.Frame(self.root)
        self._container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._switch()

        self._status = tk.StringVar(value="就绪。选择模式后点“开始”。")
        ttk.Label(self.root, textvariable=self._status,
                  relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)
        self.root.after(40, self._poll)

    def _switch(self):
        for w in self._container.winfo_children():
            w.destroy()
        if self._mode.get() == "host":
            self._host_view = ttk.Frame(self._container)
            self._host_view.pack(fill=tk.BOTH, expand=True)
            ttk.Label(self._host_view, text="把下面的邀请码发给对方：",
                      font=("", 11)).pack(anchor=tk.W, pady=(8, 4))
            self._invite_txt = tk.Text(self._host_view, height=4, width=80,
                                       font=("Consolas", 11))
            self._invite_txt.pack(fill=tk.X)
            self._invite_txt.insert("1.0", "（开始后生成）")
            self._invite_txt.config(state=tk.DISABLED)
            ttk.Button(self._host_view, text="复制邀请码",
                       command=self._copy_invite).pack(anchor=tk.W, pady=6)
            ttk.Button(self._host_view, text="发送文件给对方…",
                       command=self._send_file).pack(anchor=tk.W)
        else:
            self._join_view = ttk.Frame(self._container)
            self._join_view.pack(fill=tk.BOTH, expand=True)
            ttk.Label(self._join_view, text="粘贴对方邀请码：",
                      font=("", 11)).pack(anchor=tk.W, pady=(8, 4))
            self._code_entry = tk.Text(self._join_view, height=4, width=80,
                                        font=("Consolas", 11))
            self._code_entry.pack(fill=tk.X)
            self._canvas = tk.Canvas(self._join_view, bg="black")
            self._canvas.pack(fill=tk.BOTH, expand=True, pady=8)
            self._bind_input()
            ttk.Button(self._join_view, text="发送文件给对方…",
                       command=self._send_file).pack(anchor=tk.W)

    # ---- 运行 ----
    def _run(self):
        if self._mode.get() == "host":
            self._run_host()
        else:
            self._run_join()

    def _run_host(self):
        self._btn_run.config(state=tk.DISABLED)
        self._btn_stop.config(state=tk.NORMAL)
        self.ses = session.HostSession(
            on_invite=self._show_invite,
            on_status=self._status.set,
            on_connected=lambda: self._status.set("已连接：正在推送屏幕。"),
            on_file=self._on_file_done,
        )
        try:
            self.ses.start()
        except Exception as e:
            self._status.set(f"错误：{e}")
            self._btn_run.config(state=tk.NORMAL)
            self._btn_stop.config(state=tk.DISABLED)

    def _run_join(self):
        code = self._code_entry.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("HuoCatDesk", "请粘贴邀请码")
            return
        self._btn_run.config(state=tk.DISABLED)
        self._btn_stop.config(state=tk.NORMAL)
        self.ses = session.JoinSession(
            on_frame=lambda w, h, jpg: self._frame_q.put((w, h, jpg)),
            on_status=self._status.set,
            on_connected=lambda: self._status.set("已连接：接收屏幕中。"),
            on_file=self._on_file_done,
        )
        threading_wrap = __import__("threading")
        def _do():
            try:
                self.ses.connect(code)
            except Exception as e:
                self.root.after(0, lambda: self._status.set(f"连接失败：{e}"))
                self.root.after(0, lambda: self._btn_run.config(state=tk.NORMAL))
        threading_wrap.Thread(target=_do, daemon=True).start()

    def _stop(self):
        if self.ses:
            self.ses.stop()
            self.ses = None
        self._btn_run.config(state=tk.NORMAL)
        self._btn_stop.config(state=tk.DISABLED)
        self._status.set("已停止。")

    # ---- 回调 ----
    def _show_invite(self, code: str):
        self.root.after(0, lambda: self._set_invite(code))

    def _set_invite(self, code: str):
        self._invite_txt.config(state=tk.NORMAL)
        self._invite_txt.delete("1.0", tk.END)
        # 每行最多 5 组，便于复制
        groups = code.split("-")
        lines = ["-".join(groups[i:i + 5]) for i in range(0, len(groups), 5)]
        self._invite_txt.insert("1.0", "\n".join(lines))
        self._invite_txt.config(state=tk.DISABLED)
        self._status.set("邀请码已生成，等待对方连接…")

    def _copy_invite(self):
        try:
            txt = self._invite_txt.get("1.0", tk.END).replace("\n", "").replace(" ", "")
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
            self._status.set("已复制到剪贴板。")
        except Exception:
            pass

    def _send_file(self):
        path = filedialog.askopenfilename(title="选择要发送的文件")
        if not path:
            return
        if not self.ses:
            return
        self._status.set(f"发送中：{path.split('/')[-1]} …")
        import threading
        def _do():
            try:
                self.ses.send_file(path)
                self.root.after(0, lambda: self._status.set(f"已发送：{path}"))
            except Exception as e:
                self.root.after(0, lambda: self._status.set(f"发送失败：{e}"))
        threading.Thread(target=_do, daemon=True).start()

    def _on_file_done(self, path):
        self.root.after(0, lambda: self._status.set(
            f"已接收文件：{path}" if path else "文件接收但校验失败"))

    # ---- 屏幕帧渲染（主线程轮询 queue）----
    def _poll(self):
        try:
            while True:
                w, h, jpg = self._frame_q.get_nowait()
                img = Image.open(io.BytesIO(jpg))
                self._render(img, w, h)
        except queue.Empty:
            pass
        self.root.after(40, self._poll)

    def _render(self, img, w, h):
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        if img.size != (cw, ch):
            img = img.resize((cw, ch), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        self._canvas.create_image(cw // 2, ch // 2, image=self._photo)
        self._canvas.image = self._photo  # 防 GC

    # ---- 输入事件转发（仅 join 模式）----
    def _bind_input(self):
        c = self._canvas
        c.bind("<Motion>", self._ev_motion)
        c.bind("<ButtonPress-1>", lambda e: self._btn_press(1))
        c.bind("<ButtonRelease-1>", lambda e: self._btn_release(1))
        c.bind("<ButtonPress-3>", lambda e: self._btn_press(2))
        c.bind("<ButtonRelease-3>", lambda e: self._btn_release(2))
        c.bind("<ButtonPress-2>", lambda e: self._btn_press(4))
        c.bind("<ButtonRelease-2>", lambda e: self._btn_release(4))
        c.bind("<MouseWheel>", self._ev_wheel)
        self.root.bind("<KeyPress>", self._ev_key)
        self.root.bind("<KeyRelease>", self._ev_key_release)

    def _norm_xy(self, e):
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        return e.x / cw, e.y / ch

    def _send_mouse(self, x, y, wheel=0):
        if isinstance(self.ses, session.JoinSession):
            self.ses.send_mouse(x, y, self._btn, wheel)

    def _ev_motion(self, e):
        x, y = self._norm_xy(e)
        self._send_mouse(x, y)

    def _btn_press(self, bit):
        self._btn |= bit
        if self.ses:
            self._send_mouse(*self._last_xy())

    def _btn_release(self, bit):
        self._btn &= ~bit
        if self.ses:
            self._send_mouse(*self._last_xy())

    def _last_xy(self):
        x = self._canvas.winfo_pointerx() - self._canvas.winfo_rootx()
        y = self._canvas.winfo_pointery() - self._canvas.winfo_rooty()
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        return x / cw, y / ch

    def _ev_wheel(self, e):
        if isinstance(self.ses, session.JoinSession):
            self.ses.send_mouse(*self._last_xy(), 1 if e.delta > 0 else -1)

    def _ev_key(self, e):
        if isinstance(self.ses, session.JoinSession):
            self.ses.send_key(e.keycode, True)

    def _ev_key_release(self, e):
        if isinstance(self.ses, session.JoinSession):
            self.ses.send_key(e.keycode, False)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
