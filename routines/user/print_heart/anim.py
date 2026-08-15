"""心形动画子进程入口 ---- 极薄,只做三件事:

1. 把自己所在目录塞进 ``sys.path``,让 ``gui`` 子包能被绝对导入
   (子进程以脚本方式启动时没有 package 上下文).
2. 解析 ``duration`` 参数.
3. 交给 ``gui.app.run`` 启动 Qt 事件循环.

也支持 ``python anim.py [duration]`` 直接调试.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gui.app import run  # noqa: E402

DEFAULT_DURATION = 5.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('duration', nargs='?', type=float, default=DEFAULT_DURATION,
                        help='animation duration in seconds')
    args = parser.parse_args()
    sys.exit(run(max(0.3, float(args.duration))))


if __name__ == '__main__':
    main()
