"""Budget step (+200 IC) study: finds the best defense template at every budget B
against ANY enemy attacker up to 1.5x B (attacker advantage).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import time

from . import gamedata
from .gamedata import GameData
from .division import DivisionTemplate, calculate_division
from .battle import BattleConfig, simulate_battle_stats


@dataclass
class BudgetCurveConfig:
    tech_year: int = 1942
    terrain: str = "plains"
    doctrine: str = "grand_battleplan"
    start_ic: int = 600
    end_ic: int = 4400
    step_ic: int = 200
    enemy_mult: float = 1.5
    seed: int = 42


def _build_diverse_pool(gd: GameData, tech_year: int, doctrine: str) -> List[Tuple[str, DivisionTemplate, Dict[str, Any]]]:
    """Generate ~200+ diverse valid templates spanning 400 IC to 7000+ IC without preset bias."""
    doc_dict = {"grand": doctrine, "milestones": [True, True, True, True]} if doctrine else {}
    mot_u = "mechanized" if tech_year >= 1940 else "motorized"
    reg_spaa = "medium_sp_anti_air_support" if tech_year >= 1938 else "light_sp_anti_air_support"

    sup_sets = [
        ("без доп.", []),
        ("Сап+Арт", ["engineer", "artillery"]),
        ("Сап+Арт+ПВО", ["engineer", "artillery", "anti_air"]),
        ("Сап+Арт+ПВО+ПТ", ["engineer", "artillery", "anti_air", "anti_tank"]),
        ("Сап+Арт+ПВО+Госп", ["engineer", "artillery", "anti_air", "field_hospital"]),
        ("Сап+Арт+ПВО+ПТ+Госп", ["engineer", "artillery", "anti_air", "anti_tank", "field_hospital"]),
        ("БрСап+Арт+ПВО+ПТ+Госп", ["armored_engineer", "artillery", "anti_air", "anti_tank", "field_hospital"]),
        ("БрСап+ЛТРазв+ПВО+Госп+Лог", ["armored_engineer", "light_tank_recon", "anti_air", "field_hospital", "logistics_company"]),
    ]
    reg_sets = [
        ("", []),
        ("+Полк.Тяж", ["fire_support"]),
        ("+Полк.Тяж+ПТ", ["fire_support", "anti_tank_battery"]),
        ("+Полк.Фулл(Тяж+Оруд+ПТ+ПВО)", ["fire_support", "field_guns", "anti_tank_battery", "anti_air_battery"]),
        ("+Полк.ПТ-САУ+ЗСУ", ["medium_tank_destroyer_support", reg_spaa]),
    ]

    cores: List[Tuple[str, Dict[str, int], bool]] = []
    # Infantry cores (6..15)
    for n in (6, 8, 9, 10, 12, 15):
        cores.append((f"{n} Пех", {"infantry": n}, False))
    # Infantry + Artillery
    for ni, na in ((6, 1), (7, 2), (8, 3), (9, 2), (9, 3), (10, 4)):
        cores.append((f"{ni} Пех + {na} Арт", {"infantry": ni, "artillery_brigade": na}, False))
    # Infantry + AT
    for ni, nat in ((7, 1), (8, 2), (9, 2), (10, 3)):
        cores.append((f"{ni} Пех + {nat} ПТ", {"infantry": ni, "anti_tank_brigade": nat}, False))
    # Space Marines (Infantry + 1 Medium/Heavy Tank)
    for ni in (7, 8, 9, 11):
        cores.append((f"{ni} Пех + 1 СТ", {"infantry": ni, "medium_armor": 1}, True))
        cores.append((f"{ni} Пех + 1 ТТ", {"infantry": ni, "heavy_armor": 1}, True))
    # Mechanized / Motorized cores
    for nm in (6, 8, 9, 10, 12):
        cores.append((f"{nm} Мех", {mot_u: nm}, True))
    for nm, nat in ((6, 1), (7, 2), (8, 2)):
        cores.append((f"{nm} Мех + {nat} ПТ", {mot_u: nm, "anti_tank_brigade": nat}, True))
    # Mech + 1 Heavy Tank
    for nm in (6, 8, 9):
        cores.append((f"{nm} Мех + 1 ТТ", {mot_u: nm, "heavy_armor": 1}, True))
    # Medium & Heavy Armor cores
    for ntk, nm in ((3, 6), (4, 5), (5, 5), (6, 4), (7, 5), (8, 7)):
        cores.append((f"{ntk} СТ + {nm} Мех", {"medium_armor": ntk, mot_u: nm}, True))
        cores.append((f"{ntk} ТТ + {nm} Мех", {"heavy_armor": ntk, mot_u: nm}, True))

    pool: List[Tuple[str, DivisionTemplate, Dict[str, Any]]] = []
    seen = set()
    for cname, bats, is_arm in cores:
        for sname, sups in sup_sets:
            if not is_arm and "БрСап" in sname and len(sups) > 4:
                pass
            for rname, regs in reg_sets:
                if "+Полк.ПТ-САУ" in rname and not is_arm:
                    continue
                if "+Полк.Тяж" in rname and any(k in bats for k in ("medium_armor", "heavy_armor")) and sum(bats.values()) > 10 and "infantry" not in bats:
                    continue
                key = (tuple(sorted(bats.items())), tuple(sorted(sups)), tuple(sorted(regs)))
                if key in seen:
                    continue
                seen.add(key)
                label = f"{cname} | {sname}{' ' + rname if rname else ''}"
                tpl = DivisionTemplate(label, bats, sups, regs, tech_year=tech_year, doctrine=doc_dict)
                st = calculate_division(tpl, gd)
                pool.append((label, tpl, st))
    return pool


def _build_enemy_attackers(gd: GameData, tech_year: int) -> List[Tuple[str, Dict[str, Any]]]:
    """Diverse enemy offensive templates across all IC tiers."""
    mot_u = "mechanized" if tech_year >= 1940 else "motorized"
    mw = {"grand": "new_mobile_warfare", "milestones": [True, True, True, True]}
    sf = {"grand": "superior_firepower", "milestones": [True, True, True, True]}
    specs = [
        ("Враг: Пех 9/0", {"infantry": 9}, ["engineer", "artillery"], [], sf),
        ("Враг: Пех+Арта 7/2", {"infantry": 7, "artillery_brigade": 2}, ["engineer", "artillery", "anti_air"], ["fire_support"], sf),
        ("Враг: Ударная 9/3", {"infantry": 9, "artillery_brigade": 3}, ["engineer", "artillery", "anti_air", "recon"], ["field_guns"], sf),
        ("Враг: Космодесант 8/1 ТТ", {"infantry": 8, "heavy_armor": 1}, ["engineer", "artillery", "anti_air"], ["fire_support"], sf),
        ("Враг: Лёгкие танки 6/4", {"light_armor": 6, "motorized": 4}, ["armored_engineer", "artillery", "anti_air"], [], mw),
        ("Враг: Сред. танки 6/4", {"medium_armor": 6, mot_u: 4}, ["armored_engineer", "light_tank_recon", "signal_company"], [], mw),
        ("Враг: Сред. танки 8/7", {"medium_armor": 8, mot_u: 7}, ["armored_engineer", "light_tank_recon", "anti_air", "signal_company"], ["medium_sp_anti_air_support"], mw),
        ("Враг: Тяж. танки 8/7", {"heavy_armor": 8, mot_u: 7}, ["armored_engineer", "light_tank_recon", "signal_company"], ["medium_sp_anti_air_support"], mw),
    ]
    out = []
    for name, b, s, r, d in specs:
        tpl = DivisionTemplate(name, b, s, r, tech_year=tech_year, doctrine=d)
        out.append((name, calculate_division(tpl, gd)))
    return out


def run_budget_curve(config: BudgetCurveConfig, gd: Optional[GameData] = None) -> Dict[str, Any]:
    """For every budget B (step +200 IC), find the best defense template against enemies up to 1.5x B."""
    t0 = time.perf_counter()
    gd = gd or gamedata.load()
    ter = gd.terrain.get(config.terrain, gd.terrain.get("plains", {}))
    battle_w = float(ter.get("combat_width", 70))

    pool = _build_diverse_pool(gd, config.tech_year, config.doctrine)
    all_enemies = _build_enemy_attackers(gd, config.tech_year)

    # Cache battle outcomes: (def_idx, enemy_idx) -> (own_mp, enemy_mp, hold)
    battle_cache: Dict[Tuple[int, int], Tuple[int, int, int]] = {}

    def fight(def_idx: int, enemy_idx: int) -> Tuple[int, int, int]:
        k = (def_idx, enemy_idx)
        if k not in battle_cache:
            dst = pool[def_idx][2]
            est = all_enemies[enemy_idx][1]
            dcnt = max(1, round(battle_w / max(1.0, dst["width"]))) + 2
            ecnt = max(1, round(battle_w / max(1.0, est["width"]))) + 2
            res = simulate_battle_stats(
                est, dst,
                BattleConfig(terrain=config.terrain, attacker_count=ecnt, defender_count=dcnt, max_hours=240, seed=config.seed),
                gd, record_timeline=False,
            )
            hold = 1 if res["winner"] in ("defender", "draw") else 0
            battle_cache[k] = (
                res["defender_summary"]["manpower_lost"],
                res["attacker_summary"]["manpower_lost"],
                hold,
            )
        return battle_cache[k]

    steps_out: List[Dict[str, Any]] = []
    prev_winner_idx: Optional[int] = None

    for budget in range(config.start_ic, config.end_ic + 1, config.step_ic):
        enemy_cap = budget * config.enemy_mult
        eligible_enemies = [i for i, (_, est) in enumerate(all_enemies) if est["ic_cost"] <= enemy_cap]
        if not eligible_enemies:
            eligible_enemies = [0]

        # Candidates within budget B: focus on top frontier near B (and best from previous step)
        in_budget = [i for i, (_, _, st) in enumerate(pool) if st["ic_cost"] <= budget]
        if not in_budget:
            continue
        # Keep top 45 by (ic_cost descending, defense+soft+armor) so we test the richest & strongest options at budget B
        in_budget.sort(key=lambda i: (
            -min(budget, pool[i][2]["ic_cost"]),
            -(pool[i][2]["defense"] + pool[i][2]["soft"] * 2 + pool[i][2]["armor"] * 15),
        ))
        # Ensure diverse archetypes in the tested slice
        test_indices = list(dict.fromkeys(([prev_winner_idx] if prev_winner_idx is not None else []) + in_budget[:45]))

        best_row: Optional[Dict[str, Any]] = None
        best_score = -1e9
        best_idx = test_indices[0]

        for idx in test_indices:
            own_mp, en_mp, holds = 0, 0, 0
            for eidx in eligible_enemies:
                omp, emp, h = fight(idx, eidx)
                own_mp += omp
                en_mp += emp
                holds += h
            n = len(eligible_enemies)
            mp_ratio = en_mp / max(1.0, own_mp)
            hold_pct = holds / n * 100.0
            score = hold_pct * 0.70 + min(10.0, mp_ratio) * 15.0 + (en_mp - own_mp) / (n * 500.0)
            if score > best_score:
                best_score = score
                best_idx = idx
                label, tpl, st = pool[idx]
                best_row = {
                    "budget_ic": budget,
                    "enemy_max_ic": round(enemy_cap, 0),
                    "enemies_count": n,
                    "name": label,
                    "ic_cost": st["ic_cost"],
                    "width": st["width"],
                    "hardness": round(st["hardness"] * 100, 1),
                    "armor": st["armor"],
                    "pierce": st["pierce"],
                    "hold_pct": round(hold_pct, 1),
                    "avg_own_mp": round(own_mp / n, 0),
                    "avg_enemy_mp": round(en_mp / n, 0),
                    "mp_ratio": round(mp_ratio, 2),
                    "battalions": dict(tpl.battalions),
                    "support": list(tpl.support),
                    "regimental": list(tpl.regimental),
                }

        if best_row:
            prev_winner_idx = best_idx
            steps_out.append(best_row)

    return {
        "tech_year": config.tech_year,
        "terrain": gd.name(config.terrain),
        "doctrine": config.doctrine,
        "step_ic": config.step_ic,
        "enemy_mult": config.enemy_mult,
        "pool_size": len(pool),
        "elapsed_sec": round(time.perf_counter() - t0, 2),
        "steps": steps_out,
    }
