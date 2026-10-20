#!/usr/bin/env python3
"""Строка статуса Claude Code: лимиты 5h/7d, время сброса и заполненность контекста.

Claude Code передаёт на stdin JSON сессии; печатаем одну строку с ANSI-цветами.
"""
import json
import os
import re
import sys
import time
from datetime import datetime

CTX_CEIL = 300_000  # потолок контекста для шкалы
BAR_W = 10

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
BLUE = "\033[38;2;120;160;220m"
ORANGE = "\033[38;2;245;140;40m"

# Опорные точки градиента: зелёный → жёлтый → оранжевый → красный
STOPS = [(0.0, (80, 200, 80)), (1 / 3, (230, 210, 60)), (2 / 3, (245, 140, 40)), (1.0, (230, 60, 60))]


def color(frac):
    frac = max(0.0, min(1.0, frac))
    for (f0, c0), (f1, c1) in zip(STOPS, STOPS[1:]):
        if frac <= f1:
            t = (frac - f0) / (f1 - f0)
            r, g, b = (round(a + (b_ - a) * t) for a, b_ in zip(c0, c1))
            return f"\033[38;2;{r};{g};{b}m"
    return "\033[38;2;230;60;60m"


def bar(frac):
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * BAR_W)
    return f"{color(frac)}{'█' * filled}{DIM}{'░' * (BAR_W - filled)}{RESET}"


def to_epoch(v):
    """resets_at может прийти секундами эпохи или ISO-строкой."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e12 else v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def until(ts):
    left = int(ts - time.time())
    if left <= 0:
        return "now"
    d, rem = divmod(left, 86400)
    if d:
        return f"{d}d {rem // 3600}h"
    h, m = divmod(rem // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def limit_part(label, lim, fmt_reset):
    label = f"{BOLD}{label}:{RESET}"
    if not lim or lim.get("used_percentage") is None:
        return f"{label} {DIM}—{RESET}"
    pct = float(lim["used_percentage"])
    s = f"{label} {bar(pct / 100)} {color(pct / 100)}{pct:.0f}%{RESET}"
    ts = to_epoch(lim.get("resets_at"))
    if ts:
        s += f" {DIM}⟳{RESET} {BLUE}{fmt_reset(ts)}{RESET}"
    return s


def ctx_tokens(cw):
    cur = cw.get("current_usage") or {}
    if cur:
        return sum(cur.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return cw.get("total_input_tokens")


def fmt_k(n):
    return f"{n / 1000:.0f}k" if n >= 1000 else str(n)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    model = (data.get("model") or {}).get("display_name") or (data.get("model") or {}).get("id")
    cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or os.getcwd()
    cwd = "~" if cwd.rstrip(os.sep) == os.path.expanduser("~") else os.path.basename(cwd.rstrip(os.sep)) or cwd

    rl = data.get("rate_limits") or {}
    parts = [
        limit_part("5h", rl.get("five_hour"), until),
        limit_part("7d", rl.get("seven_day"), until),
    ]

    cw = data.get("context_window") or {}
    tokens = ctx_tokens(cw)
    if tokens is None:
        parts.append(f"{BOLD}ctx:{RESET} {bar(0)} {DIM}—{RESET}")
    else:
        frac = tokens / CTX_CEIL
        parts.append(f"{BOLD}ctx:{RESET} {bar(frac)} {color(frac)}{fmt_k(tokens)}{RESET}{DIM}/{fmt_k(CTX_CEIL)}{RESET}")

    sep = f" {DIM}│{RESET} "
    # Первая строка — шкалы, под ней папка и модель
    top = sep.join(parts)
    print(top)
    # Бледная черта-разделитель во всю ширину верхней строки
    print(f"{DIM}{'─' * len(re.sub(r'\033\[[0-9;]*m', '', top))}{RESET}")
    eff = data.get("effort")
    eff = (eff.get("level") if isinstance(eff, dict) else eff) or os.environ.get("CLAUDE_EFFORT")
    # Терминал не умеет мелкий шрифт — effort приглушённым цветом
    eff_s = f" {DIM}{eff}{RESET}" if eff else ""
    print(sep.join([f"{ORANGE}{model or '—'}{RESET}{eff_s}", f"\033[36m{cwd}{RESET}"]))


if __name__ == "__main__":
    main()
