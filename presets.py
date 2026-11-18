"""Meta division template presets for HoI4 1.19.5.0+."""

from typing import Dict
from .division import DivisionTemplate


PRESETS: Dict[str, DivisionTemplate] = {
    "inf_18w_hold": DivisionTemplate(
        name="18w Оборонительная пехота (9/0 + Сапёры/ПВО/Арта)",
        battalions={"infantry": 9},
        support=["engineer", "artillery", "anti_air"],
        regimental=["fire_support"],
        tech_year=1940,
        doctrine={"grand": "grand_battleplan", "milestones": [True, True, True, True]},
    ),
    "inf_15w_meta": DivisionTemplate(
        name="15w Мета-пехота 1.19 (6/1)",
        battalions={"infantry": 6, "artillery_brigade": 1},
        support=["engineer", "artillery", "anti_air", "recon"],
        regimental=["fire_support"],
        tech_year=1940,
        doctrine={"grand": "superior_firepower", "milestones": [True, True, True, True]},
    ),
    "inf_mass_assault": DivisionTemplate(
        name="Массовый штурм 1.19+ (10 пехоты = 18w)",
        battalions={"infantry": 10},
        support=["engineer", "artillery", "anti_air", "field_hospital", "logistics_company"],
        regimental=["fire_support", "anti_tank_battery"],
        tech_year=1942,
        doctrine={"grand": "mass_assault", "milestones": [True, True, True, True]},
    ),
    "inf_9_3_shock": DivisionTemplate(
        name="27w Ударная пехота (9/3)",
        battalions={"infantry": 9, "artillery_brigade": 3},
        support=["engineer", "artillery", "anti_air", "logistics_company", "signal_company"],
        regimental=["field_guns"],
        tech_year=1940,
        doctrine={"grand": "superior_firepower", "milestones": [True, True, True, True]},
    ),
    "tank_30w_med": DivisionTemplate(
        name="30w Средние танки + Мех (8 СТ / 7 Мех)",
        battalions={"medium_armor": 8, "mechanized": 7},
        support=["armored_engineer", "light_tank_recon", "anti_air", "logistics_company", "signal_company"],
        regimental=["medium_sp_anti_air_support"],
        tech_year=1942,
        doctrine={"grand": "new_mobile_warfare", "milestones": [True, True, True, True]},
    ),
    "tank_36w_heavy": DivisionTemplate(
        name="36w Тяжёлый прорыв (10 ТТ / 8 Мех)",
        battalions={"heavy_armor": 10, "mechanized": 8},
        support=["assault_engineer", "light_tank_recon", "logistics_company", "maintenance_company", "signal_company"],
        regimental=["heavy_tank_destroyer_support", "medium_sp_anti_air_support"],
        tech_year=1943,
        doctrine={"grand": "new_mobile_warfare", "milestones": [True, True, True, True]},
    ),
    "mountaineer_25w": DivisionTemplate(
        name="25w Горнострелки (8 Горн / 3 Арта)",
        battalions={"mountaineers": 8, "artillery_brigade": 3},
        support=["engineer", "artillery", "anti_air", "logistics_company", "recon"],
        regimental=["fire_support"],
        tech_year=1940,
        doctrine={"grand": "grand_battleplan", "milestones": [True, True, True, True]},
    ),
}
