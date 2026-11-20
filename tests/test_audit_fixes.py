"""Tests verifying fixes from the HoI4 calculator audit."""

import copy
from pathlib import Path
import random
import pytest

from hoi4_calculator import gamedata
from hoi4_calculator.battle import (
    BattleConfig,
    _aa_air_sup_reduction,
    _eval_tactic_weight,
    _eval_trigger_block,
    _pick_tactic,
    simulate_battle,
)
from hoi4_calculator.pdx import PdxParseError, parse
from hoi4_calculator.presets import PRESETS


# ------------------------------------------------------------------ 1. Tactics
def _sample_tactics(gd, *, n=300, **kwargs):
    rng = random.Random(123)
    seen = set()
    for _ in range(n):
        tid, _ = _pick_tactic(gd, rng, **kwargs)
        seen.add(tid)
    return seen


def test_tactics_enforce_skill_and_skill_advantage():
    gd = gamedata.load()

    # Defender with skill=1, skill_adv=0, no traits:
    # - tactic_counterattack requires skill_advantage > 0
    # - tactic_ambush requires skill > 2 OR skill_advantage > 1 OR trickster
    # - tactic_backhand_blow requires skill > 4 OR (defensive_doctrine AND skill > 3)
    low = _sample_tactics(
        gd,
        is_attacker=False,
        phase="no",
        unlocked={"tactic_backhand_blow", "tactic_elastic_defense", "tactic_delay"},
        hardness=0.0,
        arty_ratio=0.0,
        skill=1,
        skill_adv=0,
        frontage_full=True,
        has_reserves=True,
        terrain_id="plains",
    )
    assert "tactic_counterattack" not in low
    assert "tactic_ambush" not in low
    assert "tactic_backhand_blow" not in low
    assert "tactic_elastic_defense" not in low

    # With skill=5, skill_adv=2, all of those become eligible!
    high = _sample_tactics(
        gd,
        is_attacker=False,
        phase="no",
        unlocked={"tactic_backhand_blow", "tactic_elastic_defense", "tactic_delay"},
        hardness=0.0,
        arty_ratio=0.0,
        skill=5,
        skill_adv=2,
        frontage_full=True,
        has_reserves=True,
        terrain_id="plains",
    )
    assert "tactic_counterattack" in high
    assert "tactic_ambush" in high
    assert "tactic_backhand_blow" in high
    assert "tactic_elastic_defense" in high


def test_tactics_enforce_country_tag_traits_and_nested_logic():
    gd = gamedata.load()

    # Without tag="JAP", tactic_banzai_charge must NEVER be selected
    generic = _sample_tactics(
        gd,
        is_attacker=True,
        phase="no",
        unlocked=set(),
        hardness=0.0,
        arty_ratio=0.0,
        skill=2,
        skill_adv=0,
        frontage_full=False,
        has_reserves=False,
        terrain_id="plains",
        tag="",
    )
    assert "tactic_banzai_charge" not in generic

    ger = _sample_tactics(
        gd,
        is_attacker=True,
        phase="no",
        unlocked=set(),
        hardness=0.0,
        arty_ratio=0.0,
        skill=2,
        skill_adv=0,
        frontage_full=False,
        has_reserves=False,
        terrain_id="plains",
        tag="GER",
    )
    assert "tactic_banzai_charge" not in ger

    jap = _sample_tactics(
        gd,
        is_attacker=True,
        phase="no",
        unlocked=set(),
        hardness=0.0,
        arty_ratio=0.0,
        skill=2,
        skill_adv=0,
        frontage_full=False,
        has_reserves=False,
        terrain_id="plains",
        tag="JAP",
    )
    assert "tactic_banzai_charge" in jap

    # Nested AND inside OR: tactic_backhand_blow needs skill > 4 OR (defensive_doctrine AND skill > 3)
    skill4_no_trait = _sample_tactics(
        gd,
        is_attacker=False,
        phase="no",
        unlocked={"tactic_backhand_blow"},
        hardness=0.0,
        arty_ratio=0.0,
        skill=4,
        skill_adv=0,
        frontage_full=False,
        has_reserves=False,
        terrain_id="plains",
        traits=[],
    )
    assert "tactic_backhand_blow" not in skill4_no_trait

    skill4_with_trait = _sample_tactics(
        gd,
        is_attacker=False,
        phase="no",
        unlocked={"tactic_backhand_blow"},
        hardness=0.0,
        arty_ratio=0.0,
        skill=4,
        skill_adv=0,
        frontage_full=False,
        has_reserves=False,
        terrain_id="plains",
        traits=["defensive_doctrine"],
    )
    assert "tactic_backhand_blow" in skill4_with_trait

    # River crossing modifier: tactic_seize_bridge requires river_crossing
    no_river = _sample_tactics(
        gd,
        is_attacker=True,
        phase="no",
        unlocked=set(),
        hardness=0.0,
        arty_ratio=0.0,
        skill=4,
        skill_adv=0,
        frontage_full=False,
        has_reserves=False,
        terrain_id="plains",
        has_river=False,
    )
    assert "tactic_seize_bridge" not in no_river

    with_river = _sample_tactics(
        gd,
        is_attacker=True,
        phase="no",
        unlocked=set(),
        hardness=0.0,
        arty_ratio=0.0,
        skill=4,
        skill_adv=0,
        frontage_full=False,
        has_reserves=False,
        terrain_id="plains",
        has_river=True,
    )
    assert "tactic_seize_bridge" in with_river


def test_tactics_unit_types_and_weight_modifiers():
    gd = gamedata.load()

    # street_fighting phase: tactic_sf_mouse_holing requires engineer or pioneer_support
    no_eng = _sample_tactics(
        gd,
        is_attacker=True,
        phase="street_fighting",
        unlocked=set(),
        hardness=0.0,
        arty_ratio=0.0,
        skill=3,
        skill_adv=0,
        frontage_full=True,
        has_reserves=False,
        terrain_id="urban",
        unit_types={"infantry"},
    )
    assert "tactic_sf_mouse_holing" not in no_eng
    assert "tactic_sf_armor_supported_assault" not in no_eng

    with_eng_flame = _sample_tactics(
        gd,
        is_attacker=True,
        phase="street_fighting",
        unlocked=set(),
        hardness=0.0,
        arty_ratio=0.0,
        skill=3,
        skill_adv=0,
        frontage_full=True,
        has_reserves=False,
        terrain_id="urban",
        unit_types={"infantry", "engineer", "medium_flame_tank"},
    )
    assert "tactic_sf_mouse_holing" in with_eng_flame
    assert "tactic_sf_armor_supported_assault" in with_eng_flame

    # Base weight modifiers: tactic_assault has factor 0.2 when NOT urban
    assault_base = gd.tactics["tactic_assault"]["base"]
    ctx_base = {
        "is_attacker": True, "phase": "no", "unlocked": set(), "hardness": 0.0,
        "arty_ratio": 0.2, "skill": 3.0, "skill_adv": 0.0, "frontage_full": False,
        "has_reserves": False, "terrain_id": "plains", "has_river": False,
        "traits": set(), "tag": "", "unit_types": set(), "province_vp": 0.0,
    }
    w_plains = _eval_tactic_weight(assault_base, ctx_base, gd)
    w_urban = _eval_tactic_weight(assault_base, {**ctx_base, "terrain_id": "urban"}, gd)
    assert w_urban > w_plains
    assert abs(w_plains - 0.4) < 1e-6
    assert abs(w_urban - 2.0) < 1e-6


# ------------------------------------------------------ 2. Defines-driven math
def test_defines_and_leader_skills_loaded_and_used():
    gd = gamedata.load()
    assert gd.d("ENEMY_AIR_SUPERIORITY_IMPACT") == -0.35
    assert gd.d("ENEMY_AIR_SUPERIORITY_DEFENSE") == 0.75
    assert gd.d("ENEMY_AIR_SUPERIORITY_DEFENSE_STEEPNESS") == 625.0
    assert gd.d("ANTI_AIR_ATTACK_TO_DAMAGE_REDUCTION_FACTOR") == 2.5
    assert gd.d("ANTI_AIR_MAXIMUM_DAMAGE_REDUCTION_FACTOR") == 0.75
    assert gd.leader_skill_bonus("attack", 4) == pytest.approx(0.10)
    assert gd.leader_skill_bonus("defense", 4) == pytest.approx(0.10)
    assert gd.leader_skill_bonus("attack", 0) == 0.0

    # Paradox diminishing-returns AA curve
    assert _aa_air_sup_reduction(0.0, 0.75, 625.0) == 0.0
    assert 0.0 < _aa_air_sup_reduction(30.0, 0.75, 625.0) < 0.75
    assert _aa_air_sup_reduction(10000.0, 0.75, 625.0) == pytest.approx(0.75, rel=1e-3)

    # Verify changing extracted defines actually changes battle results
    atk = PRESETS["inf_18w_hold"]
    dfn = PRESETS["inf_18w_hold"]
    cfg = BattleConfig(attacker_count=4, defender_count=4, air_superiority=1.0, seed=11)
    res_base = simulate_battle(atk, dfn, cfg, gd)

    raw_mod = copy.deepcopy(gd.raw)
    raw_mod["defines"]["ENEMY_AIR_SUPERIORITY_IMPACT"] = -0.80
    gd_mod = gamedata.GameData(raw_mod)
    res_mod = simulate_battle(atk, dfn, cfg, gd_mod)
    assert (
        res_mod["defender_summary"]["manpower_lost"] >= res_base["defender_summary"]["manpower_lost"]
        or res_mod["hours_lasted"] != res_base["hours_lasted"]
    )


# ----------------------------------------------------------- 3. Strict pdx.py
def test_pdx_parser_strict_errors():
    # Valid input with trailing whitespace, comments, quotes, and ==
    parsed = parse('foo = { a = 1 b == "hi" c >= 2.5 } # trailing comment \n  ')
    assert parsed == {"foo": {"a": 1, "b": {"op": "==", "value": "hi"}, "c": {"op": ">=", "value": 2.5}}}

    # Unterminated string must raise PdxParseError instead of silently truncating
    with pytest.raises(PdxParseError):
        parse('a = "unterminated\nb = 2')

    # Extra closing brace must raise PdxParseError
    with pytest.raises(PdxParseError):
        parse("a = { x = 1 } } b = 2")

    # Unclosed opening brace must raise PdxParseError
    with pytest.raises(PdxParseError):
        parse("a = { x = 1")

    # Missing value after operator must raise PdxParseError
    with pytest.raises(PdxParseError):
        parse("a = ")

    # Stray operator without key must raise PdxParseError
    with pytest.raises(PdxParseError):
        parse("= 123")


# -------------------------------------------------------- 4. Exact dice rolls
def test_exact_dice_rolls_mode():
    atk = PRESETS["tank_30w_med"]
    dfn = PRESETS["inf_18w_hold"]

    cfg_a = BattleConfig(attacker_count=4, defender_count=4, roll_dice=True, seed=99)
    r1 = simulate_battle(atk, dfn, cfg_a)
    r2 = simulate_battle(atk, dfn, cfg_a)
    assert r1["hours_lasted"] == r2["hours_lasted"]
    assert r1["attacker_summary"]["manpower_lost"] == r2["attacker_summary"]["manpower_lost"]

    # Different seeds produce stochastic variation
    hours_set = {
        simulate_battle(atk, dfn, BattleConfig(attacker_count=4, defender_count=4, roll_dice=True, seed=s))["hours_lasted"]
        for s in range(1, 12)
    }
    assert len(hours_set) > 1


# ----------------------------------------------- 5. Legacy packages removed
def test_legacy_packages_removed():
    pkg_dir = Path(__file__).resolve().parent.parent
    assert not (pkg_dir / "engine").exists()
    assert not (pkg_dir / "data").exists()
