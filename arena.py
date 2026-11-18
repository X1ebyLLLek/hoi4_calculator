"""HoI4 1.19.5.0+ Tournament Arena: finds the best defense & universal division templates."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import time

from . import gamedata
from .gamedata import GameData
from .division import DivisionTemplate, calculate_division
from .battle import BattleConfig, simulate_battle_stats


@dataclass
class ArenaConfig:
    tech_year: int = 1940
    terrain: str = "plains"
    river: str = "none"
    fort_level: int = 0
    balance_mode: str = "width"  # "width" (fill combat width) or "ic" (equal IC budget)
    ic_budget: float = 10000.0
    max_hours: int = 480
    include_tanks: bool = True
    include_special: bool = True
    seed: int = 42


def _make_tpl(
    tid: str,
    name: str,
    archetype: str,
    battalions: Dict[str, int],
    support: List[str],
    regimental: List[str],
    grand_doc: str,
    tech_year: int,
) -> Tuple[str, DivisionTemplate, str]:
    tpl = DivisionTemplate(
        name=name,
        battalions=battalions,
        support=support,
        regimental=regimental,
        tech_year=tech_year,
        doctrine={"grand": grand_doc, "milestones": [True, True, True, True]} if grand_doc else {},
    )
    return tid, tpl, archetype


def generate_arena_templates(
    tech_year: int = 1940,
    include_tanks: bool = True,
    include_special: bool = True,
) -> List[Tuple[str, DivisionTemplate, str]]:
    """Generate a curated, comprehensive pool of meta & experimental division combinations."""
    pool: List[Tuple[str, DivisionTemplate, str]] = []

    sup_basic = ["engineer", "artillery", "anti_air"]
    sup_at = ["engineer", "artillery", "anti_air", "anti_tank"]
    sup_elite = ["engineer", "artillery", "anti_air", "field_hospital", "logistics_company"]
    reg_inf = ["fire_support"]
    reg_at = ["fire_support", "anti_tank_battery"]
    reg_arty = ["fire_support", "field_guns"]

    # 1. Pure Infantry across widths & doctrines
    for n_inf in (6, 9, 10, 12):
        for doc, dname in (("grand_battleplan", "GBP"), ("mass_assault", "MA"), ("superior_firepower", "SF")):
            pool.append(_make_tpl(
                f"inf_{n_inf}_{doc}", f"Пехота {n_inf}/0 ({dname})", "infantry",
                {"infantry": n_inf}, sup_basic, reg_inf, doc, tech_year
            ))
        pool.append(_make_tpl(
            f"inf_{n_inf}_at", f"Пехота {n_inf}/0 + ПТ-подд. (GBP)", "infantry_at",
            {"infantry": n_inf}, sup_at, reg_at, "grand_battleplan", tech_year
        ))

    # 2. Infantry + Line Artillery
    for n_inf, n_art in ((6, 1), (7, 2), (9, 1), (9, 2), (9, 3)):
        for doc, dname in (("superior_firepower", "SF"), ("grand_battleplan", "GBP")):
            pool.append(_make_tpl(
                f"inf_{n_inf}_{n_art}_{doc}", f"Пехота+Арта {n_inf}/{n_art} ({dname})", "inf_arty",
                {"infantry": n_inf, "artillery_brigade": n_art}, sup_elite if n_art >= 2 else sup_basic,
                reg_arty if n_art >= 2 else reg_inf, doc, tech_year
            ))

    # 3. Infantry + Line Anti-Tank / Anti-Air
    for n_inf, n_at in ((8, 1), (9, 2)):
        pool.append(_make_tpl(
            f"inf_{n_inf}_lat{n_at}", f"ПТ-пехота {n_inf}/{n_at} (GBP)", "infantry_at",
            {"infantry": n_inf, "anti_tank_brigade": n_at}, sup_at, reg_at, "grand_battleplan", tech_year
        ))

    # 4. Special Forces (Mountaineers / Marines)
    if include_special:
        pool.append(_make_tpl(
            "mtn_9_0", "Горнострелки 9/0 (GBP)", "special",
            {"mountaineers": 9}, sup_basic, reg_inf, "grand_battleplan", tech_year
        ))
        pool.append(_make_tpl(
            "mtn_8_3", "Горнострелки 8/3 (SF)", "special",
            {"mountaineers": 8, "artillery_brigade": 3}, sup_elite, reg_arty, "superior_firepower", tech_year
        ))

    # 5. Mobile & Armor
    if include_tanks:
        # Space Marines (Infantry + 1 Tank)
        pool.append(_make_tpl(
            "sm_inf8_med1", "Космодесант 8 Пех + 1 СТ (GBP)", "space_marine",
            {"infantry": 8, "medium_armor": 1}, sup_at, reg_inf, "grand_battleplan", tech_year
        ))
        pool.append(_make_tpl(
            "sm_inf8_hvy1", "Космодесант 8 Пех + 1 ТТ (GBP)", "space_marine",
            {"infantry": 8, "heavy_armor": 1}, sup_at, reg_inf, "grand_battleplan", tech_year
        ))

        # Motorized / Mechanized
        mot_unit = "mechanized" if tech_year >= 1940 else "motorized"
        pool.append(_make_tpl(
            "mot_9_0", f"{'Мех.' if mot_unit == 'mechanized' else 'Мото'}пехота 9/0 (MW)", "mobile",
            {mot_unit: 9}, ["engineer", "artillery", "anti_air", "logistics_company"], ["mot_fire_support"],
            "new_mobile_warfare", tech_year
        ))

        sup_tank = ["armored_engineer", "light_tank_recon", "anti_air", "logistics_company", "signal_company"]
        reg_tank = ["medium_sp_anti_air_support"] if tech_year >= 1938 else ["light_sp_anti_air_support"]

        # Medium Armor combinations
        for n_tk, n_inf in ((6, 4), (8, 7), (10, 5), (10, 8)):
            pool.append(_make_tpl(
                f"med_{n_tk}_{n_inf}", f"Сред. танки {n_tk} Т / {n_inf} {'Мех' if mot_unit == 'mechanized' else 'Мото'} (MW)",
                "tank", {"medium_armor": n_tk, mot_unit: n_inf}, sup_tank, reg_tank, "new_mobile_warfare", tech_year
            ))

        # Heavy Armor combinations (including Field Hospital variant for min manpower loss)
        sup_tank_hosp = ["armored_engineer", "light_tank_recon", "field_hospital", "logistics_company", "signal_company"]
        for n_tk, n_inf in ((8, 7), (10, 8)):
            pool.append(_make_tpl(
                f"hvy_{n_tk}_{n_inf}", f"Тяж. танки {n_tk} Т / {n_inf} {'Мех' if mot_unit == 'mechanized' else 'Мото'} (MW)",
                "tank", {"heavy_armor": n_tk, mot_unit: n_inf}, sup_tank, reg_tank, "new_mobile_warfare", tech_year
            ))
        pool.append(_make_tpl(
            "hvy_10_8_hosp", f"Тяж. танки 10 Т / 8 {'Мех' if mot_unit == 'mechanized' else 'Мото'} + Госпиталь (MW)",
            "tank", {"heavy_armor": 10, mot_unit: 8}, sup_tank_hosp, reg_tank, "new_mobile_warfare", tech_year
        ))

    return pool


def run_arena(config: ArenaConfig, gd: Optional[GameData] = None) -> Dict[str, Any]:
    """Run a full round-robin tournament across all generated templates."""
    t0 = time.perf_counter()
    gd = gd or gamedata.load()
    pool = generate_arena_templates(config.tech_year, config.include_tanks, config.include_special)

    ter = gd.terrain.get(config.terrain, gd.terrain.get("plains", {}))
    battle_w = float(ter.get("combat_width", 70))

    entries: List[Dict[str, Any]] = []
    for tid, tpl, arch in pool:
        stats = calculate_division(tpl, gd)
        if config.balance_mode == "ic":
            div_cnt = max(1, round(config.ic_budget / max(100.0, stats["ic_cost"])))
            div_cnt = min(div_cnt, 16)  # avoid excessive runtime on tiny templates
        else:
            front_cnt = max(1, round(battle_w / max(1.0, stats["width"])))
            div_cnt = front_cnt + 2  # frontline + 2 reserves for rotation
        entries.append({
            "id": tid,
            "name": tpl.name,
            "archetype": arch,
            "tpl": tpl,
            "stats": stats,
            "div_count": div_cnt,
            "def_wins": 0, "def_holds": 0, "def_losses": 0, "def_games": 0,
            "def_own_ic": 0.0, "def_enemy_ic": 0.0, "def_own_mp": 0, "def_enemy_mp": 0,
            "atk_wins": 0, "atk_draws": 0, "atk_losses": 0, "atk_games": 0,
            "atk_own_ic": 0.0, "atk_enemy_ic": 0.0, "atk_own_mp": 0, "atk_enemy_mp": 0,
            "atk_win_hours": [],
            "vs_arch_def": {},  # archetype -> {holds, games}
            "vs_arch_atk": {},
        })

    total_battles = 0
    for i, atk in enumerate(entries):
        for j, dfn in enumerate(entries):
            if i == j:
                continue
            bcfg = BattleConfig(
                terrain=config.terrain,
                river=config.river,
                fort_level=config.fort_level,
                attacker_count=atk["div_count"],
                defender_count=dfn["div_count"],
                max_hours=config.max_hours,
                seed=config.seed,
            )
            res = simulate_battle_stats(atk["stats"], dfn["stats"], bcfg, gd, record_timeline=False)
            total_battles += 1

            w = res["winner"]
            a_sum = res["attacker_summary"]
            d_sum = res["defender_summary"]

            # Update attacker stats
            atk["atk_games"] += 1
            atk["atk_own_ic"] += a_sum["ic_lost"]
            atk["atk_enemy_ic"] += d_sum["ic_lost"]
            atk["atk_own_mp"] += a_sum["manpower_lost"]
            atk["atk_enemy_mp"] += d_sum["manpower_lost"]
            if w == "attacker":
                atk["atk_wins"] += 1
                atk["atk_win_hours"].append(res["hours_lasted"])
            elif w == "draw":
                atk["atk_draws"] += 1
            else:
                atk["atk_losses"] += 1

            va = atk["vs_arch_atk"].setdefault(dfn["archetype"], {"wins": 0, "games": 0})
            va["games"] += 1
            if w == "attacker":
                va["wins"] += 1

            # Update defender stats
            dfn["def_games"] += 1
            dfn["def_own_ic"] += d_sum["ic_lost"]
            dfn["def_enemy_ic"] += a_sum["ic_lost"]
            dfn["def_own_mp"] += d_sum["manpower_lost"]
            dfn["def_enemy_mp"] += a_sum["manpower_lost"]
            if w == "defender":
                dfn["def_wins"] += 1
                dfn["def_holds"] += 1
            elif w == "draw":
                dfn["def_holds"] += 1
            else:
                dfn["def_losses"] += 1

            vd = dfn["vs_arch_def"].setdefault(atk["archetype"], {"holds": 0, "games": 0})
            vd["games"] += 1
            if w in ("defender", "draw"):
                vd["holds"] += 1

    leaderboard: List[Dict[str, Any]] = []
    for e in entries:
        st = e["stats"]
        dg = max(1, e["def_games"])
        ag = max(1, e["atk_games"])

        def_hold_rate = e["def_holds"] / dg
        def_win_rate = e["def_wins"] / dg
        def_ic_ratio = e["def_enemy_ic"] / max(1.0, e["def_own_ic"])
        def_mp_ratio = e["def_enemy_mp"] / max(1.0, e["def_own_mp"])
        def_avg_ic_lost = e["def_own_ic"] / dg

        atk_win_rate = e["atk_wins"] / ag
        atk_ic_ratio = e["atk_enemy_ic"] / max(1.0, e["atk_own_ic"])
        atk_mp_ratio = e["atk_enemy_mp"] / max(1.0, e["atk_own_mp"])
        atk_avg_ic_lost = e["atk_own_ic"] / ag

        def_avg_mp_lost = e["def_own_mp"] / dg
        def_avg_enemy_mp_lost = e["def_enemy_mp"] / dg
        atk_avg_mp_lost = e["atk_own_mp"] / ag
        atk_avg_enemy_mp_lost = e["atk_enemy_mp"] / ag
        total_mp_ratio = (e["def_enemy_mp"] + e["atk_enemy_mp"]) / max(1.0, e["def_own_mp"] + e["atk_own_mp"])

        # Composite KPD scores (0..100+ scale)
        defense_kpd = (
            def_hold_rate * 50.0
            + def_win_rate * 15.0
            + min(5.0, def_ic_ratio) * 6.0
            + min(5.0, def_mp_ratio) * 3.0
            - min(15.0, def_avg_ic_lost / 300.0)
        )
        offense_kpd = (
            atk_win_rate * 60.0
            + min(5.0, atk_ic_ratio) * 6.0
            + min(5.0, atk_mp_ratio) * 2.0
        )
        universal_kpd = 0.55 * defense_kpd + 0.45 * offense_kpd
        mp_saver_kpd = total_mp_ratio * 25.0 + def_hold_rate * 20.0 + atk_win_rate * 15.0

        def_vs = {
            k: round(v["holds"] / max(1, v["games"]) * 100.0, 1)
            for k, v in e["vs_arch_def"].items()
        }
        atk_vs = {
            k: round(v["wins"] / max(1, v["games"]) * 100.0, 1)
            for k, v in e["vs_arch_atk"].items()
        }

        leaderboard.append({
            "id": e["id"],
            "name": e["name"],
            "archetype": e["archetype"],
            "width": st["width"],
            "ic_cost": st["ic_cost"],
            "manpower": st["manpower"],
            "div_count": e["div_count"],
            "soft": st["soft"],
            "hard": st["hard"],
            "defense": st["defense"],
            "brk": st["brk"],
            "armor": st["armor"],
            "pierce": st["pierce"],
            "org": st["org"],
            "def_hold_pct": round(def_hold_rate * 100.0, 1),
            "def_win_pct": round(def_win_rate * 100.0, 1),
            "def_ic_ratio": round(def_ic_ratio, 2),
            "def_mp_ratio": round(def_mp_ratio, 2),
            "def_avg_mp_lost": round(def_avg_mp_lost, 0),
            "def_avg_enemy_mp_lost": round(def_avg_enemy_mp_lost, 0),
            "def_avg_ic_lost": round(def_avg_ic_lost, 1),
            "atk_win_pct": round(atk_win_rate * 100.0, 1),
            "atk_ic_ratio": round(atk_ic_ratio, 2),
            "atk_mp_ratio": round(atk_mp_ratio, 2),
            "atk_avg_mp_lost": round(atk_avg_mp_lost, 0),
            "atk_avg_enemy_mp_lost": round(atk_avg_enemy_mp_lost, 0),
            "total_mp_ratio": round(total_mp_ratio, 2),
            "mp_saver_kpd": round(mp_saver_kpd, 2),
            "atk_avg_ic_lost": round(atk_avg_ic_lost, 1),
            "defense_kpd": round(defense_kpd, 2),
            "offense_kpd": round(offense_kpd, 2),
            "universal_kpd": round(universal_kpd, 2),
            "def_vs_archetype": def_vs,
            "atk_vs_archetype": atk_vs,
            "battalions": e["tpl"].battalions,
            "support": e["tpl"].support,
            "regimental": e["tpl"].regimental,
            "doctrine": e["tpl"].doctrine.get("grand", ""),
        })

    best_defense = sorted(leaderboard, key=lambda x: -x["defense_kpd"])
    best_universal = sorted(leaderboard, key=lambda x: -x["universal_kpd"])
    best_offense = sorted(leaderboard, key=lambda x: -x["offense_kpd"])
    best_mp_saver = sorted(leaderboard, key=lambda x: -x["total_mp_ratio"])

    elapsed = round(time.perf_counter() - t0, 2)
    return {
        "templates_count": len(entries),
        "total_battles": total_battles,
        "elapsed_sec": elapsed,
        "terrain": gd.name(config.terrain),
        "balance_mode": config.balance_mode,
        "best_defense": best_defense,
        "best_universal": best_universal,
        "best_offense": best_offense,
        "best_mp_saver": best_mp_saver,
    }


def generate_fullslot_templates(tech_year: int = 1942) -> List[Tuple[str, DivisionTemplate, str]]:
    """Generate maximum-slot (25 line + 5 support + up to 5 regimental) templates of all archetypes."""
    mot_unit = "mechanized" if tech_year >= 1940 else "motorized"
    sup_inf = ["engineer", "artillery", "anti_air", "field_hospital", "logistics_company"]
    sup_arm = ["armored_engineer", "light_tank_recon", "field_hospital", "logistics_company", "signal_company"]
    reg_inf = ["fire_support", "field_guns", "anti_tank_battery", "anti_air_battery", "rocket_battery"]
    reg_arm = ["medium_tank_destroyer_support", "heavy_tank_destroyer_support",
               "medium_sp_anti_air_support", "heavy_sp_anti_air_support", "mot_fire_support"]

    full_pool: List[Tuple[str, DivisionTemplate, str]] = [
        _make_tpl("full_inf_25", "Фулл 25 Пехоты (GBP)", "infantry",
                  {"infantry": 25}, sup_inf, reg_inf, "grand_battleplan", tech_year),
        _make_tpl("full_inf_20_art5", "Фулл 20 Пех + 5 Арта (SF)", "inf_arty",
                  {"infantry": 20, "artillery_brigade": 5}, sup_inf, reg_inf, "superior_firepower", tech_year),
        _make_tpl("full_inf_20_at5", "Фулл 20 Пех + 5 ПТ (GBP)", "infantry_at",
                  {"infantry": 20, "anti_tank_brigade": 5}, sup_inf, reg_inf, "grand_battleplan", tech_year),
        _make_tpl("full_mtn_25", "Фулл 25 Горнострелков (GBP)", "special",
                  {"mountaineers": 25}, sup_inf, reg_inf, "grand_battleplan", tech_year),
        _make_tpl("full_sm_24_hvy1", "Фулл 24 Пех + 1 ТТ Космодесант (GBP)", "space_marine",
                  {"infantry": 24, "heavy_armor": 1}, sup_inf, reg_inf, "grand_battleplan", tech_year),
        _make_tpl("full_mech_25", f"Фулл 25 {'Мех' if mot_unit=='mechanized' else 'Мото'}пехоты (MW)", "mobile",
                  {mot_unit: 25}, sup_arm, ["mot_fire_support"], "new_mobile_warfare", tech_year),
        _make_tpl("full_med_15_10", f"Фулл 15 СТ + 10 {'Мех' if mot_unit=='mechanized' else 'Мото'} (MW)", "tank",
                  {"medium_armor": 15, mot_unit: 10}, sup_arm, reg_arm, "new_mobile_warfare", tech_year),
        _make_tpl("full_med_12_10_spa3", "Фулл 12 СТ + 10 Мех + 3 САУ (MW)", "tank",
                  {"medium_armor": 12, mot_unit: 10, "medium_sp_artillery_brigade": 3}, sup_arm, reg_arm, "new_mobile_warfare", tech_year),
        _make_tpl("full_hvy_15_10", f"Фулл 15 ТТ + 10 {'Мех' if mot_unit=='mechanized' else 'Мото'} (MW)", "tank",
                  {"heavy_armor": 15, mot_unit: 10}, sup_arm, reg_arm, "new_mobile_warfare", tech_year),
        _make_tpl("full_hvy_12_10_td3", "Фулл 12 ТТ + 10 Мех + 3 ПТ-САУ (MW)", "tank",
                  {"heavy_armor": 12, mot_unit: 10, "heavy_tank_destroyer_brigade": 3}, sup_arm, reg_arm, "new_mobile_warfare", tech_year),
        _make_tpl("full_hvy_12_10_spa3", "Фулл 12 ТТ + 10 Мех + 3 Т.САУ (MW)", "tank",
                  {"heavy_armor": 12, mot_unit: 10, "heavy_sp_artillery_brigade": 3}, sup_arm, reg_arm, "new_mobile_warfare", tech_year),
    ]
    if tech_year >= 1945:
        full_pool.append(_make_tpl(
            "full_mod_15_10", "Фулл 15 ОБТ + 10 Мех (MW)", "tank",
            {"modern_armor": 15, mot_unit: 10}, sup_arm, reg_arm, "new_mobile_warfare", tech_year
        ))
    return full_pool


def run_fullslot_and_upgrade_study(
    tech_year: int = 1942,
    terrain: str = "plains",
    gd: Optional[GameData] = None,
) -> Dict[str, Any]:
    """Evaluate all max-slot (25+5+5) templates in defense & compute the IC->efficiency upgrade curve."""
    t0 = time.perf_counter()
    gd = gd or gamedata.load()
    ter = gd.terrain.get(terrain, gd.terrain.get("plains", {}))
    battle_w = float(ter.get("combat_width", 70))

    # Diverse enemy attackers ("any enemy template": infantry, arty, space marine, medium & heavy tanks)
    attackers_pool = [
        tpl for _, tpl, _ in generate_arena_templates(tech_year, include_tanks=True, include_special=False)
        if any(k in tpl.battalions for k in ("artillery_brigade", "medium_armor", "heavy_armor"))
        or sum(tpl.battalions.values()) >= 9
    ][:14]
    atk_prepared = [
        (tpl, calculate_division(tpl, gd), max(1, round(battle_w / max(1.0, calculate_division(tpl, gd)["width"]))) + 2)
        for tpl in attackers_pool
    ]

    def eval_defender(tid: str, tpl: DivisionTemplate, change_note: str = "") -> Dict[str, Any]:
        st = calculate_division(tpl, gd)
        def_cnt = max(1, round(battle_w / max(1.0, st["width"]))) + 2
        own_mp, enemy_mp, own_ic, enemy_ic, holds, wins = 0, 0, 0.0, 0.0, 0, 0
        for _, ast, acnt in atk_prepared:
            res = simulate_battle_stats(
                ast, st,
                BattleConfig(terrain=terrain, attacker_count=acnt, defender_count=def_cnt, max_hours=360, seed=42),
                gd, record_timeline=False,
            )
            own_mp += res["defender_summary"]["manpower_lost"]
            enemy_mp += res["attacker_summary"]["manpower_lost"]
            own_ic += res["defender_summary"]["ic_lost"]
            enemy_ic += res["attacker_summary"]["ic_lost"]
            if res["winner"] in ("defender", "draw"):
                holds += 1
            if res["winner"] == "defender":
                wins += 1
        n = len(atk_prepared)
        mp_ratio = enemy_mp / max(1.0, own_mp)
        ic_ratio = enemy_ic / max(1.0, own_ic)
        hold_pct = holds / n * 100.0
        return {
            "id": tid, "name": tpl.name, "change": change_note,
            "width": st["width"], "ic_cost": st["ic_cost"], "manpower": st["manpower"],
            "hardness": round(st["hardness"] * 100, 1), "armor": st["armor"], "pierce": st["pierce"],
            "soft": st["soft"], "hard": st["hard"], "defense": st["defense"], "hp": st["hp"],
            "hold_pct": round(hold_pct, 1), "win_pct": round(wins / n * 100.0, 1),
            "avg_own_mp": round(own_mp / n, 0), "avg_enemy_mp": round(enemy_mp / n, 0),
            "mp_ratio": round(mp_ratio, 2), "ic_ratio": round(ic_ratio, 2),
        }

    # 1. Full-slot (25+5+5) comparison
    fullslot_results = [
        eval_defender(tid, tpl, arch) for tid, tpl, arch in generate_fullslot_templates(tech_year)
    ]
    fullslot_results.sort(key=lambda x: (-x["mp_ratio"], -x["hold_pct"]))

    # 2. Step-by-step Upgrade Curve (Cheap Infantry -> Full Heavy Tank + Mech)
    mot_u = "mechanized" if tech_year >= 1940 else "motorized"
    reg_spaa = "medium_sp_anti_air_support" if tech_year >= 1938 else "light_sp_anti_air_support"
    upgrade_steps = [
        ("u0", "Шаг 0: Голая пехота 9/0", "База",
         {"infantry": 9}, [], [], "grand_battleplan"),
        ("u1", "Шаг 1: + Сапёры, Арта, ПВО", "+3 роты поддержки (0w)",
         {"infantry": 9}, ["engineer", "artillery", "anti_air"], [], "grand_battleplan"),
        ("u2", "Шаг 2: + Госпиталь и Логистика", "+Госпиталь (+HP, -20% потерь)",
         {"infantry": 9}, ["engineer", "artillery", "anti_air", "field_hospital", "logistics_company"], [], "grand_battleplan"),
        ("u3", "Шаг 3: + 3 полковые роты 1.19+", "+Полковые роты (урон без ширины)",
         {"infantry": 9}, ["engineer", "artillery", "anti_air", "field_hospital", "logistics_company"],
         ["fire_support", "field_guns", "anti_tank_battery"], "grand_battleplan"),
        ("u4", "Шаг 4: Космодесант (8 Пех + 1 ТТ)", "Замена 1 Пех -> 1 Тяж. танк (броня!)",
         {"infantry": 8, "heavy_armor": 1}, ["engineer", "artillery", "anti_air", "field_hospital", "logistics_company"],
         ["fire_support", "field_guns", "anti_tank_battery"], "grand_battleplan"),
        ("u5", "Шаг 5: Переход на БТР (8 Мех + 1 ТТ)", "Замена Пехоты -> Мехпехота (Hardness 60%+)",
         {mot_u: 8, "heavy_armor": 1}, ["armored_engineer", "artillery", "anti_air", "field_hospital", "logistics_company"],
         ["mot_fire_support", reg_spaa], "new_mobile_warfare"),
        ("u6", "Шаг 6: Танковый кулак (8 ТТ + 7 Мех)", "Замена части Мех -> 8 Тяж. танков",
         {"heavy_armor": 8, mot_u: 7}, ["armored_engineer", "light_tank_recon", "anti_air", "field_hospital", "logistics_company"],
         ["mot_fire_support", reg_spaa], "new_mobile_warfare"),
        ("u7", "Шаг 7: Фулл-слот (15 ТТ + 10 Мех + 5+5)", "Максимум слотов 25+5+5 (пик брони и HP)",
         {"heavy_armor": 15, mot_u: 10}, ["armored_engineer", "light_tank_recon", "field_hospital", "logistics_company", "signal_company"],
         ["medium_tank_destroyer_support", "heavy_tank_destroyer_support", "medium_sp_anti_air_support", "heavy_sp_anti_air_support", "mot_fire_support"],
         "new_mobile_warfare"),
    ]
    curve = [
        eval_defender(uid, DivisionTemplate(name, b, sup, reg, tech_year=tech_year,
                      doctrine={"grand": doc, "milestones": [True, True, True, True]}), note)
        for uid, name, note, b, sup, reg, doc in upgrade_steps
    ]

    return {
        "tech_year": tech_year,
        "terrain": gd.name(terrain),
        "elapsed_sec": round(time.perf_counter() - t0, 2),
        "fullslot_ranking": fullslot_results,
        "upgrade_curve": curve,
    }
