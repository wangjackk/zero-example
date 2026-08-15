"""query_weather - 查询指定城市的天气(调用高德 API,带缓存).

新框架风格:``on_created`` 不占模块,``run`` 查询返回摘要.返回 ``{'for_llm': ...}``
让 react agent 把结果喂回 LLM(区别于 output 说话类不反馈).
"""
from typing import Any, ClassVar, Dict, Optional

from pydantic import BaseModel, Field

from routine import Routine

from .query_weather_base import (
    query_weather,
    resolve_adcode,
    format_live,
    format_forecast,
    get_reporttime,
)


class QueryWeatherInput(BaseModel):
    city: str = Field(default='北京', description='城市名称 (如 "北京" / "深圳" / "南山区")')
    extensions: str = Field(
        default='base',
        description='base=实况天气, all=未来 3~4 天预报',
    )


class QueryWeatherOutput(BaseModel):
    summary: str = Field(description='天气摘要文本 (实况或预报); 失败时为错误描述')


class QueryWeather(Routine):
    """查询指定城市的实况或预报天气.

    city: 城市名称(如"北京"/"深圳"/"南山区")
    extensions: base=实况天气, all=未来 3~4 天预报
    """

    meta: ClassVar[Dict[str, Any]] = {
        'description': '查询指定城市的实况 (base) 或未来 3~4 天预报 (all) 天气, 调用高德 API 并带缓存.',
        'input_schema': QueryWeatherInput.model_json_schema(),
        'output_schema': QueryWeatherOutput.model_json_schema(),
    }

    async def run(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        city = kwargs.get('city', '北京')
        extensions = kwargs.get('extensions', 'base')
        try:
            adcode = resolve_adcode(city)
        except ValueError as e:
            self._logger.warning(f'query_weather: 城市解析失败 - {e}')
            return {'city': city, 'for_llm': f'城市"{city}"解析失败: {e}'}

        data, cached = await query_weather(city, extensions)

        if data.get('status') != '1':
            self._logger.warning(f'query_weather: API 错误 - {data}')
            err = f'{data.get("info")} (code={data.get("infocode")})'
            return {'city': city, 'adcode': adcode, 'for_llm': f'查询失败: {err}'}

        summary = format_live(data) if extensions == 'base' else format_forecast(data)
        reporttime = get_reporttime(data)
        self._logger.info(
            f'query_weather[{"cache" if cached else "live"}] {city}: '
            f'{summary.splitlines()[0]}'
        )
        # for_llm 喂回 LLM;其余字段(adcode/cached/reporttime)供诊断但不单独反馈.
        return {
            'city': city,
            'adcode': adcode,
            'extensions': extensions,
            'cached': cached,
            'reporttime': reporttime,
            'for_llm': summary,
        }
