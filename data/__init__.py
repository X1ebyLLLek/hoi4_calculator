"""Game data modules for HoI4 1.19.4+."""

from .equipment import EQUIPMENT_DB, Equipment, get_equipment_by_category, get_default_equipment_for_year
from .battalions import BATTALION_DB, Battalion
from .support_companies import SUPPORT_DB, SupportCompany
from .doctrines_terrain import DOCTRINE_DB, TERRAIN_DB, TACTICS_DB, LandDoctrine, Terrain, CombatTactic

__all__ = [
    "EQUIPMENT_DB",
    "Equipment",
    "get_equipment_by_category",
    "get_default_equipment_for_year",
    "BATTALION_DB",
    "Battalion",
    "SUPPORT_DB",
    "SupportCompany",
    "DOCTRINE_DB",
    "TERRAIN_DB",
    "TACTICS_DB",
    "LandDoctrine",
    "Terrain",
    "CombatTactic",
]
