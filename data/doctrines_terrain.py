"""HoI4 1.19.4+ Land Doctrines, Terrain Widths/Modifiers, and Combat Tactics."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class LandDoctrine:
    id: str
    name: str
    name_ru: str
    infantry_width_delta: float = 0.0
    infantry_org_bonus: float = 0.0
    armor_org_bonus: float = 0.0
    soft_attack_pct: float = 0.0
    hard_attack_pct: float = 0.0
    defense_pct: float = 0.0
    breakthrough_pct: float = 0.0
    support_soft_attack_pct: float = 0.0
    max_planning_bonus: float = 0.30
    max_entrenchment_bonus: float = 0.0
    recovery_rate_bonus: float = 0.0
    reinforce_rate_bonus: float = 0.0
    supply_consumption_pct: float = 0.0
    description_ru: str = ""


DOCTRINE_DB: Dict[str, LandDoctrine] = {
    "none": LandDoctrine(
        id="none",
        name="No Doctrine",
        name_ru="Без доктрины",
        max_planning_bonus=0.30,
        description_ru="Базовые характеристики без бонусов доктрин.",
    ),
    "superior_firepower": LandDoctrine(
        id="superior_firepower",
        name="Superior Firepower (Integrated Support)",
        name_ru="Превосходство огневой мощи (Интегрированная поддержка)",
        infantry_org_bonus=10.0,
        soft_attack_pct=0.20,
        hard_attack_pct=0.10,
        defense_pct=0.10,
        breakthrough_pct=0.10,
        support_soft_attack_pct=0.50,
        max_planning_bonus=0.30,
        recovery_rate_bonus=0.10,
        description_ru="+20% мягкой атаки, +50% атаки ротам поддержки, +10 орг. пехоте.",
    ),
    "grand_battleplan": LandDoctrine(
        id="grand_battleplan",
        name="Grand Battleplan (Infiltration / Assault)",
        name_ru="Крупномасштабное планирование",
        infantry_org_bonus=10.0,
        soft_attack_pct=0.10,
        defense_pct=0.15,
        breakthrough_pct=0.20,
        max_planning_bonus=0.60,
        max_entrenchment_bonus=10.0,
        supply_consumption_pct=-0.10,
        description_ru="+10 окапывания, до +60% бонуса планирования, +20% прорыва, -10% снабжения.",
    ),
    "mobile_warfare": LandDoctrine(
        id="mobile_warfare",
        name="Mobile Warfare (Blitzkrieg)",
        name_ru="Маневренная война (Блицкриг)",
        infantry_org_bonus=10.0,
        armor_org_bonus=10.0,
        breakthrough_pct=0.40,
        recovery_rate_bonus=0.25,
        reinforce_rate_bonus=0.05,
        max_planning_bonus=0.30,
        description_ru="+40% прорыва, +10 орг. танкам и мотопехоте, +0.25 восстановления орг.",
    ),
    "mass_assault": LandDoctrine(
        id="mass_assault",
        name="Mass Assault (Mass Mobilization 1.19+)",
        name_ru="Массовый штурм (1.19+: -0.2 ширины пехоты)",
        infantry_width_delta=-0.2,
        infantry_org_bonus=10.0,
        defense_pct=0.10,
        recovery_rate_bonus=0.30,
        reinforce_rate_bonus=0.15,
        supply_consumption_pct=-0.20,
        max_planning_bonus=0.30,
        description_ru="1.19+: -0.2 ширины фронта пехотным батальонам, -20% снабжения, +15% шанса подкрепления, +0.30 восстановления.",
    ),
}


@dataclass(frozen=True)
class Terrain:
    id: str
    name: str
    name_ru: str
    base_width: int
    flank_width: int
    attacker_attack_mod: float  # e.g. -0.35 for mountain
    movement_cost: float


TERRAIN_DB: Dict[str, Terrain] = {
    "plains": Terrain("plains", "Plains", "Равнины", 70, 35, 0.0, 1.0),
    "forest": Terrain("forest", "Forest", "Лес", 60, 30, -0.15, 1.5),
    "hills": Terrain("hills", "Hills", "Холмы", 70, 35, -0.25, 1.5),
    "mountain": Terrain("mountain", "Mountain", "Горы", 50, 25, -0.50, 2.0),
    "marsh": Terrain("marsh", "Marsh", "Болото", 50, 25, -0.40, 2.0),
    "jungle": Terrain("jungle", "Jungle", "Джунгли", 60, 30, -0.30, 2.0),
    "desert": Terrain("desert", "Desert", "Пустыня", 70, 35, 0.0, 1.2),
    "urban": Terrain("urban", "Urban", "Город", 80, 40, -0.30, 1.2),
}


@dataclass(frozen=True)
class CombatTactic:
    id: str
    name: str
    name_ru: str
    side: str  # "attacker" or "defender"
    attacker_dmg_mod: float = 0.0
    defender_dmg_mod: float = 0.0
    combat_width_mod: float = 0.0
    countered_by: str = ""


TACTICS_DB: Dict[str, CombatTactic] = {
    "attack": CombatTactic("attack", "Attack", "Атака", "attacker", attacker_dmg_mod=0.05),
    "assault": CombatTactic("assault", "Assault", "Штурм", "attacker", attacker_dmg_mod=0.25, countered_by="counterattack"),
    "breakthrough": CombatTactic("breakthrough", "Breakthrough", "Прорыв", "attacker", attacker_dmg_mod=0.25, defender_dmg_mod=-0.15, countered_by="backhand_blow"),
    "blitz": CombatTactic("blitz", "Blitz", "Блиц", "attacker", attacker_dmg_mod=0.15, defender_dmg_mod=-0.15, countered_by="elastic_defense"),
    "encirclement": CombatTactic("encirclement", "Encirclement", "Окружение", "attacker", attacker_dmg_mod=0.25, combat_width_mod=0.50, countered_by="tactical_withdrawal"),
    "defend": CombatTactic("defend", "Defend", "Оборона", "defender", defender_dmg_mod=0.05),
    "counterattack": CombatTactic("counterattack", "Counterattack", "Контратака", "defender", defender_dmg_mod=0.25),
    "elastic_defense": CombatTactic("elastic_defense", "Elastic Defense", "Эластичная оборона", "defender", attacker_dmg_mod=-0.15, defender_dmg_mod=0.10),
    "ambush": CombatTactic("ambush", "Ambush", "Засада", "defender", attacker_dmg_mod=-0.25, defender_dmg_mod=0.10),
    "backhand_blow": CombatTactic("backhand_blow", "Backhand Blow", "Удар наотмашь", "defender", attacker_dmg_mod=-0.20, defender_dmg_mod=0.25),
    "tactical_withdrawal": CombatTactic("tactical_withdrawal", "Tactical Withdrawal", "Тактический отход", "defender", attacker_dmg_mod=-0.25, defender_dmg_mod=-0.05, combat_width_mod=-0.25),
}
