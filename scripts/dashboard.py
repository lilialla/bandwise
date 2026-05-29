#!/usr/bin/env python3
"""Bandwise IELTS progress dashboard generator.

Scans the Bandwise archive (Markdown files with YAML frontmatter produced by
the IELTS-prep Claude Code skills) and renders a single self-contained
``dashboard.html`` with inline SVG charts. No third-party dependencies are
used: only the Python 3 standard library. The output HTML embeds all styling
and chart geometry inline so it opens offline by double-click.

Data root resolution order:
  1. ``--root <path>`` CLI argument
  2. ``IELTS_COACH_HOME`` environment variable
  3. ``~/ielts-coach`` default

Usage:
  python3 dashboard.py [--root PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import html
import os
import sys
from datetime import datetime, timedelta, date

# --- Tunable constants -----------------------------------------------------

# Target band per skill used to draw the reference line on the radar chart.
TARGET_SCORES = {"L": 8.0, "R": 8.0, "W": 7.0, "S": 7.0}

# Color palette.
COL_OPUS = "#2563eb"
COL_GPT5 = "#db2777"
COL_TARGET = "#94a3b8"
COL_ACTUAL = "#16a34a"
COL_BAR = "#7c3aed"
COL_GRID = "#e2e8f0"
COL_AXIS = "#64748b"
COL_LISTEN = "#0891b2"


# ---------------------------------------------------------------------------
# Minimal YAML frontmatter parser
# ---------------------------------------------------------------------------

def _coerce_scalar(token):
    """Convert a raw scalar string into a Python value."""
    token = token.strip()
    if token == "" or token == "~":
        return None
    low = token.lower()
    if low == "null":
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    # Strip matching quotes.
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    # Numbers.
    try:
        if any(c in token for c in (".", "e", "E")) and token not in ("-", "+"):
            return float(token)
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


def _parse_inline(text):
    """Parse an inline ``{...}`` dict or ``[...]`` list (best effort)."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        body = text[1:-1].strip()
        result = {}
        for part in _split_top_level(body):
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            result[k.strip()] = _parse_value(v.strip())
        return result
    if text.startswith("[") and text.endswith("]"):
        body = text[1:-1].strip()
        if not body:
            return []
        return [_parse_value(p.strip()) for p in _split_top_level(body)]
    return _coerce_scalar(text)


def _split_top_level(body):
    """Split on commas that are not inside nested brackets/braces/quotes."""
    parts = []
    depth = 0
    quote = None
    buf = []
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch in "{[":
            depth += 1
            buf.append(ch)
            continue
        if ch in "}]":
            depth -= 1
            buf.append(ch)
            continue
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in parts if p.strip() != ""]


def _parse_value(text):
    """Parse a value that may be inline structured or a plain scalar."""
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return _parse_inline(text)
    return _coerce_scalar(text)


def _indent_of(line):
    return len(line) - len(line.lstrip(" "))


def _parse_block(lines, idx, base_indent):
    """Recursively parse a block of YAML lines starting at ``idx``.

    Returns (value, next_idx). ``value`` is a dict or list depending on the
    first meaningful line at ``base_indent``.
    """
    result_map = {}
    result_list = []
    is_list = None

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()

        # Blank lines and comments are skipped.
        if stripped == "" or stripped.startswith("#"):
            idx += 1
            continue

        indent = _indent_of(raw)
        if indent < base_indent:
            break

        if indent > base_indent:
            # Should have been consumed by a child parse; skip defensively.
            idx += 1
            continue

        # List item.
        if stripped.startswith("- "):
            is_list = True
            item_text = stripped[2:].strip()
            if item_text.startswith("{") or item_text.startswith("["):
                result_list.append(_parse_inline(item_text))
                idx += 1
            elif item_text == "" or item_text.endswith(":"):
                # Nested block item.
                value, idx = _parse_block(lines, idx + 1, base_indent + 2)
                result_list.append(value)
            else:
                result_list.append(_parse_value(item_text))
                idx += 1
            continue
        if stripped == "-":
            is_list = True
            value, idx = _parse_block(lines, idx + 1, base_indent + 2)
            result_list.append(value)
            continue

        # Mapping line.
        if ":" not in stripped:
            idx += 1
            continue
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        is_list = False if is_list is None else is_list

        if rest in ("|", ">", "|-", ">-", "|+", ">+"):
            # Multi-line scalar block: skip its body, store as None.
            idx += 1
            while idx < len(lines):
                nxt = lines[idx]
                if nxt.strip() == "":
                    idx += 1
                    continue
                if _indent_of(nxt) > base_indent:
                    idx += 1
                    continue
                break
            result_map[key] = None
            continue

        if rest == "":
            # Could be a nested map, nested list, or empty value.
            # Look ahead at the next meaningful line.
            look = idx + 1
            while look < len(lines) and (
                lines[look].strip() == "" or lines[look].strip().startswith("#")
            ):
                look += 1
            if look < len(lines) and _indent_of(lines[look]) > base_indent:
                value, idx = _parse_block(lines, look, _indent_of(lines[look]))
                result_map[key] = value
            else:
                result_map[key] = None
                idx += 1
            continue

        # Inline value.
        result_map[key] = _parse_value(rest)
        idx += 1

    if is_list:
        return result_list, idx
    return result_map, idx


def parse_frontmatter(text):
    """Extract and parse the YAML frontmatter block from a file's text."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}
    block = lines[1:end]
    value, _ = _parse_block(block, 0, 0)
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _read_md_dir(path):
    """Return list of parsed frontmatter dicts for all .md files in path."""
    records = []
    if not os.path.isdir(path):
        return records
    for name in sorted(os.listdir(path)):
        if not name.endswith(".md"):
            continue
        fpath = os.path.join(path, name)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        fm = parse_frontmatter(text)
        if fm:
            fm["_file"] = name
            records.append(fm)
    return records


def load_data(root):
    return {
        "writing": _read_md_dir(os.path.join(root, "writing")),
        "listening": _read_md_dir(os.path.join(root, "listening")),
        "reading": _read_md_dir(os.path.join(root, "reading")),
        "mock": _read_md_dir(os.path.join(root, "mock")),
    }


def read_exam_date(root, cli_exam_date):
    """Resolve exam date: CLI arg > study-plan.md frontmatter `exam_date` > None."""
    if cli_exam_date:
        return _parse_date(cli_exam_date)
    plan = os.path.join(root, "study-plan.md")
    if os.path.isfile(plan):
        try:
            with open(plan, encoding="utf-8") as fh:
                fm = parse_frontmatter(fh.read())
            return _parse_date(fm.get("exam_date"))
        except OSError:
            return None
    return None


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Small helpers for safe access
# ---------------------------------------------------------------------------

def _as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _esc(value):
    return html.escape(str(value))


def _fmt(value):
    """Format a number without a trailing .0; pass through non-numbers."""
    if isinstance(value, float):
        return ("%.1f" % value).rstrip("0").rstrip(".")
    return str(value)


# ---------------------------------------------------------------------------
# SVG chart builders
# ---------------------------------------------------------------------------

def _no_data():
    return '<p class="nodata">暂无数据</p>'


def line_chart(series, width=520, height=240, ylabel="", y_min=None, y_max=None):
    """Render a multi-line chart.

    series: list of dicts {label, color, points: [(x_label, y_value), ...]}
    Only points with numeric y are plotted.
    """
    pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    # Collect all x labels (preserve order from the first non-empty series'
    # x sequence) and all y values.
    x_labels = []
    all_y = []
    for s in series:
        for xl, yv in s["points"]:
            if xl not in x_labels:
                x_labels.append(xl)
            if yv is not None:
                all_y.append(yv)
    if not all_y or not x_labels:
        return _no_data()

    lo = y_min if y_min is not None else min(all_y)
    hi = y_max if y_max is not None else max(all_y)
    if hi == lo:
        hi = lo + 1.0
        lo = lo - 1.0
    # Add a little headroom.
    span = hi - lo
    lo -= span * 0.08
    hi += span * 0.08

    n = len(x_labels)
    if n == 1:
        x_at = {x_labels[0]: pad_l + plot_w / 2.0}
    else:
        x_at = {
            xl: pad_l + (i / (n - 1)) * plot_w for i, xl in enumerate(x_labels)
        }

    def y_at(v):
        return pad_t + plot_h - ((v - lo) / (hi - lo)) * plot_h

    parts = ['<svg viewBox="0 0 %d %d" class="chart" role="img">' % (width, height)]

    # Grid lines + y ticks.
    ticks = 4
    for t in range(ticks + 1):
        val = lo + (hi - lo) * t / ticks
        yy = y_at(val)
        parts.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
            'stroke-width="1"/>' % (pad_l, yy, width - pad_r, yy, COL_GRID)
        )
        parts.append(
            '<text x="%.1f" y="%.1f" class="ytick">%.1f</text>'
            % (pad_l - 6, yy + 3, val)
        )

    # X labels (show first, middle, last to avoid clutter).
    show_idx = {0, n - 1, n // 2}
    for i, xl in enumerate(x_labels):
        if i in show_idx:
            xx = x_at[xl]
            parts.append(
                '<text x="%.1f" y="%.1f" class="xtick">%s</text>'
                % (xx, height - pad_b + 18, _esc(xl))
            )

    # Plot each series.
    for s in series:
        pts = [
            (x_at[xl], y_at(yv), xl, yv)
            for xl, yv in s["points"]
            if yv is not None and xl in x_at
        ]
        if not pts:
            continue
        if len(pts) >= 2:
            d = "M " + " L ".join("%.1f %.1f" % (p[0], p[1]) for p in pts)
            parts.append(
                '<path d="%s" fill="none" stroke="%s" stroke-width="2.5"/>'
                % (d, s["color"])
            )
        for px, py, xl, yv in pts:
            tip = "%s · %s %s" % (_esc(xl), _esc(s["label"]), _fmt(yv))
            parts.append(
                '<circle class="pt" cx="%.1f" cy="%.1f" r="4.5" fill="%s" '
                'data-tip="%s"/>' % (px, py, s["color"], tip)
            )

    parts.append("</svg>")

    # Legend.
    legend = ['<div class="legend">']
    for s in series:
        if any(yv is not None for _, yv in s["points"]):
            legend.append(
                '<span class="lg"><i style="background:%s"></i>%s</span>'
                % (s["color"], _esc(s["label"]))
            )
    legend.append("</div>")

    label_html = (
        '<div class="ylabel">%s</div>' % _esc(ylabel) if ylabel else ""
    )
    return label_html + "".join(parts) + "".join(legend)


def radar_chart(scores, target, size=320):
    """Render a 4-axis radar (L, R, W, S) actual vs target."""
    axes = ["L", "R", "W", "S"]
    actual = [_as_float(scores.get(a)) for a in axes]
    if not any(v is not None for v in actual):
        return _no_data()

    cx = cy = size / 2.0
    radius = size / 2.0 - 46
    max_band = 9.0
    import math

    # Axis angles: top, right, bottom, left.
    angles = [-math.pi / 2 + i * (2 * math.pi / len(axes)) for i in range(len(axes))]

    def point(value, angle):
        r = (value / max_band) * radius
        return (cx + r * math.cos(angle), cy + r * math.sin(angle))

    parts = ['<svg viewBox="0 0 %d %d" class="chart radar" role="img">' % (size, size)]

    # Concentric grid rings at bands 3,5,7,9.
    for band in (3, 5, 7, 9):
        ring = [point(band, a) for a in angles]
        d = "M " + " L ".join("%.1f %.1f" % p for p in ring) + " Z"
        parts.append(
            '<path d="%s" fill="none" stroke="%s" stroke-width="1"/>'
            % (d, COL_GRID)
        )

    # Spokes + axis labels.
    for a, name in zip(angles, axes):
        ex, ey = point(max_band, a)
        parts.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
            'stroke-width="1"/>' % (cx, cy, ex, ey, COL_GRID)
        )
        lx, ly = point(max_band + 0.9, a)
        parts.append(
            '<text x="%.1f" y="%.1f" class="raxis">%s</text>' % (lx, ly + 4, name)
        )

    # Target polygon.
    tgt_pts = [point(_as_float(target.get(a)) or 0.0, ang) for a, ang in zip(axes, angles)]
    d_t = "M " + " L ".join("%.1f %.1f" % p for p in tgt_pts) + " Z"
    parts.append(
        '<path d="%s" fill="none" stroke="%s" stroke-width="2" '
        'stroke-dasharray="5 4"/>' % (d_t, COL_TARGET)
    )

    # Actual polygon (use 0 for missing axes so the shape closes).
    act_pts = [point(v if v is not None else 0.0, ang) for v, ang in zip(actual, angles)]
    d_a = "M " + " L ".join("%.1f %.1f" % p for p in act_pts) + " Z"
    parts.append(
        '<path d="%s" fill="%s" fill-opacity="0.18" stroke="%s" '
        'stroke-width="2.5"/>' % (d_a, COL_ACTUAL, COL_ACTUAL)
    )
    for (px, py), v in zip(act_pts, actual):
        if v is not None:
            parts.append('<circle cx="%.1f" cy="%.1f" r="3" fill="%s"/>' % (px, py, COL_ACTUAL))

    parts.append("</svg>")

    legend = (
        '<div class="legend">'
        '<span class="lg"><i style="background:%s"></i>最近模考</span>'
        '<span class="lg"><i style="background:%s"></i>目标</span></div>'
        % (COL_ACTUAL, COL_TARGET)
    )
    return "".join(parts) + legend


def hbar_chart(pairs, width=520, bar_h=24, gap=10):
    """Render a horizontal bar chart from [(label, count), ...] (pre-sorted)."""
    if not pairs:
        return _no_data()
    pad_l, pad_r, pad_t = 150, 40, 8
    n = len(pairs)
    height = pad_t + n * (bar_h + gap) + 8
    plot_w = width - pad_l - pad_r
    max_v = max(c for _, c in pairs) or 1

    parts = ['<svg viewBox="0 0 %d %d" class="chart" role="img">' % (width, height)]
    for i, (label, count) in enumerate(pairs):
        y = pad_t + i * (bar_h + gap)
        bw = (count / max_v) * plot_w
        parts.append(
            '<text x="%d" y="%.1f" class="blabel">%s</text>'
            % (pad_l - 8, y + bar_h * 0.7, _esc(label))
        )
        # track behind the bar for a cleaner look
        parts.append(
            '<rect x="%d" y="%.1f" width="%.1f" height="%d" rx="5" class="bartrack"/>'
            % (pad_l, y, plot_w, bar_h)
        )
        parts.append(
            '<rect class="bar" x="%d" y="%.1f" width="%.1f" height="%d" rx="5" '
            'fill="%s" data-tip="%s · %d 次"/>'
            % (pad_l, y, bw, bar_h, COL_BAR, _esc(label), count)
        )
        parts.append(
            '<text x="%.1f" y="%.1f" class="bval">%d</text>'
            % (pad_l + bw + 8, y + bar_h * 0.7, count)
        )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Section assembly
# ---------------------------------------------------------------------------

def build_writing_trend(writing):
    opus_pts = []
    gpt5_pts = []
    rows = []
    for rec in writing:
        date = rec.get("date") or rec.get("_file", "")
        opus = _as_float(_get(rec, "ai_scores", "opus", "overall"))
        gpt5 = _as_float(_get(rec, "ai_scores", "gpt5", "overall"))
        rows.append((str(date), opus, gpt5))
    rows.sort(key=lambda r: r[0])
    for date, opus, gpt5 in rows:
        opus_pts.append((date, opus))
        gpt5_pts.append((date, gpt5))
    series = [{"label": "Opus 总分", "color": COL_OPUS, "points": opus_pts}]
    if any(g is not None for _, g in gpt5_pts):
        series.append({"label": "GPT-5 总分", "color": COL_GPT5, "points": gpt5_pts})
    return line_chart(series, ylabel="分数", y_min=4.0, y_max=9.0)


def build_radar(mock):
    if not mock:
        return _no_data()
    rows = sorted(mock, key=lambda r: str(r.get("date") or r.get("_file", "")))
    latest = rows[-1]
    scores = _get(latest, "scores") or {}
    if not isinstance(scores, dict):
        return _no_data()
    return radar_chart(scores, TARGET_SCORES)


def build_error_bars(writing, listening):
    counts = {}
    for rec in list(writing) + list(listening):
        errs = rec.get("errors")
        if not isinstance(errs, list):
            continue
        for e in errs:
            if not isinstance(e, dict):
                continue
            tag = e.get("tag")
            if tag is None:
                continue
            inc = e.get("count")
            inc = inc if isinstance(inc, int) and inc > 0 else 1
            counts[str(tag)] = counts.get(str(tag), 0) + inc
    if not counts:
        return _no_data()
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return hbar_chart(top)


def build_listening_trend(listening):
    rows = []
    for rec in listening:
        date = str(rec.get("date") or rec.get("_file", ""))
        total = rec.get("total_questions")
        correct = rec.get("correct_count")
        pct = None
        if isinstance(total, (int, float)) and total and isinstance(correct, (int, float)):
            pct = round(100.0 * correct / total, 1)
        rows.append((date, pct))
    rows.sort(key=lambda r: r[0])
    series = [{"label": "正确率 %", "color": COL_LISTEN, "points": rows}]
    return line_chart(series, ylabel="%", y_min=0.0, y_max=100.0)


def _all_records(data):
    out = []
    for key in ("writing", "listening", "reading", "mock"):
        for rec in data.get(key, []):
            out.append((key, rec))
    return out


def _rec_date(rec):
    return str(rec.get("date") or rec.get("_file", ""))[:10]


def _is_date(s):
    return len(s) == 10 and s[4] == "-" and s[7] == "-"


def _activity_counts(data):
    counts = {}
    for _key, rec in _all_records(data):
        d = _rec_date(rec)
        if _is_date(d):
            counts[d] = counts.get(d, 0) + 1
    return counts


def _latest_overall(mock):
    if not mock:
        return None
    rows = sorted(mock, key=_rec_date)
    return _as_float(_get(rows[-1], "scores", "overall"))


def build_kpis(data):
    open_verif = 0
    for _k, rec in _all_records(data):
        ov = rec.get("open_verifications")
        if isinstance(ov, list):
            open_verif += len(ov)
    latest = _latest_overall(data["mock"])
    cards = [
        ("写作篇数", len(data["writing"]), "var(--c-writing)"),
        ("听力套数", len(data["listening"]), "var(--c-listen)"),
        ("模考次数", len(data["mock"]), "var(--c-mock)"),
        ("学习活跃天数", len(_activity_counts(data)), "var(--c-streak)"),
        ("最近模考总分", _fmt(latest) if latest is not None else "—", "var(--c-target)"),
        ("待核验项", open_verif, "var(--c-warn)"),
    ]
    items = "".join(
        '<div class="card" style="--accent:%s"><div class="cval">%s</div>'
        '<div class="clabel">%s</div></div>' % (accent, _esc(v), _esc(lbl))
        for lbl, v, accent in cards
    )
    return '<div class="cards">%s</div>' % items


def _progress_ring(cur, target, size=148):
    import math
    r = size / 2.0 - 13
    circ = 2 * math.pi * r
    frac = 0.0 if not cur or not target else max(0.0, min(cur / target, 1.0))
    cx = cy = size / 2.0
    return (
        '<svg viewBox="0 0 %d %d" class="ring" role="img">'
        '<circle class="ring-bg" cx="%.1f" cy="%.1f" r="%.1f"/>'
        '<circle class="ring-fg" cx="%.1f" cy="%.1f" r="%.1f" '
        'stroke-dasharray="%.2f" stroke-dashoffset="%.2f" '
        'transform="rotate(-90 %.1f %.1f)"/></svg>'
        % (size, size, cx, cy, r, cx, cy, r, circ, circ * (1 - frac), cx, cy)
    )


def build_hero(data, exam_date):
    if exam_date:
        days = (exam_date - date.today()).days
        sub = exam_date.strftime("%Y-%m-%d")
        if days > 0:
            big, unit = str(days), "天后考试"
        elif days == 0:
            big, unit = "今天", "就是考试日"
        else:
            big, unit = str(-days), "天前已考"
    else:
        big, unit = "—", "未设置考试日期"
        sub = "用 --exam-date 或在 study-plan.md 写 exam_date"

    target_avg = sum(TARGET_SCORES.values()) / len(TARGET_SCORES)
    cur = _latest_overall(data["mock"])
    ring = _progress_ring(cur, target_avg)
    cur_txt = _fmt(cur) if cur is not None else "—"
    return (
        '<section class="hero">'
        '<div class="hero-cd"><div class="cd-num">%s</div>'
        '<div class="cd-unit">%s</div><div class="cd-sub">%s</div></div>'
        '<div class="hero-ring">%s<div class="ring-cap">'
        '<div class="ring-cur">%s</div><div class="ring-tgt">目标 %s</div>'
        '</div></div></section>'
        % (_esc(big), _esc(unit), _esc(sub), ring, cur_txt, _fmt(target_avg))
    )


def build_goal_gap(mock):
    if not mock:
        return _no_data()
    rows = sorted(mock, key=_rec_date)
    scores = _get(rows[-1], "scores") or {}
    if not isinstance(scores, dict):
        return _no_data()
    names = {"L": "听力", "R": "阅读", "W": "写作", "S": "口语"}
    out = ['<div class="goals">']
    for k in ("L", "R", "W", "S"):
        cur = _as_float(scores.get(k)) or 0.0
        tgt = TARGET_SCORES[k]
        frac = max(0.0, min(cur / tgt, 1.0)) if tgt else 0.0
        met = cur >= tgt
        cls = "met" if met else "gap"
        tail = "已达标" if met else ("差 %s" % _fmt(tgt - cur))
        out.append(
            '<div class="goal"><div class="goal-top">'
            '<span class="goal-name">%s</span>'
            '<span class="goal-val %s">%s / %s · %s</span></div>'
            '<div class="goal-track"><div class="goal-fill %s" '
            'style="width:%.0f%%"></div></div></div>'
            % (names[k], cls, _fmt(cur), _fmt(tgt), tail, cls, frac * 100)
        )
    out.append("</div>")
    return "".join(out)


def build_heatmap(data, weeks=18):
    counts = _activity_counts(data)
    today = date.today()
    start = today - timedelta(days=weeks * 7 - 1)
    start -= timedelta(days=start.weekday())  # align to Monday
    cell, gap = 13, 3
    cols = (today - start).days // 7 + 1
    w = 24 + cols * (cell + gap)
    h = 22 + 7 * (cell + gap)
    maxc = max(counts.values()) if counts else 0

    def level(n):
        if n <= 0:
            return 0
        if maxc <= 1:
            return 4
        q = n / maxc
        return 1 if q <= 0.25 else 2 if q <= 0.5 else 3 if q <= 0.75 else 4

    parts = ['<svg viewBox="0 0 %d %d" class="heatmap" role="img">' % (w, h)]
    wd = ["一", "三", "五"]
    for idx, ri in enumerate((0, 2, 4)):
        parts.append(
            '<text x="0" y="%.1f" class="hm-wd">%s</text>'
            % (32 + ri * (cell + gap), wd[idx])
        )
    months = set()
    d = start
    while d <= today:
        ci = (d - start).days // 7
        x = 22 + ci * (cell + gap)
        y = 18 + d.weekday() * (cell + gap)
        n = counts.get(d.isoformat(), 0)
        parts.append(
            '<rect class="hm-cell hm-l%d" x="%.1f" y="%.1f" width="%d" '
            'height="%d" rx="3" data-tip="%s · %d 项"/>'
            % (level(n), x, y, cell, cell, d.isoformat(), n)
        )
        if d.day <= 7 and d.month not in months:
            months.add(d.month)
            parts.append('<text x="%.1f" y="11" class="hm-mon">%d月</text>' % (x, d.month))
        d += timedelta(days=1)
    parts.append("</svg>")
    parts.append(
        '<div class="hm-legend"><span>少</span>'
        + "".join('<i class="hm-l%d"></i>' % i for i in range(5))
        + "<span>多</span></div>"
    )
    return "".join(parts)


def build_activity_feed(data, limit=8):
    items = []
    for key, rec in _all_records(data):
        d = _rec_date(rec)
        if key == "writing":
            band = _as_float(_get(rec, "ai_scores", "opus", "overall"))
            desc = "写作 %s · %s 分" % (rec.get("task", ""), _fmt(band) if band is not None else "—")
        elif key == "listening":
            tot, cor = rec.get("total_questions"), rec.get("correct_count")
            cc = "%s/%s" % (cor, tot) if tot else "—"
            desc = "听力 %s %s · %s" % (rec.get("source_book", ""), rec.get("test_id", ""), cc)
        elif key == "reading":
            desc = "阅读 %s %s" % (rec.get("source_book", ""), rec.get("test_id", ""))
        else:
            band = _as_float(_get(rec, "scores", "overall"))
            desc = "模考 %s %s · %s 分" % (rec.get("source_book", ""), rec.get("test_id", ""), _fmt(band) if band is not None else "—")
        items.append((d, key, desc))
    if not items:
        return _no_data()
    items.sort(key=lambda x: x[0], reverse=True)
    rows = "".join(
        '<li class="feed-item"><span class="feed-dot feed-%s"></span>'
        '<span class="feed-date">%s</span><span class="feed-desc">%s</span></li>'
        % (key, _esc(d), _esc(desc))
        for d, key, desc in items[:limit]
    )
    return '<ul class="feed">%s</ul>' % rows


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------

STYLE = """
:root {
  --bg:#f5f7fb; --panel:#ffffff; --ink:#0f172a; --muted:#64748b;
  --border:#e6ebf2; --track:#eef2f7; --shadow:0 1px 3px rgba(15,23,42,.06);
  --accent:#0ea5e9; --accent2:#1e3a8a;
  --c-writing:#2563eb; --c-listen:#0891b2; --c-mock:#7c3aed;
  --c-streak:#f59e0b; --c-target:#16a34a; --c-warn:#e11d48;
  --good:#16a34a; --bad:#e11d48;
  --hm0:#eaeef4; --hm1:#cfe8fb; --hm2:#88c9f2; --hm3:#33a1e0; --hm4:#0b6cb0;
}
[data-theme="dark"] {
  --bg:#0b1220; --panel:#141d30; --ink:#e7eef9; --muted:#93a4c0;
  --border:#243149; --track:#1b2740; --shadow:0 1px 3px rgba(0,0,0,.4);
  --hm0:#1b2740; --hm1:#163a5a; --hm2:#1f6fa6; --hm3:#37a0dd; --hm4:#7fd0ff;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei","Hiragino Sans GB",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.45; transition:background .25s,color .25s; }
.wrap { max-width:1160px; margin:0 auto; padding:26px 20px 60px; }
.topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:22px; }
.topbar h1 { font-size:24px; margin:0 0 4px; letter-spacing:-0.01em; }
.topbar .ts { color:var(--muted); font-size:12.5px; margin:0; }
.ttoggle { border:1px solid var(--border); background:var(--panel); color:var(--ink);
  border-radius:999px; padding:7px 14px; font-size:13px; cursor:pointer;
  box-shadow:var(--shadow); white-space:nowrap; transition:transform .1s; }
.ttoggle:hover { transform:translateY(-1px); }
/* hero */
.hero { display:flex; align-items:center; justify-content:space-between; gap:24px;
  background:linear-gradient(120deg,var(--accent2),var(--accent));
  color:#fff; border-radius:18px; padding:26px 30px; margin-bottom:22px;
  box-shadow:0 10px 30px rgba(14,165,233,.22); flex-wrap:wrap; }
.hero-cd .cd-num { font-size:58px; font-weight:800; line-height:1; letter-spacing:-1px; }
.hero-cd .cd-unit { font-size:17px; font-weight:600; margin-top:6px; opacity:.95; }
.hero-cd .cd-sub { font-size:12.5px; margin-top:6px; opacity:.8; }
.hero-ring { position:relative; width:148px; height:148px; flex:0 0 auto; }
.ring { width:148px; height:148px; display:block; }
.ring-bg { fill:none; stroke:rgba(255,255,255,.25); stroke-width:11; }
.ring-fg { fill:none; stroke:#fff; stroke-width:11; stroke-linecap:round; transition:stroke-dashoffset .6s ease; }
.ring-cap { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }
.ring-cur { font-size:30px; font-weight:800; }
.ring-tgt { font-size:12px; opacity:.85; margin-top:2px; }
/* kpi cards */
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:22px; }
.card { background:var(--panel); border:1px solid var(--border); border-top:3px solid var(--accent);
  border-radius:13px; padding:15px 17px; box-shadow:var(--shadow); }
.card .cval { font-size:29px; font-weight:750; }
.card .clabel { color:var(--muted); font-size:12.5px; margin-top:2px; }
/* grid + panels */
.grid { display:grid; grid-template-columns:repeat(2,1fr); gap:18px; }
.panel { background:var(--panel); border:1px solid var(--border); border-radius:16px;
  padding:18px 20px; box-shadow:var(--shadow); min-width:0; }
.panel.wide { grid-column:1 / -1; }
.panel h2 { font-size:15px; margin:0 0 14px; }
.chart { width:100%; height:auto; display:block; overflow:visible; }
.radar { max-width:330px; margin:0 auto; }
.ytick,.xtick,.bval { fill:var(--muted); font-size:11px; }
.xtick { text-anchor:middle; } .ytick { text-anchor:end; }
.raxis { fill:var(--ink); font-size:13px; font-weight:600; text-anchor:middle; }
.blabel { fill:var(--ink); font-size:12px; text-anchor:end; }
.bartrack { fill:var(--track); }
.pt,.bar,.hm-cell { cursor:pointer; transition:opacity .12s; }
.pt:hover { r:6.5; } .bar:hover { opacity:.82; } .hm-cell:hover { stroke:var(--ink); stroke-width:1.4; }
.ylabel { color:var(--muted); font-size:12px; margin-bottom:4px; }
.legend { display:flex; flex-wrap:wrap; gap:16px; margin-top:8px; }
.lg { font-size:12px; color:var(--muted); display:inline-flex; align-items:center; }
.lg i { width:12px; height:12px; border-radius:3px; display:inline-block; margin-right:6px; }
.nodata { color:var(--muted); font-style:italic; font-size:14px; padding:24px 0; text-align:center; }
/* goal bars */
.goals { display:flex; flex-direction:column; gap:14px; }
.goal-top { display:flex; justify-content:space-between; font-size:13px; margin-bottom:6px; }
.goal-name { font-weight:600; }
.goal-val.met { color:var(--good); } .goal-val.gap { color:var(--muted); }
.goal-track { height:10px; background:var(--track); border-radius:99px; overflow:hidden; }
.goal-fill { height:100%; border-radius:99px; transition:width .6s ease; }
.goal-fill.met { background:var(--good); } .goal-fill.gap { background:var(--accent); }
/* heatmap */
.heatmap { width:100%; height:auto; display:block; overflow:visible; }
.hm-wd { fill:var(--muted); font-size:10px; } .hm-mon { fill:var(--muted); font-size:10px; }
.hm-l0{fill:var(--hm0);} .hm-l1{fill:var(--hm1);} .hm-l2{fill:var(--hm2);} .hm-l3{fill:var(--hm3);} .hm-l4{fill:var(--hm4);}
.hm-legend { display:flex; align-items:center; gap:4px; justify-content:flex-end; margin-top:8px; font-size:11px; color:var(--muted); }
.hm-legend i { width:12px; height:12px; border-radius:3px; display:inline-block; }
/* activity feed */
.feed { list-style:none; margin:0; padding:0; }
.feed-item { display:flex; align-items:center; gap:10px; padding:9px 0; border-bottom:1px solid var(--border); font-size:13.5px; }
.feed-item:last-child { border-bottom:none; }
.feed-dot { width:9px; height:9px; border-radius:99px; flex:0 0 auto; }
.feed-writing{background:var(--c-writing);} .feed-listening{background:var(--c-listen);}
.feed-reading{background:var(--c-target);} .feed-mock{background:var(--c-mock);}
.feed-date { color:var(--muted); font-variant-numeric:tabular-nums; flex:0 0 auto; }
.feed-desc { color:var(--ink); }
/* tooltip */
#tip { position:fixed; z-index:50; background:var(--ink); color:var(--bg);
  padding:6px 10px; border-radius:8px; font-size:12.5px; pointer-events:none;
  opacity:0; transition:opacity .1s; box-shadow:0 6px 20px rgba(0,0,0,.25); white-space:nowrap; }
footer { color:var(--muted); font-size:12px; margin-top:30px; text-align:center; }
@media (max-width:720px){ .grid{grid-template-columns:1fr;} .hero{justify-content:center; text-align:center;} }
"""

SCRIPT = """
(function(){
  var root=document.documentElement;
  var saved=localStorage.getItem('bw-theme');
  if(!saved){ saved=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'; }
  root.setAttribute('data-theme',saved);
  var btn=document.getElementById('themeBtn');
  function lbl(){ btn.textContent=(root.getAttribute('data-theme')==='dark')?'切换浅色':'切换深色'; }
  if(btn){ lbl(); btn.onclick=function(){
    var n=root.getAttribute('data-theme')==='dark'?'light':'dark';
    root.setAttribute('data-theme',n); localStorage.setItem('bw-theme',n); lbl();
  }; }
  var tip=document.getElementById('tip');
  document.addEventListener('mouseover',function(e){
    var t=e.target.closest('[data-tip]'); if(!t)return;
    tip.textContent=t.getAttribute('data-tip'); tip.style.opacity='1';
  });
  document.addEventListener('mousemove',function(e){
    if(tip.style.opacity!=='1')return;
    var x=e.clientX+14,y=e.clientY+14;
    if(x+tip.offsetWidth>innerWidth)x=e.clientX-tip.offsetWidth-14;
    if(y+tip.offsetHeight>innerHeight)y=e.clientY-tip.offsetHeight-14;
    tip.style.left=x+'px'; tip.style.top=y+'px';
  });
  document.addEventListener('mouseout',function(e){
    if(e.target.closest('[data-tip]')) tip.style.opacity='0';
  });
})();
"""


def render_html(data, root, exam_date=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hero = build_hero(data, exam_date)
    kpis = build_kpis(data)

    # (title, body, wide?)
    panels = [
        ("目标达成度（最近模考 vs 目标）", build_goal_gap(data["mock"]), False),
        ("四科雷达", build_radar(data["mock"]), False),
        ("学习热力图（近 18 周）", build_heatmap(data), True),
        ("写作分数趋势", build_writing_trend(data["writing"]), False),
        ("听力正确率趋势", build_listening_trend(data["listening"]), False),
        ("高频错误标签", build_error_bars(data["writing"], data["listening"]), False),
        ("最近动态", build_activity_feed(data), False),
    ]
    panel_html = "".join(
        '<section class="panel%s"><h2>%s</h2>%s</section>'
        % (" wide" if wide else "", _esc(title), body)
        for title, body, wide in panels
    )

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bandwise · 雅思备考进度面板</title>
<style>%s</style>
</head>
<body>
<div class="wrap">
<div class="topbar">
<div><h1>Bandwise · 雅思备考进度面板</h1>
<p class="ts">生成时间 %s · 数据目录：%s</p></div>
<button id="themeBtn" class="ttoggle" type="button">切换深色</button>
</div>
%s
%s
<div class="grid">%s</div>
<footer>由 Bandwise 面板生成器生成 · 完全离线 · 零依赖</footer>
</div>
<div id="tip"></div>
<script>%s</script>
</body>
</html>
""" % (STYLE, _esc(ts), _esc(root), hero, kpis, panel_html, SCRIPT)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def resolve_root(cli_root):
    if cli_root:
        return os.path.abspath(os.path.expanduser(cli_root))
    env = os.environ.get("IELTS_COACH_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/ielts-coach"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dashboard.py",
        description="生成 Bandwise 雅思备考进度面板 "
        "（dashboard.html，内嵌 SVG 图表）。",
    )
    parser.add_argument(
        "--root",
        help="数据根目录。未设置时回退到 $IELTS_COACH_HOME，"
        "再回退到 ~/ielts-coach。",
    )
    parser.add_argument(
        "--out",
        help="输出 HTML 路径（默认 <root>/dashboard.html）。",
    )
    parser.add_argument(
        "--exam-date",
        help="考试日期 YYYY-MM-DD（用于倒计时）。未给则读 study-plan.md 的 exam_date。",
    )
    args = parser.parse_args(argv)

    root = resolve_root(args.root)
    exam_date = read_exam_date(root, args.exam_date)
    out = args.out
    if out:
        out = os.path.abspath(os.path.expanduser(out))
    else:
        out = os.path.join(root, "dashboard.html")

    data = load_data(root)
    page = render_html(data, root, exam_date)

    out_dir = os.path.dirname(out) or "."
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(page)
    except OSError as exc:
        print("错误：无法写入 %s：%s" % (out, exc), file=sys.stderr)
        return 1

    total = sum(len(v) for v in data.values())
    print(
        "已生成 %s（写作=%d，听力=%d，阅读=%d，模考=%d；共 %d 个文件）"
        % (out, len(data["writing"]), len(data["listening"]),
           len(data["reading"]), len(data["mock"]), total)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
