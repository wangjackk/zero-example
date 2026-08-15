"""query_weather_base -- 高德天气 API 调用 + 带 TTL 的本地缓存

文档: https://lbs.amap.com/api/webservice/guide/api-advanced/weatherinfo

- 实况天气每小时更新多次 → TTL 30 分钟
- 预报天气每天在 8/11/18 点前后更新 → 缓存到下一个更新时刻 +30min 缓冲
- 缓存以 JSON 形式持久化到 weather_cache.json,跨进程生效

CLI 用法:
    python query_weather_base.py                   # 默认查北京实况
    python query_weather_base.py 上海              # 按城市名查实况
    python query_weather_base.py 南山区 all        # 查区级预报
    python query_weather_base.py 310000 base       # 直接用 adcode
    python query_weather_base.py 北京 base --force # 跳过缓存强制刷新
"""

import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Tuple

import httpx


KEY = 'f9c35efab03e9995bb91fdaaa041e7f3'
WEATHER_URL = 'https://restapi.amap.com/v3/weather/weatherInfo'

_HERE = Path(__file__).parent
_ADCODE_JSON = _HERE / 'adcode.json'
_CACHE_FILE = _HERE / 'weather_cache.json'

# 常见行政后缀,用户输入 "北京" 时自动尝试 "北京市"
_SUFFIXES = ['市', '省', '县', '区', '自治区', '自治州', '地区', '特别行政区', '盟', '旗']

# 预报天气官方更新时间(文档: 分别在 8,11,18 点左右更新)
_FORECAST_UPDATE_HOURS = [8, 11, 18]
# 缓冲分钟数:更新时刻之后多等几分钟再视为"新数据已就绪"
_FORECAST_UPDATE_BUFFER = timedelta(minutes=30)

# 实况天气 TTL:文档说"每小时更新多次",30 分钟是合理的保鲜期
_LIVE_TTL = timedelta(minutes=30)

_adcode_cache: Optional[Dict[str, str]] = None
_mem_cache: Dict[str, dict] = {}
_cache_loaded = False
_cache_lock = asyncio.Lock()


def _load_adcode() -> Dict[str, str]:
    global _adcode_cache
    if _adcode_cache is None:
        with open(_ADCODE_JSON, 'r', encoding='utf-8') as f:
            _adcode_cache = json.load(f)
    return _adcode_cache


def resolve_adcode(city: str) -> str:
    """城市名 -> adcode.

    匹配策略:
      1. 纯数字 -> 直接当 adcode 使用
      2. 精确匹配
      3. 补后缀(市/省/区/...)后精确匹配
      4. 唯一前缀匹配(e.g. "西双版纳" -> "西双版纳傣族自治州")
    """
    city = city.strip()
    if city.isdigit():
        return city

    table = _load_adcode()

    if city in table:
        return table[city]

    for suf in _SUFFIXES:
        key = city + suf
        if key in table:
            return table[key]

    hits = [k for k in table if k.startswith(city)]
    if len(hits) == 1:
        return table[hits[0]]
    if len(hits) > 1:
        hits.sort(key=len)
        raise ValueError(
            f'"{city}" 匹配到多个城市: {hits[:8]}{"..." if len(hits) > 8 else ""},请写完整名'
        )

    raise ValueError(f'未找到城市 "{city}",请传入完整城市名或 adcode')


# ---------------- 缓存 ----------------

def _load_cache() -> None:
    global _mem_cache, _cache_loaded
    if _cache_loaded:
        return
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
                _mem_cache = json.load(f)
        except Exception:
            _mem_cache = {}
    _cache_loaded = True


def _save_cache() -> None:
    try:
        with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_mem_cache, f, ensure_ascii=False, separators=(',', ':'))
    except Exception:
        pass


def _next_forecast_update(after: datetime) -> datetime:
    """返回 after 之后(不含)的下一个预报更新时刻(已加缓冲)"""
    day = after.date()
    for h in _FORECAST_UPDATE_HOURS:
        t = datetime.combine(day, time(h, 0)) + _FORECAST_UPDATE_BUFFER
        if t > after:
            return t
    return datetime.combine(day + timedelta(days=1), time(_FORECAST_UPDATE_HOURS[0], 0)) + _FORECAST_UPDATE_BUFFER


def _cache_valid(entry: dict, now: datetime) -> bool:
    """判断缓存条目是否仍然有效"""
    try:
        fetched_at = datetime.fromisoformat(entry['fetched_at'])
    except Exception:
        return False
    if entry.get('extensions') == 'base':
        return now - fetched_at < _LIVE_TTL
    next_update = _next_forecast_update(fetched_at)
    return now < next_update


# ---------------- API 调用 ----------------

async def _fetch(adcode: str, extensions: str, key: Optional[str]) -> dict:
    params = {
        'key': key or KEY,
        'city': adcode,
        'extensions': extensions,
        'output': 'JSON',
    }
    # trust_env=False: 高德是国内 API, 强制直连, 避免继承 shell / Windows 系统代理
    # (VPN / Clash 之类会把 127.0.0.1:7890 写进系统代理, 代理进程不在时会挂在 TLS)
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        resp = await client.get(WEATHER_URL, params=params)
        resp.raise_for_status()
        return resp.json()


async def query_weather(
    city: str = '北京',
    extensions: str = 'base',
    key: Optional[str] = None,
    force_refresh: bool = False,
) -> Tuple[dict, bool]:
    """查询天气(带缓存).

    Args:
        city: 城市名或 adcode
        extensions: base=实况, all=预报
        key: 自定义 key;默认用模块 KEY
        force_refresh: True 时跳过缓存直接请求

    Returns:
        (api_json, cached) ---- cached 表示本次是否命中缓存
    """
    adcode = resolve_adcode(city)
    cache_key = f'{adcode}:{extensions}'
    now = datetime.now()

    async with _cache_lock:
        _load_cache()
        if not force_refresh and cache_key in _mem_cache:
            entry = _mem_cache[cache_key]
            if _cache_valid(entry, now):
                return entry['data'], True

        data = await _fetch(adcode, extensions, key)
        # 只缓存成功响应
        if data.get('status') == '1':
            _mem_cache[cache_key] = {
                'data': data,
                'fetched_at': now.isoformat(timespec='seconds'),
                'extensions': extensions,
                'adcode': adcode,
            }
            _save_cache()
        return data, False


def clear_cache(adcode: Optional[str] = None, extensions: Optional[str] = None) -> int:
    """清缓存.不传参清全部;只传 adcode 清该城市;全传清单条.返回清除条数."""
    _load_cache()
    if adcode is None:
        n = len(_mem_cache)
        _mem_cache.clear()
        _save_cache()
        return n
    keys = []
    for k in list(_mem_cache.keys()):
        ad, ext = k.split(':', 1)
        if ad == adcode and (extensions is None or ext == extensions):
            keys.append(k)
    for k in keys:
        del _mem_cache[k]
    _save_cache()
    return len(keys)


# ---------------- 格式化 ----------------

# 高德 API 的 week 字段:1=Mon ... 7=Sun(ISO 格式)
_WEEK_CN = {'1': '一', '2': '二', '3': '三', '4': '四', '5': '五', '6': '六', '7': '日'}


def _loc(province: str, city: str) -> str:
    """拼省市;直辖市 province == city 的"北京"+"北京市"会重复,去冗余."""
    if not province or city.startswith(province):
        return city
    return f'{province}{city}'


def format_live(data: dict) -> str:
    """实况单行,紧凑版."""
    if data.get('status') != '1' or not data.get('lives'):
        return f'[错误] {data.get("info")} (code={data.get("infocode")})'
    live = data['lives'][0]
    return (
        f"{_loc(live['province'], live['city'])} "
        f"{live['weather']} {live['temperature']}° "
        f"{live['winddirection']}风{live['windpower']} "
        f"湿度{live['humidity']}% "
        f"({live['reporttime']})"
    )


def format_forecast(data: dict) -> str:
    """预报表格版,markdown 管道表,token 约比原来省一半."""
    if data.get('status') != '1' or not data.get('forecasts'):
        return f'[错误] {data.get("info")} (code={data.get("infocode")})'
    fc = data['forecasts'][0]
    lines = [f"{_loc(fc['province'], fc['city'])} 预报 (发布 {fc['reporttime']})",
             '日期|周|白天|夜间|风']
    for cast in fc['casts']:
        date = cast['date'][5:]  # 去掉年份前缀,只保留 MM-DD
        wk = _WEEK_CN.get(str(cast['week']), cast['week'])
        day = f"{cast['dayweather']}{cast['daytemp']}°"
        night = f"{cast['nightweather']}{cast['nighttemp']}°"
        # 昼夜风向/风力一致时合并,不一致时分开
        if cast['daywind'] == cast['nightwind'] and cast['daypower'] == cast['nightpower']:
            wind = f"{cast['daywind']}{cast['daypower']}"
        else:
            wind = f"昼{cast['daywind']}{cast['daypower']}/夜{cast['nightwind']}{cast['nightpower']}"
        lines.append(f'{date}|{wk}|{day}|{night}|{wind}')
    return '\n'.join(lines)


def get_reporttime(data: dict) -> Optional[str]:
    """统一取返回数据里的 reporttime"""
    if data.get('lives'):
        return data['lives'][0].get('reporttime')
    if data.get('forecasts'):
        return data['forecasts'][0].get('reporttime')
    return None


# ---------------- CLI ----------------

async def main():
    args = [a for a in sys.argv[1:] if a != '--force']
    force = '--force' in sys.argv
    city = args[0] if len(args) > 0 else '北京'
    extensions = args[1] if len(args) > 1 else 'base'

    adcode = resolve_adcode(city)
    print(f'>>> city={city} adcode={adcode} extensions={extensions} force={force}')
    data, cached = await query_weather(city, extensions, force_refresh=force)
    print(f'--- {"命中缓存" if cached else "实时请求"} reporttime={get_reporttime(data)} ---')
    if extensions == 'base':
        print(format_live(data))
    else:
        print(format_forecast(data))


def _regen_adcode_json():
    """从 AMap_adcode_citycode.xlsx 重新生成 adcode.json(需要 openpyxl)"""
    import openpyxl

    xlsx = _HERE / 'AMap_adcode_citycode.xlsx'
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb['Sheet1']
    mapping: Dict[str, str] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        name, adcode = row[0], row[1]
        if not name or adcode in (None, '', r'\N'):
            continue
        ad = str(adcode).strip()
        if not ad.isdigit():
            continue
        mapping[str(name).strip()] = ad
    with open(_ADCODE_JSON, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, separators=(',', ':'))
    print(f'wrote {len(mapping)} entries to {_ADCODE_JSON}')


if __name__ == '__main__':
    asyncio.run(main())
