"""HoI4 1.19.4+ Standard & Regimental Support Companies database."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class SupportCompany:
    id: str
    name: str
    name_ru: str
    slot_type: str  # "standard" or "regimental" (1.19+)
    manpower: int
    hp: float
    organization: float
    recovery_rate: float
    supply_use: float
    weight: float
    training_time: int
    equipment: Dict[str, int]  # equipment_category -> count
    # Stat multipliers applied to the equipment inside this support company
    soft_attack_mult: float = 1.0
    hard_attack_mult: float = 1.0
    defense_mult: float = 1.0
    breakthrough_mult: float = 1.0
    air_attack_mult: float = 1.0
    # Division-wide flat / percentage bonuses (base Lv1 + per_level_bonus * (tech_level - 1))
    entrenchment_base: float = 0.0
    entrenchment_per_lvl: float = 0.0
    recon_base: float = 0.0
    recon_per_lvl: float = 0.0
    initiative_base: float = 0.0
    initiative_per_lvl: float = 0.0
    supply_reduction_base: float = 0.0
    supply_reduction_per_lvl: float = 0.0
    fuel_reduction_base: float = 0.0
    fuel_reduction_per_lvl: float = 0.0
    trickleback_base: float = 0.0
    trickleback_per_lvl: float = 0.0
    xp_loss_reduction_base: float = 0.0
    xp_loss_reduction_per_lvl: float = 0.0
    equipment_capture_base: float = 0.0
    equipment_capture_per_lvl: float = 0.0
    reliability_bonus_base: float = 0.0
    reliability_bonus_per_lvl: float = 0.0
    suppression_mult_base: float = 0.0
    suppression_mult_per_lvl: float = 0.0
    # Division-wide combat stat % bonuses (e.g. Assault Engineer breakthrough)
    div_breakthrough_pct: float = 0.0
    div_defense_pct: float = 0.0
    div_soft_attack_pct: float = 0.0
    # Terrain modifiers granted to the division
    terrain_modifiers: Dict[str, Dict[str, float]] = field(default_factory=dict)
    description_ru: str = ""


SUPPORT_DB: Dict[str, SupportCompany] = {
    # ======================== STANDARD SUPPORT COMPANIES ========================
    "engineer": SupportCompany(
        id="engineer",
        name="Engineer Company",
        name_ru="Инженерная рота (Сапёры)",
        slot_type="standard",
        manpower=300,
        hp=2.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.02,
        weight=0.1,
        training_time=120,
        equipment={"infantry_eq": 10, "support_eq": 30},
        defense_mult=1.30,
        entrenchment_base=2.0,
        entrenchment_per_lvl=2.0,  # +2/+4/+6/+8
        terrain_modifiers={
            "forest": {"defense": 0.25, "movement": 0.05},
            "hills": {"defense": 0.20},
            "mountain": {"defense": 0.20},
            "marsh": {"defense": 0.25, "movement": 0.10},
            "jungle": {"defense": 0.25, "movement": 0.05},
            "urban": {"defense": 0.25, "attack": 0.10},
            "river": {"attack": 0.25, "defense": 0.25, "movement": 0.25},
            "fort": {"attack": 0.20, "defense": 0.15},
        },
        description_ru="Даёт +2..+8 к окапыванию, бонусы к обороне в лесах/городах/болотах, снимает штрафы за реку и форты.",
    ),
    "assault_engineer": SupportCompany(
        id="assault_engineer",
        name="Assault Engineers",
        name_ru="Штурмовые инженеры",
        slot_type="standard",
        manpower=300,
        hp=2.5,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.04,
        weight=0.1,
        training_time=150,
        equipment={"infantry_eq": 20, "support_eq": 40},
        breakthrough_mult=1.50,
        entrenchment_base=1.0,
        entrenchment_per_lvl=1.0,
        div_breakthrough_pct=0.05,
        terrain_modifiers={
            "urban": {"attack": 0.25, "defense": 0.10},
            "river": {"attack": 0.35, "movement": 0.25},
            "fort": {"attack": 0.40},
        },
        description_ru="Спецпроект: +5% прорыва дивизии, мощные бонусы при штурме фортов (+40%), городов (+25%) и форсировании рек (+35%).",
    ),
    "armored_engineer": SupportCompany(
        id="armored_engineer",
        name="Armored Engineers",
        name_ru="Бронированные инженеры",
        slot_type="standard",
        manpower=300,
        hp=3.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.05,
        weight=0.2,
        training_time=150,
        equipment={"support_eq": 30, "light_tank": 10},
        entrenchment_base=2.0,
        entrenchment_per_lvl=2.0,
        div_breakthrough_pct=0.05,
        terrain_modifiers={
            "forest": {"attack": 0.10, "defense": 0.15},
            "urban": {"attack": 0.20, "defense": 0.15},
            "river": {"attack": 0.35, "movement": 0.25},
            "fort": {"attack": 0.35},
        },
        description_ru="Бронированные сапёры: добавляют броню, прорыв (+5%), окапывание и бонусы на реках/фортах.",
    ),
    "recon_cav": SupportCompany(
        id="recon_cav",
        name="Cavalry Recon Company",
        name_ru="Разведрота (Кавалерия)",
        slot_type="standard",
        manpower=500,
        hp=2.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.02,
        weight=0.1,
        training_time=120,
        equipment={"infantry_eq": 40, "support_eq": 10},
        recon_base=1.0,
        recon_per_lvl=1.0,  # 1/2/3/4
        terrain_modifiers={
            "plains": {"movement": 0.10},
            "forest": {"movement": 0.10},
            "hills": {"movement": 0.10},
            "mountain": {"movement": 0.10},
            "desert": {"movement": 0.10},
        },
        description_ru="Даёт +1..+4 разведки (повышает шанс контрить тактику врага) и +10% скорости по пересечённой местности.",
    ),
    "recon_mot": SupportCompany(
        id="recon_mot",
        name="Motorized Recon Company",
        name_ru="Моторизованная разведка",
        slot_type="standard",
        manpower=500,
        hp=2.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.03,
        weight=0.1,
        training_time=120,
        equipment={"infantry_eq": 40, "support_eq": 10, "motorized": 20},
        recon_base=1.5,
        recon_per_lvl=1.0,
        terrain_modifiers={
            "plains": {"movement": 0.15},
            "desert": {"movement": 0.15},
            "hills": {"movement": 0.10},
        },
        description_ru="Высокая разведка (+1.5..+4.5) и +15% скорости на равнинах/пустынях.",
    ),
    "recon_armored_car": SupportCompany(
        id="recon_armored_car",
        name="Armored Car Recon",
        name_ru="Разведка на бронеавтомобилях",
        slot_type="standard",
        manpower=500,
        hp=2.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.04,
        weight=0.2,
        training_time=120,
        equipment={"support_eq": 10, "armored_car": 24},
        recon_base=2.0,
        recon_per_lvl=1.0,
        terrain_modifiers={
            "plains": {"movement": 0.15},
            "desert": {"movement": 0.15},
        },
        description_ru="Максимальная разведка (+2..+5) и лёгкая броня для пехотных дивизий.",
    ),
    "recon_light_tank": SupportCompany(
        id="recon_light_tank",
        name="Armored Recon (Light Tank)",
        name_ru="Бронеразведка (Лёгкие танки)",
        slot_type="standard",
        manpower=500,
        hp=2.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.05,
        weight=0.3,
        training_time=120,
        equipment={"support_eq": 10, "light_tank": 24},
        recon_base=1.5,
        recon_per_lvl=1.0,
        div_soft_attack_pct=0.05,
        terrain_modifiers={
            "plains": {"movement": 0.10},
        },
        description_ru="Даёт разведку, ощутимую броню, прорыв и +5% мягкой атаки артиллерии/дивизии.",
    ),
    "support_artillery": SupportCompany(
        id="support_artillery",
        name="Support Artillery",
        name_ru="Рота артиллерийской поддержки",
        slot_type="standard",
        manpower=300,
        hp=0.2,
        organization=0.0,
        recovery_rate=0.10,
        supply_use=0.12,
        weight=0.1,
        training_time=120,
        equipment={"artillery": 12},
        soft_attack_mult=0.60,
        hard_attack_mult=0.60,
        defense_mult=0.60,
        breakthrough_mult=0.60,
        description_ru="Дёшево и без ширины фронта добавляет 12 орудий с мощной противопехотной атакой.",
    ),
    "support_rocket_artillery": SupportCompany(
        id="support_rocket_artillery",
        name="Support Rocket Artillery",
        name_ru="Рота реактивной артиллерии",
        slot_type="standard",
        manpower=300,
        hp=0.2,
        organization=0.0,
        recovery_rate=0.10,
        supply_use=0.12,
        weight=0.1,
        training_time=120,
        equipment={"rocket_artillery": 12},
        soft_attack_mult=0.60,
        hard_attack_mult=0.60,
        defense_mult=0.60,
        breakthrough_mult=0.75,
        description_ru="Добавляет прорыв и мягкую атаку без ширины фронта (12 установок).",
    ),
    "support_anti_air": SupportCompany(
        id="support_anti_air",
        name="Support Anti-Air",
        name_ru="Рота ПВО",
        slot_type="standard",
        manpower=300,
        hp=0.2,
        organization=0.0,
        recovery_rate=0.10,
        supply_use=0.08,
        weight=0.1,
        training_time=120,
        equipment={"anti_air": 20},
        soft_attack_mult=0.60,
        hard_attack_mult=0.60,
        defense_mult=0.60,
        breakthrough_mult=0.60,
        air_attack_mult=0.80,
        description_ru="Сбивает штурмовики врага, снижает штраф от вражеского превосходства в воздухе и даёт пробитие против лёгких танков.",
    ),
    "support_anti_tank": SupportCompany(
        id="support_anti_tank",
        name="Support Anti-Tank",
        name_ru="Рота ПТ-поддержки",
        slot_type="standard",
        manpower=300,
        hp=0.2,
        organization=0.0,
        recovery_rate=0.10,
        supply_use=0.08,
        weight=0.1,
        training_time=120,
        equipment={"anti_tank": 24},
        soft_attack_mult=0.50,
        hard_attack_mult=0.60,
        defense_mult=0.50,
        breakthrough_mult=0.50,
        description_ru="Даёт пехоте высокое бронепробитие и противотанковую атаку без траты ширины фронта.",
    ),
    "logistics": SupportCompany(
        id="logistics",
        name="Logistics Company",
        name_ru="Рота снабжения (Логистика)",
        slot_type="standard",
        manpower=500,
        hp=1.0,
        organization=10.0,
        recovery_rate=0.30,
        supply_use=0.0,
        weight=0.1,
        training_time=120,
        equipment={"support_eq": 20, "motorized": 10},
        supply_reduction_base=0.10,
        supply_reduction_per_lvl=0.033,  # ~10% -> 20% at Lv4
        fuel_reduction_base=0.05,
        fuel_reduction_per_lvl=0.05,     # 5% -> 20% at Lv4
        description_ru="Снижает потребление припасов на 10%..20% и топлива на 5%..20%. Незаменима для танков и больших дивизий.",
    ),
    "field_hospital": SupportCompany(
        id="field_hospital",
        name="Field Hospital",
        name_ru="Полевой госпиталь",
        slot_type="standard",
        manpower=500,
        hp=2.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.05,
        weight=0.1,
        training_time=120,
        equipment={"support_eq": 30, "motorized": 20},
        trickleback_base=0.05,
        trickleback_per_lvl=0.05,        # 5% -> 20%
        xp_loss_reduction_base=0.10,
        xp_loss_reduction_per_lvl=0.033,  # 10% -> 20%
        description_ru="Возвращает 5%..20% потерь в пул рекрутов (Trickleback) и сохраняет опыт дивизии.",
    ),
    "signal": SupportCompany(
        id="signal",
        name="Signal Company",
        name_ru="Рота связи",
        slot_type="standard",
        manpower=500,
        hp=1.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.02,
        weight=0.1,
        training_time=120,
        equipment={"support_eq": 20, "motorized": 10},
        initiative_base=0.20,
        initiative_per_lvl=0.10,         # +20% -> +50%
        description_ru="Увеличивает инициативу (+20%..+50%): дивизии быстрее вступают в бой из резерва и быстрее накапливают планирование.",
    ),
    "maintenance": SupportCompany(
        id="maintenance",
        name="Maintenance Company",
        name_ru="Ремонтная рота",
        slot_type="standard",
        manpower=500,
        hp=1.0,
        organization=20.0,
        recovery_rate=0.30,
        supply_use=0.03,
        weight=0.1,
        training_time=120,
        equipment={"support_eq": 25},
        reliability_bonus_base=0.05,
        reliability_bonus_per_lvl=0.05,  # +5% -> +20%
        equipment_capture_base=0.05,
        equipment_capture_per_lvl=0.05,  # 5% -> 20%
        description_ru="Повышает надёжность техники (+5%..+20%) и захватывает 5%..20% снаряжения врага в бою.",
    ),
    "military_police": SupportCompany(
        id="military_police",
        name="Military Police",
        name_ru="Военная полиция",
        slot_type="standard",
        manpower=500,
        hp=1.0,
        organization=10.0,
        recovery_rate=0.30,
        supply_use=0.02,
        weight=0.1,
        training_time=120,
        equipment={"infantry_eq": 40, "support_eq": 10},
        suppression_mult_base=0.20,
        suppression_mult_per_lvl=0.10,   # +20% -> +50%
        description_ru="Увеличивает подавление сопротивления (+20%..+50%) для гарнизонных шаблонов.",
    ),

    # ======================== 1.19+ REGIMENTAL SUPPORT COMPANIES ========================
    "reg_heavy_weapons": SupportCompany(
        id="reg_heavy_weapons",
        name="Regimental Heavy Weapons",
        name_ru="Полковое тяжёлое вооружение (1.19+)",
        slot_type="regimental",
        manpower=250,
        hp=2.0,
        organization=10.0,
        recovery_rate=0.20,
        supply_use=0.04,
        weight=0.1,
        training_time=100,
        equipment={"infantry_eq": 40, "support_eq": 15},
        soft_attack_mult=1.35,
        defense_mult=1.25,
        breakthrough_mult=1.15,
        description_ru="Полковая поддержка 1.19+: усиливает пехотный огневой вал (тяжёлые пулемёты и миномёты) при 0 ширины фронта.",
    ),
    "reg_anti_air": SupportCompany(
        id="reg_anti_air",
        name="Regimental Anti-Air",
        name_ru="Полковая ПВО (1.19+)",
        slot_type="regimental",
        manpower=200,
        hp=0.4,
        organization=0.0,
        recovery_rate=0.10,
        supply_use=0.06,
        weight=0.1,
        training_time=100,
        equipment={"anti_air": 16},
        soft_attack_mult=0.55,
        hard_attack_mult=0.55,
        air_attack_mult=0.75,
        description_ru="Полковая поддержка 1.19+: дополнительный слой ПВО и лёгкого пробития в слоте полковой поддержки.",
    ),
    "reg_anti_tank": SupportCompany(
        id="reg_anti_tank",
        name="Regimental Anti-Tank",
        name_ru="Полковая ПТ-батарея (1.19+)",
        slot_type="regimental",
        manpower=200,
        hp=0.4,
        organization=0.0,
        recovery_rate=0.10,
        supply_use=0.06,
        weight=0.1,
        training_time=100,
        equipment={"anti_tank": 18},
        hard_attack_mult=0.55,
        defense_mult=0.50,
        description_ru="Полковая поддержка 1.19+: компактная ПТ-батарея для повышения бронепробития пехоты.",
    ),
    "reg_medium_td": SupportCompany(
        id="reg_medium_td",
        name="Regimental Tank Destroyer",
        name_ru="Полковая рота ПТ-САУ (1.19+)",
        slot_type="regimental",
        manpower=250,
        hp=0.5,
        organization=0.0,
        recovery_rate=0.10,
        supply_use=0.10,
        weight=0.4,
        training_time=140,
        equipment={"medium_td": 16},
        soft_attack_mult=0.55,
        hard_attack_mult=0.65,
        breakthrough_mult=0.50,
        description_ru="Полковая поддержка 1.19+: добавляет ПТ-САУ без ширины фронта, резко повышая броню и пробитие.",
    ),
    "reg_spaa": SupportCompany(
        id="reg_spaa",
        name="Regimental SP Anti-Air",
        name_ru="Полковая рота ЗСУ (1.19+)",
        slot_type="regimental",
        manpower=250,
        hp=0.5,
        organization=0.0,
        recovery_rate=0.10,
        supply_use=0.08,
        weight=0.4,
        training_time=140,
        equipment={"medium_spaa": 12},
        soft_attack_mult=0.55,
        air_attack_mult=0.75,
        description_ru="Полковая поддержка 1.19+: бронированная ЗСУ в полковом слоте для танковых и мех. дивизий.",
    ),
}
