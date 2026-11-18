"""Meta division template presets for HoI4 1.19.4+."""

from typing import Dict
from ..engine.calculator import DivisionTemplate


PRESET_TEMPLATES: Dict[str, DivisionTemplate] = {
    "inf_18w_hold": DivisionTemplate(
        name="18w Оборонительная пехота (9/0 + Сапёры/ПВО/Арта)",
        battalions={"infantry": 9},
        support_companies=["engineer", "support_artillery", "support_anti_air"],
        regimental_supports=["reg_heavy_weapons"],
        tech_year=1940,
        support_tech_level=2,
        doctrine_id="grand_battleplan",
    ),
    "inf_15w_meta": DivisionTemplate(
        name="15w Мета-пехота 1.19.4 (6/1)",
        battalions={"infantry": 6, "artillery": 1},
        support_companies=["engineer", "support_artillery", "support_anti_air", "recon_cav"],
        regimental_supports=["reg_heavy_weapons"],
        tech_year=1940,
        support_tech_level=2,
        doctrine_id="superior_firepower",
    ),
    "inf_mass_assault": DivisionTemplate(
        name="Массовый штурм 1.19+ (12 пехоты = 21.6w)",
        battalions={"infantry": 12},
        support_companies=["engineer", "support_artillery", "support_anti_air", "field_hospital", "logistics"],
        regimental_supports=["reg_heavy_weapons", "reg_anti_tank"],
        tech_year=1942,
        support_tech_level=3,
        doctrine_id="mass_assault",
    ),
    "inf_9_3_shock": DivisionTemplate(
        name="27w Ударная пехота (9/3)",
        battalions={"infantry": 9, "artillery": 3},
        support_companies=["engineer", "support_artillery", "support_anti_air", "logistics", "signal"],
        regimental_supports=["reg_heavy_weapons"],
        tech_year=1940,
        support_tech_level=2,
        doctrine_id="superior_firepower",
    ),
    "tank_30w_med": DivisionTemplate(
        name="30w Средние танки + Мех (8 Танков / 7 Мех)",
        battalions={"medium_tank": 8, "mechanized": 7},
        support_companies=["armored_engineer", "recon_light_tank", "support_anti_air", "logistics", "signal"],
        regimental_supports=["reg_spaa"],
        tech_year=1940,
        support_tech_level=2,
        doctrine_id="mobile_warfare",
    ),
    "tank_36w_heavy": DivisionTemplate(
        name="36w Тяжёлый прорыв (10 Тяж. танков / 8 Мех)",
        battalions={"heavy_tank": 10, "mechanized": 8},
        support_companies=["assault_engineer", "recon_light_tank", "logistics", "maintenance", "signal"],
        regimental_supports=["reg_medium_td", "reg_spaa"],
        tech_year=1942,
        support_tech_level=3,
        doctrine_id="mobile_warfare",
    ),
    "mountaineer_25w": DivisionTemplate(
        name="25w Горнострелки (8 Горн / 3 Арта)",
        battalions={"mountaineers": 8, "artillery": 3},
        support_companies=["engineer", "support_artillery", "support_anti_air", "logistics", "recon_cav"],
        regimental_supports=["reg_heavy_weapons"],
        tech_year=1940,
        support_tech_level=2,
        doctrine_id="grand_battleplan",
    ),
}
