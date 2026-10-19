"""文件传输：分块流式发送 + SHA256 校验。复用 Channel 的加密通道。"""
from __future__ import annotations

import hashlib
import os
import struct

from . import protocol as P

CHUNK = 60000  # 每片字节数（留余量给帧头/nonce/tag）


class Sender:
    """发送一个文件。可在独立线程调用 run()。"""

    def __init__(self, channel, path, file_id: int = 1, progress=None):
        self.channel = channel
        self.path = path
        self.file_id = file_id
        self.progress = progress  # callable(sent, total)

    def run(self) -> None:
        size = os.path.getsize(self.path)
        name = os.path.basename(self.path).encode("utf-8")
        meta = struct.pack(">BH", self.file_id, len(name)) + name + struct.pack(">Q", size)
        self.channel.send(P.FILE_META, meta)
        sha = hashlib.sha256()
        sent = 0
        with open(self.path, "rb") as f:
            while True:
                data = f.read(CHUNK)
                if not data:
                    break
                sha.update(data)
                frame = struct.pack(">BQ", self.file_id, sent) + data
                self.channel.send(P.FILE_DATA, frame)
                sent += len(data)
                if self.progress:
                    try:
                        self.progress(sent, size)
                    except Exception:
                        pass
        self.channel.send(P.FILE_END, struct.pack(">B", self.file_id) + sha.digest())


class Receiver:
    """接收端：通过 install() 注册到 channel.on(FILE_*)。"""

    def __init__(self, destdir: str = ".", done=None, progress=None):
        self.destdir = destdir
        self.done = done           # callable(path_or_None)  None=校验失败
        self.progress = progress   # callable(got, total)
        self._files: dict[int, list] = {}

    def install(self, channel) -> None:
        channel.on(P.FILE_META, self._on_meta)
        channel.on(P.FILE_DATA, self._on_data)
        channel.on(P.FILE_END, self._on_end)

    def _on_meta(self, body: bytes, addr) -> None:
        fid, = struct.unpack_from(">B", body, 0)
        nlen, = struct.unpack_from(">H", body, 1)
        name = body[3:3 + nlen].decode("utf-8", "replace")
        size, = struct.unpack_from(">Q", body, 3 + nlen)
        name = os.path.basename(name) or f"huocatdesk_recv_{fid}"
        path = os.path.join(self.destdir, name)
        os.makedirs(self.destdir, exist_ok=True)
        self._files[fid] = [path, open(path, "wb"), hashlib.sha256(), size, 0]

    def _on_data(self, body: bytes, addr) -> None:
        fid, = struct.unpack_from(">B", body, 0)
        off, = struct.unpack_from(">Q", body, 1)
        data = body[9:]
        st = self._files.get(fid)
        if not st:
            return
        st[1].seek(off)
        st[1].write(data)
        st[2].update(data)
        st[4] += len(data)
        if self.progress:
            try:
                self.progress(st[4], st[3])
            except Exception:
                pass

    def _on_end(self, body: bytes, addr) -> None:
        fid, = struct.unpack_from(">B", body, 0)
        digest = body[1:33]
        st = self._files.pop(fid, None)
        if not st:
            return
        path, fh, sha, size, got = st
        fh.close()
        ok = (sha.digest() == digest) and (got == size)
        if self.done:
            try:
                self.done(path if ok else None)
            except Exception:
                pass
