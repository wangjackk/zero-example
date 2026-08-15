"""greet_by_time -- 根据当前时间段返回一句中文问候语.

根据当前小时判断时段:早晨/上午/中午/下午/傍晚/晚上/深夜,
可选接收 name 参数,把名字嵌进问候里.
"""
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field

from routine import Routine


class GreetByTimeInput(BaseModel):
    """greet_by_time 输入:可选 name."""

    name: str = Field(
        default="",
        description="可选的称呼或名字,为空则用通用问候",
    )


class GreetByTimeOutput(BaseModel):
    greeting: str = Field(
        default="",
        description="生成的中文问候语",
    )
    period: str = Field(
        default="",
        description="时段名称:早晨/上午/中午/下午/傍晚/晚上/深夜",
    )
    hour: int = Field(
        default=0,
        description="当前小时(24 小时制)",
    )


def _period_of_hour(hour: int) -> str:
    if 5 <= hour < 9:
        return "早晨"
    if 9 <= hour < 11:
        return "上午"
    if 11 <= hour < 13:
        return "中午"
    if 13 <= hour < 17:
        return "下午"
    if 17 <= hour < 19:
        return "傍晚"
    if 19 <= hour < 23:
        return "晚上"
    return "深夜"


def _build_greeting(period: str, name: str) -> str:
    templates = {
        "早晨": [
            "早呀，{name}新的一天开始啦～",
            "{name}早上好，今天也要元气满满哦。",
            "早安{name}，记得吃早饭呀。",
        ],
        "上午": [
            "{name}上午好，今天状态怎么样？",
            "上午好呀{name}，工作顺利吗？",
            "{name}上午好，再坚持一会儿就到午饭啦。",
        ],
        "中午": [
            "{name}中午好，记得按时吃饭哦。",
            "中午好呀{name}，午休了吗？",
            "{name}午安，吃完午饭可以小憩一下。",
        ],
        "下午": [
            "{name}下午好，要不要来杯咖啡提提神？",
            "下午好呀{name}，今天过半啦。",
            "{name}下午好，继续加油呀。",
        ],
        "傍晚": [
            "傍晚啦{name}，工作差不多可以收个尾了～",
            "{name}傍晚好，天边的颜色好看吗？",
            "傍晚好呀{name}，准备下班/放学了吗？",
        ],
        "晚上": [
            "{name}晚上好，今天过得充实吗？",
            "晚上好呀{name}，放松一下吧～",
            "{name}晚上好，有事随时找我。",
        ],
        "深夜": [
            "这么晚还没睡呀{name}，早点休息哦。",
            "{name}夜深啦，注意身体，别熬太晚。",
            "深夜好{name}，忙完这一阵就去睡吧。",
        ],
    }

    now_minute = datetime.now().minute
    bucket = templates.get(period, templates["下午"])
    template = bucket[now_minute % len(bucket)]

    if name:
        return template.format(name=name)
    text = template.format(name="")
    text = text.replace("，，", "，").replace("。。", "。")
    text = text.lstrip("，, ")
    return text


class GreetByTime(Routine):
    """根据当前时间段返回一句中文问候语."""

    name = "greet_by_time"

    meta = {
        "description": "根据当前时间段(早晨/上午/中午/下午/傍晚/晚上/深夜)生成一句自然的中文问候语，可选附带称呼。",
        "input_schema": GreetByTimeInput.model_json_schema(),
        "output_schema": GreetByTimeOutput.model_json_schema(),
    }

    async def run(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        inp = GreetByTimeInput.model_validate(kwargs)
        now = datetime.now()
        hour = now.hour
        period = _period_of_hour(hour)
        greeting = _build_greeting(period, inp.name.strip())

        self._logger.info(
            "greet_by_time: period=%s hour=%s name=%r",
            period, hour, inp.name,
        )

        return {
            "greeting": greeting,
            "period": period,
            "hour": hour,
        }
