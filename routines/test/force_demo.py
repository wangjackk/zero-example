"""ForceDemo -- force_start 抢占 demo(兄弟间横向 force).

先 start echo 占 output,再 force_start output2 抢过来----kernel 驱逐 echo
(cascade stop,reason='force')后 output2 起来.验证兄弟间横向 force:output2
没拿到 echo 的 handle,靠 force 走 kernel 找占住者驱逐.
"""
from typing import Any, Dict

from routine import Routine


class ForceDemo(Routine):
    """force_start 抢占 demo:先 start echo 占 output,再 force_start output2
    抢过来----kernel 驱逐 echo(cascade stop,reason='force')后 output2 起来.

    验证兄弟间横向 force(echo / output2 都是 ForceDemo 的子):
    output2 没拿到 echo 的 handle,靠 force 走 kernel 找占住者驱逐.
    """

    meta = {'description': 'force_start 抢占 demo(兄弟间横向 force)'}
    # is_passive = True

    async def run(self, kwargs: Dict[str, Any]):
        echo = await self.submit('test_echo', {'text': 'evicted'})
        out2 = await self.submit('output2', {'text': 'winner'})
        await echo.start()  # echo 占住 output
        self._logger.info('echo started, holds output')

        # try_start 探测:冲突失败但保留 handle(区别于 start 全有或全无----失败清掉).
        # 用 try_start 不用 start:start 失败会把 handle 清掉,后面 force_start 找不到.
        err = await out2.try_start()
        if err:
            self._logger.info('output2 try_start failed (expected, echo holds output): %s', err)

        # force_start:驱逐 echo 后 output2 起来(handle 仍在,try_start 保留了)
        self._logger.info('output2 force_start')
        err = await out2.force_start()
        if err:
            self._logger.warning('output2 force_start failed: %s', err)
            return
        self._logger.info('output2 force_start ok (echo evicted)')

        # output2 跑完拿 result;echo 被驱逐(stopped reason=force,对父透明不抛)
        result = await out2
        self._logger.info('output2 result: %s', result)
        try:
            echo_result = await echo
            self._logger.info('echo result (evicted, transparent): %s', echo_result)
        except RuntimeError as e:
            self._logger.info('echo wait raised: %s', e)
