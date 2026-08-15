from .list_music import ListMusic
from .play_music import PlayMusic

from routine import Routines

def get_routines() -> Routines:
    rs = Routines()
    rs.register(PlayMusic, ListMusic)

    return rs

