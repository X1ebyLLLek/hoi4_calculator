"""Minimal parser for Paradox script files (.txt) used by Hearts of Iron IV.

Result is a plain nested structure:
  * a block is ``dict`` (key -> value); a key that occurs several times becomes ``list`` of values
  * a block holding only bare words/numbers (``{ a b c }``) becomes ``list``
  * scalars are ``int`` / ``float`` / ``bool`` (yes/no) / ``str``
Comparison operators (``>``, ``<``, ``>=``) are kept as ``{"op": ">", "value": x}``.
"""

import re
from typing import Any, List, Tuple

_TOKEN = re.compile(
    r'\s*(?:(#[^\n]*)|("(?:[^"\\]|\\.)*")|([{}])|(>=|<=|!=|=|>|<)|([^\s{}=<>"#]+))'
)


def _tokens(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    pos, n = 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            break
        pos = m.end()
        comment, string, brace, op, word = m.groups()
        if comment is not None:
            continue
        if string is not None:
            out.append(("str", string[1:-1]))
        elif brace:
            out.append((brace, brace))
        elif op:
            out.append(("op", op))
        elif word:
            out.append(("word", word))
    return out


def _scalar(word: str) -> Any:
    if word == "yes":
        return True
    if word == "no":
        return False
    try:
        return int(word)
    except ValueError:
        pass
    try:
        return float(word)
    except ValueError:
        return word


def _add(d: dict, key: str, value: Any) -> None:
    if key in d:
        if isinstance(d[key], list) and d.get("__multi__", set()) and key in d["__multi__"]:
            d[key].append(value)
        else:
            d.setdefault("__multi__", set()).add(key)
            d[key] = [d[key], value]
    else:
        d[key] = value


def _parse_block(toks: List[Tuple[str, str]], i: int) -> Tuple[Any, int]:
    """Parse tokens after '{' until matching '}'."""
    d: dict = {}
    bare: list = []
    n = len(toks)
    while i < n:
        kind, val = toks[i]
        if kind == "}":
            i += 1
            break
        if kind == "{":  # anonymous nested block
            sub, i = _parse_block(toks, i + 1)
            bare.append(sub)
            continue
        if kind in ("word", "str"):
            if i + 1 < n and toks[i + 1][0] == "op":
                op = toks[i + 1][1]
                if i + 2 < n and toks[i + 2][0] == "{":
                    value, i = _parse_block(toks, i + 3)
                elif i + 2 < n:
                    value = _scalar(toks[i + 2][1]) if toks[i + 2][0] == "word" else toks[i + 2][1]
                    i += 3
                else:
                    i += 2
                    continue
                if op != "=":
                    value = {"op": op, "value": value}
                _add(d, val, value)
                continue
            bare.append(_scalar(val) if kind == "word" else val)
            i += 1
            continue
        i += 1
    if bare and not d:
        return bare, i
    if bare:
        d["__bare__"] = bare
    return d, i


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        obj.pop("__multi__", None)
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def parse(text: str) -> dict:
    toks = _tokens(text)
    root, _ = _parse_block(toks + [("}", "}")], 0)
    return _clean(root) if isinstance(root, dict) else {"__bare__": root}


def parse_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return parse(f.read())


def as_list(v: Any) -> list:
    """Normalise a possibly-repeated key to a list."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
