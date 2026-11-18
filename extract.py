"""Extract Hearts of Iron IV game data (units, equipment, tank modules, terrain,
tactics, defines, doctrine/equipment techs) into ``generated/game_data.json``.

Usage:  python -m hoi4_calculator.extract [path-to-Hearts-of-Iron-IV]
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .pdx import as_list, parse_file

OUT_FILE = Path(__file__).parent / "generated" / "game_data.json"

COMMON_STEAM_PATHS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV",
    r"C:\Program Files\Steam\steamapps\common\Hearts of Iron IV",
    r"D:\SteamLibrary\steamapps\common\Hearts of Iron IV",
    r"D:\Steam\steamapps\common\Hearts of Iron IV",
    r"E:\SteamLibrary\steamapps\common\Hearts of Iron IV",
    os.path.expanduser("~/.steam/steam/steamapps/common/Hearts of Iron IV"),
]

NAVAL_AIR_UNIT_FILES = {
    "air.txt", "battlecruiser.txt", "battleship.txt", "carrier.txt", "destroyer.txt", "heavy_cruiser.txt",
    "light_cruiser.txt", "repair_ships.txt", "submarine.txt", "support_ships.txt", "helicopter_brigade.txt",
}
LAND_EQUIPMENT_FILES = {
    "amphibious_mechanized.txt", "anti_air.txt", "anti_tank.txt", "armored_car.txt", "artillery.txt",
    "infantry.txt", "mechanized.txt", "motorized.txt", "support.txt", "specialist_armored_vehicles.txt",
    "tank_amphibious.txt", "tank_chassis.txt", "tank_heavy.txt", "tank_light.txt", "tank_medium.txt",
    "tank_modern.txt", "tank_super_heavy.txt", "railway_gun.txt", "emplacement_gun_ammo.txt", "x_tank_chassis.txt",
    "sam_missile.txt", "super_heavy_railway_gun.txt",
}


def find_game_dir(explicit: Optional[str] = None) -> Path:
    cands = [explicit] if explicit else []
    cands += [os.environ.get("HOI4_DIR")] + COMMON_STEAM_PATHS
    for c in cands:
        if c and (Path(c) / "common" / "units").is_dir():
            return Path(c)
    raise FileNotFoundError(
        "Не найдена папка Hearts of Iron IV. Передайте путь аргументом или переменной окружения HOI4_DIR."
    )


def read_version(game: Path) -> str:
    f = game / "launcher-settings.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("rawVersion", "?")
        except Exception:
            pass
    return "?"


# --------------------------------------------------------------------- localisation
_LOC_LINE = re.compile(r'^\s*([A-Za-z0-9_.\-\']+):\d*\s+"(.*)"\s*(?:#.*)?$')


def load_localisation(game: Path, lang: str) -> Dict[str, str]:
    loc: Dict[str, str] = {}
    d = game / "localisation" / lang
    if not d.is_dir():
        return loc
    for f in d.glob(f"*_l_{lang}.yml"):
        for line in f.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            m = _LOC_LINE.match(line)
            if m:
                loc[m.group(1)] = m.group(2)
    return loc


# --------------------------------------------------------------------- defines
def extract_defines(game: Path) -> Dict[str, Any]:
    text = (game / "common" / "defines" / "00_defines.lua").read_text(encoding="utf-8-sig", errors="replace")
    out: Dict[str, Any] = {}
    num = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*(-?[0-9.]+)\s*,")
    arr = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*\{([^}]*)\}\s*,")
    # multi-line arrays (PIERCING_THRESHOLDS etc.)
    for m in re.finditer(r"([A-Z0-9_]+)\s*=\s*\{([^{}]*)\}", text):
        vals = re.sub(r"--[^\n]*", "", m.group(2))
        nums = re.findall(r"-?\d+\.?\d*", vals)
        if nums and m.group(1) in {"PIERCING_THRESHOLDS", "PIERCING_THRESHOLD_DAMAGE_VALUES"}:
            out[m.group(1)] = [float(x) for x in nums]
    for line in text.splitlines():
        m = num.match(line)
        if m:
            out.setdefault(m.group(1), float(m.group(2)))
    keep = re.compile(
        r"^(LAND_COMBAT|COMBAT_|CHANCE_TO_AVOID|ENGAGEMENT|DAMAGE_SPLIT|PLANNING_|ARMOR_VS|SUPPLY_ORG|REINFORCE_CHANCE|"
        r"MAX_DIVISION|MAX_REGIMENTAL|MAX_DIVISION_SUPPORT|ATTRITION|AIR_SUPPORT_BASE|CAS_NIGHT|ANTI_AIR|"
        r"PIERCING|DEFAULT_MORALE|LAND_AIR|FASTER_ORG|SLOWER_ORG|RELIABILITY_ORG|TRUCK|BASE_CAPTURE|NIGHT|"
        r"EXPERIENCE|ARMY_INITIATIVE|PARADROP|ORG_|BASE_|MAX_|TACTIC|RECON|RIVER_CROSSING|DIG_IN|UNIT_DIGIN|"
        r"EQUIPMENT_COMBAT|RELIABIL)"
    )
    return {k: v for k, v in out.items() if keep.match(k)}


# --------------------------------------------------------------------- sub units
def extract_subunits(game: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    udir = game / "common" / "units"
    for f in sorted(udir.glob("*.txt")):
        if f.name in NAVAL_AIR_UNIT_FILES:
            continue
        data = parse_file(str(f))
        for k, v in (data.get("sub_units") or {}).items():
            if isinstance(v, dict) and "group" in v:
                v = dict(v)
                v["_file"] = f.name
                out[k] = v
    return out


# --------------------------------------------------------------------- equipment
def extract_equipment(game: Path):
    edir = game / "common" / "units" / "equipment"
    raw: Dict[str, dict] = {}
    for f in sorted(edir.glob("*.txt")):
        if f.name not in LAND_EQUIPMENT_FILES:
            continue
        data = parse_file(str(f))
        for k, v in (data.get("equipments") or {}).items():
            if isinstance(v, dict):
                v = dict(v)
                v["_file"] = f.name
                raw[k] = v

    def resolve(key: str, seen=()) -> dict:
        item = raw[key]
        base: dict = {}
        arch = item.get("archetype")
        if arch and arch in raw and arch not in seen:
            base = resolve(arch, seen + (key,))
        merged = dict(base)
        for kk, vv in item.items():
            merged[kk] = vv
        return merged

    resolved: Dict[str, dict] = {}
    for k in raw:
        try:
            r = resolve(k)
        except RecursionError:
            r = raw[k]
        for junk in ("can_be_produced", "module_slots", "allowed_module_categories", "upgrades",
                     "type", "picture", "sprite", "visual_level", "interface_category", "priority", "default_modules"):
            if junk in ("type", "module_slots", "default_modules"):
                continue
            r.pop(junk, None)
        r["_is_archetype"] = bool(raw[k].get("is_archetype"))
        resolved[k] = r
    return resolved


def extract_modules(game: Path) -> Dict[str, Any]:
    mdir = game / "common" / "units" / "equipment" / "modules"
    out: Dict[str, Any] = {}
    for f in sorted(mdir.glob("*tank*.txt")):
        data = parse_file(str(f))
        for blk in as_list(data.get("equipment_modules")):
            for k, v in blk.items():
                if isinstance(v, dict) and "category" in v:
                    out[k] = v
    return out


# --------------------------------------------------------------------- terrain / tactics
def extract_terrain(game: Path) -> Dict[str, Any]:
    data = parse_file(str(game / "common" / "terrain" / "00_terrain.txt"))
    return data.get("categories", {})


def extract_tactics(game: Path) -> Dict[str, Any]:
    data = parse_file(str(game / "common" / "combat_tactics.txt"))
    return {k: v for k, v in data.items() if k.startswith("tactic_")}


# --------------------------------------------------------------------- technologies
def extract_techs(game: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    tdir = game / "common" / "technologies"
    for f in ("infantry.txt", "support.txt", "armor.txt", "artillery.txt", "NSB_armor.txt"):
        p = tdir / f
        if not p.exists():
            continue
        data = parse_file(str(p))
        for blk in as_list(data.get("technologies")):
            for k, v in blk.items():
                if isinstance(v, dict):
                    v = dict(v)
                    for junk in ("ai_will_do", "path", "categories", "allow", "enable_equipments", "dependencies",
                                 "xor", "research_cost", "cost", "show_equipment_icon", "enable_subunits"):
                        if junk in ("enable_equipments", "enable_subunits"):
                            continue
                        v.pop(junk, None)
                    v["_file"] = f
                    out[k] = v
    return out


def _flatten_strings(v: Any) -> list:
    out: list = []
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, list):
        for x in v:
            out += _flatten_strings(x)
    elif isinstance(v, dict):
        for k, x in v.items():
            if k in ("__bare__",):
                out += _flatten_strings(x)
    return out


def extract_unlocks(techs: Dict[str, Any]) -> Dict[str, Any]:
    """Earliest start_year of the technology that unlocks a sub unit / equipment module."""
    sub: Dict[str, int] = {}
    mod: Dict[str, int] = {}
    for tid, t in techs.items():
        year = t.get("start_year", 1936)
        for s in _flatten_strings(t.get("enable_subunits")):
            sub[s] = min(sub.get(s, 9999), year)
        for m in _flatten_strings(t.get("enable_equipment_modules")):
            mod[m] = min(mod.get(m, 9999), year)
    return {"subunits": sub, "modules": mod}


_DOC_JUNK = {"icon", "description", "available", "ai_will_do", "xp_cost", "xp_type", "effect", "folder",
             "allowed", "background", "icon_frame", "cost", "ai_weight"}


def _strip_doc(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _strip_doc(x) for k, x in v.items() if k not in _DOC_JUNK}
    if isinstance(v, list):
        return [_strip_doc(x) for x in v]
    return v


def extract_doctrines(game: Path) -> Dict[str, Any]:
    base = game / "common" / "doctrines"
    out: Dict[str, Any] = {"grand": {}, "sub": {}, "tracks": {}}
    for f in (base / "grand_doctrines").glob("*.txt"):
        if f.name.startswith(("land", "special_forces")):
            for k, v in parse_file(str(f)).items():
                if isinstance(v, dict):
                    out["grand"][k] = _strip_doc(v)
    for sub_dir in ("land", "special_forces"):
        for f in (base / "subdoctrines" / sub_dir).glob("*.txt"):
            for k, v in parse_file(str(f)).items():
                if isinstance(v, dict):
                    out["sub"][k] = _strip_doc(v)
    for f in (base / "tracks").glob("*.txt"):
        if f.name.startswith(("land", "special_forces")):
            for k, v in parse_file(str(f)).items():
                if isinstance(v, dict):
                    out["tracks"][k] = _strip_doc(v)
    return out


def extract_all(game: Path) -> dict:
    loc_ru = load_localisation(game, "russian")
    loc_en = load_localisation(game, "english")
    data = {
        "game_version": read_version(game),
        "defines": extract_defines(game),
        "subunits": extract_subunits(game),
        "equipment": extract_equipment(game),
        "modules": extract_modules(game),
        "terrain": extract_terrain(game),
        "tactics": extract_tactics(game),
        "techs": extract_techs(game),
        "doctrines": extract_doctrines(game),
    }
    data["unlocks"] = extract_unlocks(data["techs"])
    # localisation – only keys we may need
    needed = set(data["subunits"]) | set(data["equipment"]) | set(data["modules"]) | set(data["techs"]) \
        | set(data["tactics"]) | set(data["terrain"])
    for grp in ("grand", "sub", "tracks"):
        for k, v in data["doctrines"][grp].items():
            needed.add(k)
            if isinstance(v.get("name"), str):
                needed.add(v["name"])
    for sub in data["doctrines"]["sub"].values():
        for rk in (sub.get("rewards") or {}):
            needed.add(rk)
    loc = {}
    for k in needed:
        for cand in (k, k.upper()):
            v = loc_ru.get(cand) or loc_en.get(cand)
            if v:
                loc[k] = v
                break
    for k in list(data["subunits"]):
        for cand in (k, k + "_name", k + "_short"):
            if cand in loc_ru and k not in loc:
                loc[k] = loc_ru[cand]
    data["loc"] = loc
    data["loc_en"] = {k: loc_en[k] for k in needed if k in loc_en}
    return data


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    game = find_game_dir(argv[0] if argv else None)
    data = extract_all(game)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Игра: {game}  (версия {data['game_version']})")
    for key in ("subunits", "equipment", "modules", "terrain", "tactics", "techs", "defines"):
        print(f"  {key}: {len(data[key])}")
    print(f"Сохранено: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
