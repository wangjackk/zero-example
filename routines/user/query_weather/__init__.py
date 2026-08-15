from .query_weather import QueryWeather

from routine import Routines

def get_routines() -> Routines:
    rs = Routines()
    rs.register(QueryWeather)
    return rs
