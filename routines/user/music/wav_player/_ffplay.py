"""FFplay 后端 ---- 通过外部 ffplay 子进程播音.

优点: 格式兼容性好 (mp3/wav/flac 一把梭),靠子进程隔离不占主循环.
缺点: 需要系统里有 ffplay 可执行文件.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Optional

from ._base import WavPlayer


_TERMINATE_GRACE = 1.0


class FFplayPlayer(WavPlayer):
    """调 ffplay -nodisp -autoexit 走子进程播放."""

    def __init__(self, logger):
        super().__init__(logger)
        self._proc: asyncio.subprocess.Process | None = None
        # stop() 被调用过 → play() 里不要把 terminate 导致的非零退出码当错误报
        self._stopping = False

    @staticmethod
    def is_available() -> bool:
        return shutil.which('ffplay') is not None

    async def play(self, file_path: Path, duration: Optional[float] = None) -> None:
        args = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet']
        if duration is not None:
            args += ['-t', str(duration)]
        args.append(str(file_path))

        self._stopping = False
        self._proc = await asyncio.create_subprocess_exec(*args)
        self._logger.info(f'wav_player[ffplay]: pid={self._proc.pid} file={file_path}')

        try:
            returncode = await self._proc.wait()
        except asyncio.CancelledError:
            # 外层 task 被 cancel → 顺手把子进程杀掉再抛
            await self._force_kill()
            raise

        if self._stopping:
            # stop() 主动 terminate 导致的非零退出码是预期内的
            return
        if returncode != 0:
            raise RuntimeError(f'ffplay exited with code {returncode}')

    async def stop(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        self._stopping = True
        self._logger.info(f'wav_player[ffplay]: stop -> terminate pid={proc.pid}')
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_GRACE)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass

    async def _force_kill(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.kill()
        except ProcessLookupError:
            return
        try:
            await proc.wait()
        except Exception:
            pass
