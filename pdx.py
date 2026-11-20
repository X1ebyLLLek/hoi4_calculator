"""Minimal strict parser for Paradox script files (.txt) used by Hearts of Iron IV.

Result is a plain nested structure:
  * a block is ``dict`` (key -> value); a key that occurs several times becomes ``list`` of values
  * a block holding only bare words/numbers (``{ a b c }``) becomes ``list``
  * scalars are ``int`` / ``float`` / ``bool`` (yes/no) / ``str``
Comparison operators (``>``, ``<``, ``>=``, ``<=``, ``!=``, ``==``) are kept as
``{"op": ">", "value": x}``.

Raises ``PdxParseError`` on unrecognized tokens, unterminated strings, or
malformed/unbalanced blocks instead of silently truncating the input.
"""

import re
from typing import Any, List, Tuple

_WS = re.compile(r"\s*")
_TOKEN = re.compile(
    r'(?:(#[^\n]*)|("(?:[^"\\]|\\.)*")|([{}])|(>=|<=|!=|==|=|>|<)|([^\s{}=<>"#]+))'
)


class PdxParseError(ValueError):
    """Raised when a Paradox script file contains invalid or unexpected syntax."""

    def __init__(self, message: str, source: str = "<string>", line: int = 1, col: int = 1):
        self.source = source
        self.line = line
        self.col = col
        super().__init__(f"{source}:{line}:{col}: {message}")


def _line_col(text: str, pos: int) -> Tuple[int, int]:
    line = text.count("\n", 0, pos) + 1
    last_nl = text.rfind("\n", 0, pos)
    col = pos - last_nl if last_nl != -1 else pos + 1
    return line, col


def _tokens(text: str, source: str = "<string>") -> List[Tuple[str, str, int]]:
    out: List[Tuple[str, str, int]] = []
    pos, n = 0, len(text)
    if text.startswith("\ufeff"):
        pos = 1
    while pos < n:
        pos = _WS.match(text, pos).end()
        if pos >= n:
            break
        m = _TOKEN.match(text, pos)
        if not m:
            line, col = _line_col(text, pos)
            snippet = text[pos : pos + 30].replace("\n", "\\n")
            raise PdxParseError(f"unexpected character or unterminated string near {snippet!r}", source, line, col)
        tok_pos = pos
        pos = m.end()
        comment, string, brace, op, word = m.groups()
        if comment is not None:
            continue
        if string is not None:
            out.append(("str", string[1:-1], tok_pos))
        elif brace:
            out.append((brace, brace, tok_pos))
        elif op:
            out.append(("op", op, tok_pos))
        elif word:
            out.append(("word", word, tok_pos))
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


def _parse_block(
    toks: List[Tuple[str, str, int]],
    i: int,
    text: str,
    source: str,
    *,
    is_root: bool = False,
    open_pos: int = 0,
) -> Tuple[Any, int]:
    """Parse tokens after '{' until matching '}' (or EOF when ``is_root`` is True)."""
    d: dict = {}
    bare: list = []
    n = len(toks)
    closed = False
    while i < n:
        kind, val, tok_pos = toks[i]
        if kind == "}":
            if is_root:
                line, col = _line_col(text, tok_pos)
                raise PdxParseError("unexpected closing brace '}'", source, line, col)
            i += 1
            closed = True
            break
        if kind == "{":  # anonymous nested block
            sub, i = _parse_block(toks, i + 1, text, source, is_root=False, open_pos=tok_pos)
            bare.append(sub)
            continue
        if kind in ("word", "str"):
            if i + 1 < n and toks[i + 1][0] == "op":
                op = toks[i + 1][1]
                op_pos = toks[i + 1][2]
                if i + 2 >= n:
                    line, col = _line_col(text, op_pos)
                    raise PdxParseError(f"missing value after operator {op!r} for key {val!r}", source, line, col)
                v_kind, v_val, v_pos = toks[i + 2]
                if v_kind == "{":
                    value, i = _parse_block(toks, i + 3, text, source, is_root=False, open_pos=v_pos)
                elif v_kind in ("word", "str"):
                    value = _scalar(v_val) if v_kind == "word" else v_val
                    i += 3
                else:
                    line, col = _line_col(text, v_pos)
                    raise PdxParseError(f"unexpected token {v_val!r} after operator {op!r}", source, line, col)
                if op != "=":
                    value = {"op": op, "value": value}
                _add(d, val, value)
                continue
            bare.append(_scalar(val) if kind == "word" else val)
            i += 1
            continue
        line, col = _line_col(text, tok_pos)
        raise PdxParseError(f"unexpected token {val!r}", source, line, col)

    if not is_root and not closed:
        line, col = _line_col(text, open_pos)
        raise PdxParseError("unclosed block '{'", source, line, col)

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


def parse(text: str, source: str = "<string>") -> dict:
    toks = _tokens(text, source=source)
    root, _ = _parse_block(toks, 0, text, source, is_root=True)
    return _clean(root) if isinstance(root, dict) else {"__bare__": root}


def parse_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return parse(f.read(), source=str(path))


def as_list(v: Any) -> list:
    """Normalise a possibly-repeated key to a list."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
