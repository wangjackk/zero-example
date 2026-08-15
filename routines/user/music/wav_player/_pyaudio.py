"""PyAudio 后端 ---- 纯 Python 读 WAV + PortAudio 出声.

只支持 PCM .wav (用 stdlib ``wave`` 模块解的).非 wav 格式走到这里会 raise.
pyaudio 是同步阻塞 API, 所以整个播放循环塞到后台线程里, 用 ``threading.Event``
和 asyncio 协调停止.
"""

import asyncio
import threading
import time
import wave
from pathlib import Path
from typing import Optional

from ._base import WavPlayer


_CHUNK_FRAMES = 1024
_STOP_GRACE = 1.0


class PyAudioPlayer(WavPlayer):
    """用 pyaudio + stdlib wave 在线程里播 PCM wav."""

    def __init__(self, logger):
        super().__init__(logger)
        self._stop_event: Optional[threading.Event] = None
        self._play_future: Optional[asyncio.Future] = None

    @staticmethod
    def is_available() -> bool:
        try:
            import pyaudio  # noqa: F401
        except Exception:
            return False
        return True

    async def play(self, file_path: Path, duration: Optional[float] = None) -> None:
        if file_path.suffix.lower() != '.wav':
            # pyaudio 后端只认 PCM wav.想听 mp3/flac 请装 ffplay.
            raise RuntimeError(
                f'pyaudio backend only supports .wav, got {file_path.suffix} '
                f'({file_path.name}); install ffplay for other formats'
            )

        import pyaudio  # 延迟 import, 避免 import 期拖慢整个模块加载

        self._stop_event = threading.Event()
        stop_event = self._stop_event
        logger = self._logger

        def _play_sync() -> None:
            pa = pyaudio.PyAudio()
            wf = None
            stream = None
            try:
                wf = wave.open(str(file_path), 'rb')
                stream = pa.open(
                    format=pa.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True,
                )
                logger.info(
                    f'wav_player[pyaudio]: sr={wf.getframerate()} '
                    f'ch={wf.getnchannels()} width={wf.getsampwidth()} file={file_path}'
                )

                deadline = (time.monotonic() + duration) if duration is not None else None
                while not stop_event.is_set():
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    data = wf.readframes(_CHUNK_FRAMES)
                    if not data:
                        break
                    stream.write(data)
            finally:
                if stream is not None:
                    try:
                        stream.stop_stream()
                    except Exception:
                        pass
                    try:
                        stream.close()
                    except Exception:
                        pass
                if wf is not None:
                    try:
                        wf.close()
                    except Exception:
                        pass
                try:
                    pa.terminate()
                except Exception:
                    pass

        loop = asyncio.get_running_loop()
        self._play_future = loop.run_in_executor(None, _play_sync)
        try:
            await asyncio.shield(self._play_future)
        except asyncio.CancelledError:
            # 后台线程不能强制中断, 先通知它退出循环再等它收尾 (有限时间, 不 hang)
            stop_event.set()
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._play_future), timeout=_STOP_GRACE
                )
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
            raise

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        fut = self._play_future
        if fut is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(fut), timeout=_STOP_GRACE)
        except Exception:
            pass
