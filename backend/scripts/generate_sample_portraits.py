"""Draw the illustrated sample mugshots used by the demo data.

Every face is procedurally generated from a seed: none is a photo of, or is
modelled on, a real person. Each image carries a "SYNTHETIC ILLUSTRATION"
placard so it can never be mistaken for a real record photo.

Usage (needs Playwright's Chromium to rasterise the SVGs):

    python -m scripts.generate_sample_portraits            # from backend/

Writes ``app/sample_photos/{male,female}-NN.jpg``. The JPEGs are committed,
so this only needs re-running to change the artwork.
"""
from __future__ import annotations

import io
import os
import random
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "app" / "sample_photos"
W, H = 600, 750
MALE_COUNT, FEMALE_COUNT = 30, 16

SKIN = [  # (base, shadow, highlight)
    ("#c68a62", "#9a6243", "#dcA582"), ("#b67a52", "#8a5638", "#cf9670"),
    ("#a56c46", "#7a4a2e", "#c08660"), ("#d49b72", "#a8714f", "#e8b994"),
    ("#8f5a38", "#663c23", "#ab7550"), ("#c08562", "#935d40", "#d9a483"),
    ("#9c6542", "#71452b", "#b88060"), ("#ddb08a", "#b4815e", "#f0caa6"),
]
HAIR = ["#141110", "#1d1714", "#2a1f19", "#3b2c22", "#121212", "#4a3a30"]
GREY = ["#6d6a66", "#8c8883", "#a9a49e"]
SHIRTS = ["#3d4b5c", "#55606b", "#6b5a45", "#2f3a33", "#7a7f86", "#5b4a52", "#8a7350", "#34404f"]
WALLS = [("#5f6d78", "#3c4650"), ("#6a7069", "#424840"), ("#6c6a74", "#45434d"), ("#5a6a72", "#36424a")]


def _c(rng: random.Random, lo: float, hi: float) -> float:
    return round(rng.uniform(lo, hi), 1)


def portrait_svg(seed: int, female: bool, label: str) -> str:
    rng = random.Random(seed)
    skin, shade, light = rng.choice(SKIN)
    age_grey = rng.random() < (0.12 if female else 0.25)
    hair = rng.choice(GREY) if age_grey else rng.choice(HAIR)
    shirt = rng.choice(SHIRTS)
    wall, wall_dark = rng.choice(WALLS)

    cx, cy = 300, 318
    fw = _c(rng, 96, 108) if female else _c(rng, 104, 120)
    jw = fw * (_c(rng, 0.78, 0.86) if female else _c(rng, 0.84, 0.96))
    chin = _c(rng, 30, 40) if female else _c(rng, 38, 54)
    top = cy - (_c(rng, 150, 160))
    bottom = cy + (_c(rng, 158, 168) if female else _c(rng, 162, 176))
    eye_y = cy - _c(rng, 2, 10)
    eye_dx = _c(rng, 42, 48)
    eye_w = _c(rng, 21, 25)
    eye_h = _c(rng, 7.5, 10) if female else _c(rng, 6.5, 9)
    brow_y = eye_y - _c(rng, 26, 34)
    brow_tilt = _c(rng, -6, 6)
    brow_thick = _c(rng, 5, 7) if female else _c(rng, 7, 11)
    nose_y = cy + _c(rng, 48, 60)
    nose_w = _c(rng, 22, 27) if female else _c(rng, 25, 32)
    mouth_y = cy + _c(rng, 92, 102)
    mouth_w = _c(rng, 24, 30) if female else _c(rng, 26, 34)
    mouth_curve = _c(rng, -4, 2)
    lip = "#8d4b3f" if female and rng.random() < 0.5 else shade
    iris = rng.choice(["#2b1a10", "#3a2414", "#1f140d", "#4a3220"])

    parts: list[str] = []
    add = parts.append

    # ── defs ────────────────────────────────────────────────────────────────
    add(f"""<defs>
  <radialGradient id="wall" cx="50%" cy="38%" r="75%">
    <stop offset="0" stop-color="{wall}"/><stop offset="1" stop-color="{wall_dark}"/>
  </radialGradient>
  <radialGradient id="face" cx="44%" cy="38%" r="70%">
    <stop offset="0" stop-color="{light}"/><stop offset=".55" stop-color="{skin}"/><stop offset="1" stop-color="{shade}"/>
  </radialGradient>
  <linearGradient id="neck" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{shade}"/><stop offset=".6" stop-color="{skin}"/>
  </linearGradient>
  <linearGradient id="shirt" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{shirt}"/><stop offset="1" stop-color="#1c2026"/>
  </linearGradient>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter>
  <filter id="softer" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="4"/></filter>
  <filter id="hairtex" x="-10%" y="-10%" width="120%" height="120%" color-interpolation-filters="sRGB">
    <feTurbulence type="fractalNoise" baseFrequency="0.9 0.06" numOctaves="2" seed="{seed}" result="n"/>
    <feColorMatrix in="n" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  1.1 0 0 0 -.62" result="streaks"/>
    <feComposite in="streaks" in2="SourceGraphic" operator="in" result="lit0"/>
    <feComponentTransfer in="lit0" result="lit"><feFuncA type="linear" slope=".22"/></feComponentTransfer>
    <feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="lit"/></feMerge>
  </filter>
  <filter id="stubble" x="-10%" y="-10%" width="120%" height="120%">
    <feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="1" seed="{seed + 7}" result="n"/>
    <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 3 -1.2" result="dots"/>
    <feComposite in="dots" in2="SourceGraphic" operator="in"/>
  </filter>
  <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="{seed + 3}"/>
    <feColorMatrix type="matrix" values="0 0 0 0 .5  0 0 0 0 .5  0 0 0 0 .5  0 0 0 .07 0"/></filter>
  <clipPath id="faceclip"><path d="{{FACE}}"/></clipPath>
</defs>""")

    face = (f"M{cx},{top} C{cx + fw * .78},{top} {cx + fw},{cy - 112} {cx + fw},{cy - 30} "
            f"C{cx + fw},{cy + 40} {cx + jw},{cy + 92} {cx + chin},{bottom - 22} "
            f"Q{cx},{bottom + 10} {cx - chin},{bottom - 22} "
            f"C{cx - jw},{cy + 92} {cx - fw},{cy + 40} {cx - fw},{cy - 30} "
            f"C{cx - fw},{cy - 112} {cx - fw * .78},{top} {cx},{top} Z")
    parts[0] = parts[0].replace("{FACE}", face)

    # ── background: mugshot wall with a height chart ───────────────────────
    add(f'<rect width="{W}" height="{H}" fill="url(#wall)"/>')
    for i, y in enumerate(range(60, H, 46)):
        add(f'<line x1="0" x2="{W}" y1="{y}" y2="{y}" stroke="#ffffff" stroke-opacity="{0.16 if i % 2 == 0 else 0.08}" stroke-width="{2 if i % 2 == 0 else 1}"/>')
        if i % 2 == 0:
            add(f'<text x="18" y="{y - 6}" font-family="Arial, sans-serif" font-size="15" fill="#ffffff" fill-opacity=".35">{200 - i * 5}</text>')
            add(f'<text x="{W - 18}" y="{y - 6}" text-anchor="end" font-family="Arial, sans-serif" font-size="15" fill="#ffffff" fill-opacity=".35">{200 - i * 5}</text>')
    add(f'<ellipse cx="{cx}" cy="{cy + 40}" rx="230" ry="300" fill="#000" opacity=".22" filter="url(#soft)"/>')

    # ── long hair behind the head ───────────────────────────────────────────
    style = rng.choice(["long", "long", "bun", "braid", "bob"]) if female else rng.choice(
        ["crop", "crop", "side", "slick", "buzz", "curly", "receding", "receding"] if not age_grey
        else ["receding", "receding", "crop", "bald", "side"])
    if style == "long":
        add(f'<path d="M{cx - fw - 18},{cy - 60} C{cx - fw - 40},{cy + 60} {cx - fw - 50},{cy + 200} {cx - fw - 30},{cy + 270} '
            f'L{cx + fw + 30},{cy + 270} C{cx + fw + 50},{cy + 200} {cx + fw + 40},{cy + 60} {cx + fw + 18},{cy - 60} '
            f'C{cx + fw},{top - 40} {cx - fw},{top - 40} {cx - fw - 18},{cy - 60} Z" fill="{hair}" filter="url(#hairtex)"/>')
    elif style == "bob":
        add(f'<path d="M{cx - fw - 22},{cy - 60} C{cx - fw - 34},{cy + 30} {cx - fw - 30},{cy + 110} {cx - fw + 4},{cy + 130} '
            f'L{cx + fw - 4},{cy + 130} C{cx + fw + 30},{cy + 110} {cx + fw + 34},{cy + 30} {cx + fw + 22},{cy - 60} '
            f'C{cx + fw},{top - 40} {cx - fw},{top - 40} {cx - fw - 22},{cy - 60} Z" fill="{hair}" filter="url(#hairtex)"/>')
    elif style == "bun":
        add(f'<ellipse cx="{cx}" cy="{top - 18}" rx="52" ry="40" fill="{hair}" filter="url(#hairtex)"/>')
    elif style == "braid":
        side = rng.choice([-1, 1])
        bx = cx + side * (fw - 10)
        for k in range(6):
            add(f'<ellipse cx="{bx + side * 12}" cy="{cy + 120 + k * 30}" rx="20" ry="20" fill="{hair}" filter="url(#hairtex)"/>')

    # ── shirt, neck, ears ───────────────────────────────────────────────────
    nw = _c(rng, 44, 52) if female else _c(rng, 54, 66)
    add(f'<path d="M{cx - nw - 10},{cy + 200} C{cx - 150},{cy + 230} {cx - 250},{cy + 250} {cx - 290},{cy + 330} L{cx - 300},{H} '
        f'L{cx + 300},{H} L{cx + 290},{cy + 330} C{cx + 250},{cy + 250} {cx + 150},{cy + 230} {cx + nw + 10},{cy + 200} Z" fill="url(#shirt)"/>')
    add(f'<rect x="{cx - nw}" y="{cy + 60}" width="{nw * 2}" height="{175}" rx="20" fill="url(#neck)"/>')
    add(f'<ellipse cx="{cx}" cy="{bottom + 6}" rx="{jw * .8}" ry="26" fill="{shade}" opacity=".35" filter="url(#softer)"/>')
    # collar
    add(f'<path d="M{cx - nw - 12},{cy + 196} L{cx},{cy + 300} L{cx - 18},{cy + 320} L{cx - nw - 40},{cy + 236} Z" fill="{shirt}" stroke="#000" stroke-opacity=".25"/>')
    add(f'<path d="M{cx + nw + 12},{cy + 196} L{cx},{cy + 300} L{cx + 18},{cy + 320} L{cx + nw + 40},{cy + 236} Z" fill="{shirt}" stroke="#000" stroke-opacity=".25"/>')
    for s in (-1, 1):
        add(f'<ellipse cx="{cx + s * (fw - 2)}" cy="{eye_y + 22}" rx="17" ry="33" fill="{skin}"/>')
        add(f'<ellipse cx="{cx + s * (fw + 2)}" cy="{eye_y + 22}" rx="8" ry="20" fill="{shade}" opacity=".7"/>')
        if female and rng.random() < 0.6:
            add(f'<circle cx="{cx + s * (fw + 1)}" cy="{eye_y + 58}" r="4.5" fill="#d8b45a"/>')

    # ── face and its shading ────────────────────────────────────────────────
    add(f'<path d="{face}" fill="url(#face)"/>')
    add('<g clip-path="url(#faceclip)">')
    light_side = rng.choice([-1, 1])
    add(f'<ellipse cx="{cx - light_side * fw}" cy="{cy + 20}" rx="{fw * .45}" ry="190" fill="{shade}" opacity=".55" filter="url(#soft)"/>')
    add(f'<ellipse cx="{cx}" cy="{bottom - 10}" rx="{chin + 30}" ry="22" fill="{shade}" opacity=".35" filter="url(#softer)"/>')
    for s in (-1, 1):  # eye sockets
        add(f'<ellipse cx="{cx + s * eye_dx}" cy="{eye_y - 4}" rx="{eye_w + 8}" ry="{eye_h + 9}" fill="{shade}" opacity=".45" filter="url(#softer)"/>')
        add(f'<ellipse cx="{cx + s * (eye_dx + 8)}" cy="{nose_y + 4}" rx="30" ry="18" fill="{light}" opacity=".18" filter="url(#soft)"/>')
    add(f'<ellipse cx="{cx + light_side * 6}" cy="{eye_y + 20}" rx="7" ry="34" fill="{light}" opacity=".35" filter="url(#softer)"/>')
    if age_grey or rng.random() < 0.3:  # forehead lines / nasolabial folds
        for k in range(2 + (1 if age_grey else 0)):
            y = brow_y - 22 - k * 11
            add(f'<path d="M{cx - 40},{y} Q{cx},{y - 5} {cx + 40},{y}" stroke="{shade}" stroke-width="1.6" fill="none" opacity=".5"/>')
        for s in (-1, 1):
            add(f'<path d="M{cx + s * (nose_w + 4)},{nose_y - 2} Q{cx + s * (nose_w + 16)},{mouth_y - 10} {cx + s * (mouth_w + 8)},{mouth_y + 8}" '
                f'stroke="{shade}" stroke-width="2" fill="none" opacity=".45"/>')
    add('</g>')

    # ── facial hair ─────────────────────────────────────────────────────────
    beard = None if female else rng.choice(["none", "stubble", "stubble", "moustache", "beard", "goatee", "beard"])
    beard_col = rng.choice(GREY) if age_grey else hair
    if beard in ("stubble", "beard"):
        op = ".85" if beard == "beard" else ".55"
        flt = "" if beard == "beard" else ' filter="url(#stubble)"'
        add(f'<g clip-path="url(#faceclip)"><path d="M{cx - fw},{eye_y + 30} C{cx - fw + 4},{cy + 110} {cx - chin - 30},{bottom + 10} {cx},{bottom + 14} '
            f'C{cx + chin + 30},{bottom + 10} {cx + fw - 4},{cy + 110} {cx + fw},{eye_y + 30} L{cx + fw - 22},{eye_y + 40} '
            f'C{cx + fw - 30},{nose_y + 20} {cx + mouth_w + 26},{nose_y + 6} {cx + nose_w},{nose_y + 8} L{cx - nose_w},{nose_y + 8} '
            f'C{cx - mouth_w - 26},{nose_y + 6} {cx - fw + 30},{nose_y + 20} {cx - fw + 22},{eye_y + 40} Z" '
            f'fill="{beard_col}" opacity="{op}"{flt}/></g>')
    if beard == "goatee":
        add(f'<path d="M{cx - mouth_w - 6},{mouth_y - 2} C{cx - mouth_w - 8},{bottom - 6} {cx + mouth_w + 8},{bottom - 6} {cx + mouth_w + 6},{mouth_y - 2} '
            f'L{cx + mouth_w - 4},{mouth_y + 10} L{cx - mouth_w + 4},{mouth_y + 10} Z" fill="{beard_col}" opacity=".9" filter="url(#hairtex)"/>')
    if beard in ("moustache", "beard", "goatee"):
        add(f'<path d="M{cx},{nose_y + 14} C{cx + 18},{nose_y + 8} {cx + mouth_w + 12},{nose_y + 18} {cx + mouth_w + 10},{mouth_y + 4} '
            f'C{cx + mouth_w - 4},{mouth_y - 10} {cx + 10},{mouth_y - 10} {cx},{mouth_y - 8} C{cx - 10},{mouth_y - 10} {cx - mouth_w + 4},{mouth_y - 10} '
            f'{cx - mouth_w - 10},{mouth_y + 4} C{cx - mouth_w - 12},{nose_y + 18} {cx - 18},{nose_y + 8} {cx},{nose_y + 14} Z" '
            f'fill="{beard_col}" filter="url(#hairtex)"/>')

    # ── eyes and brows ──────────────────────────────────────────────────────
    gaze = _c(rng, -2.5, 2.5)
    for s in (-1, 1):
        ex = cx + s * eye_dx
        add(f'<path d="M{ex - eye_w},{eye_y} Q{ex},{eye_y - eye_h * 1.5} {ex + eye_w},{eye_y} Q{ex},{eye_y + eye_h * 1.1} {ex - eye_w},{eye_y} Z" fill="#ece4da"/>')
        add(f'<clipPath id="eye{s + 1}{seed}"><path d="M{ex - eye_w},{eye_y} Q{ex},{eye_y - eye_h * 1.5} {ex + eye_w},{eye_y} Q{ex},{eye_y + eye_h * 1.1} {ex - eye_w},{eye_y} Z"/></clipPath>')
        add(f'<g clip-path="url(#eye{s + 1}{seed})"><circle cx="{ex + gaze}" cy="{eye_y - 1}" r="{eye_h + 1.5}" fill="{iris}"/>'
            f'<circle cx="{ex + gaze}" cy="{eye_y - 1}" r="{eye_h * .45}" fill="#050505"/>'
            f'<rect x="{ex - eye_w}" y="{eye_y - eye_h * 1.6}" width="{eye_w * 2}" height="{eye_h * .9}" fill="{shade}" opacity=".45"/></g>')
        add(f'<circle cx="{ex + gaze + 2.5}" cy="{eye_y - 3.5}" r="1.8" fill="#fff" opacity=".85"/>')
        add(f'<path d="M{ex - eye_w - 2},{eye_y + 1} Q{ex},{eye_y - eye_h * 1.6} {ex + eye_w + 2},{eye_y}" stroke="#1a100b" stroke-width="{3 if female else 2.4}" fill="none" stroke-linecap="round"/>')
        add(f'<path d="M{ex - eye_w + 4},{eye_y + 5} Q{ex},{eye_y + eye_h * 1.4} {ex + eye_w - 2},{eye_y + 4}" stroke="{shade}" stroke-width="1.4" fill="none" opacity=".8"/>')
        inner, outer = ex - s * (eye_w + 4), ex + s * (eye_w + 6)
        add(f'<path d="M{inner},{brow_y + brow_tilt * .5 + 3} Q{ex},{brow_y - 8} {outer},{brow_y - brow_tilt * .3 + 4}" '
            f'stroke="{beard_col if not female else hair}" stroke-width="{brow_thick}" fill="none" stroke-linecap="round" opacity=".92"/>')

    # ── nose and mouth ──────────────────────────────────────────────────────
    add(f'<path d="M{cx - 6},{eye_y + 8} C{cx - 10},{nose_y - 20} {cx - nose_w},{nose_y - 6} {cx - nose_w + 2},{nose_y + 4} '
        f'C{cx - nose_w + 6},{nose_y + 12} {cx - 10},{nose_y + 8} {cx},{nose_y + 12}" stroke="{shade}" stroke-width="2.6" fill="none" opacity=".75"/>')
    add(f'<path d="M{cx + nose_w - 2},{nose_y + 4} C{cx + nose_w - 6},{nose_y + 12} {cx + 10},{nose_y + 8} {cx},{nose_y + 12}" stroke="{shade}" stroke-width="2.6" fill="none" opacity=".75"/>')
    for s in (-1, 1):
        add(f'<ellipse cx="{cx + s * 9}" cy="{nose_y + 6}" rx="5.5" ry="3" fill="#2a1710" opacity=".55"/>')
    add(f'<path d="M{cx - mouth_w},{mouth_y} Q{cx - mouth_w / 2},{mouth_y - 9} {cx},{mouth_y - 5} Q{cx + mouth_w / 2},{mouth_y - 9} {cx + mouth_w},{mouth_y} '
        f'Q{cx},{mouth_y + 2 + mouth_curve} {cx - mouth_w},{mouth_y} Z" fill="{lip}" opacity=".85"/>')
    add(f'<path d="M{cx - mouth_w},{mouth_y} Q{cx},{mouth_y + 2 + mouth_curve} {cx + mouth_w},{mouth_y} Q{cx},{mouth_y + 16} {cx - mouth_w},{mouth_y} Z" fill="{lip}" opacity=".6"/>')
    add(f'<path d="M{cx - mouth_w - 2},{mouth_y + 1} Q{cx},{mouth_y + 3 + mouth_curve} {cx + mouth_w + 2},{mouth_y + 1}" stroke="#2a1510" stroke-width="2.2" fill="none" stroke-linecap="round"/>')
    if female and rng.random() < 0.4:
        add(f'<circle cx="{cx}" cy="{brow_y - 4}" r="4.5" fill="#9b1f2a"/>')
    if rng.random() < 0.2:
        mx, my = cx + rng.choice([-1, 1]) * _c(rng, 30, 60), cy + _c(rng, 40, 90)
        add(f'<circle cx="{mx}" cy="{my}" r="3" fill="#3a2418" opacity=".8"/>')
    if not female and rng.random() < 0.18:
        sx = cx + rng.choice([-1, 1]) * eye_dx
        add(f'<path d="M{sx - 6},{brow_y - 16} L{sx + 8},{eye_y + 26}" stroke="{light}" stroke-width="3" opacity=".7"/>')

    # ── hair on top ─────────────────────────────────────────────────────────
    hl = {"receding": cy - 92, "bald": cy - 140, "buzz": cy - 104}.get(style, cy - _c(rng, 100, 112))
    temple = fw - (14 if style in ("receding", "bald") else 6)
    if style == "bald":
        add(f'<path d="M{cx - fw - 2},{cy - 10} C{cx - fw - 4},{cy - 70} {cx - fw + 6},{cy - 90} {cx - fw + 14},{cy - 96} L{cx - fw + 20},{cy - 30} Z" fill="{hair}" filter="url(#hairtex)"/>')
        add(f'<path d="M{cx + fw + 2},{cy - 10} C{cx + fw + 4},{cy - 70} {cx + fw - 6},{cy - 90} {cx + fw - 14},{cy - 96} L{cx + fw - 20},{cy - 30} Z" fill="{hair}" filter="url(#hairtex)"/>')
        add(f'<ellipse cx="{cx - 30}" cy="{top + 34}" rx="40" ry="18" fill="#fff" opacity=".12" filter="url(#softer)"/>')
    else:
        lift = {"curly": 34, "slick": 22, "buzz": 6, "side": 26, "bun": 10, "braid": 12}.get(style, 18)
        cap = (f"M{cx - fw - 7},{cy - 4} C{cx - fw - 14},{top - lift - 10} {cx - 70},{top - lift - 16} {cx},{top - lift - 14} "
               f"C{cx + 70},{top - lift - 16} {cx + fw + 14},{top - lift - 10} {cx + fw + 7},{cy - 4} "
               f"L{cx + temple},{cy - 30} C{cx + temple - 6},{hl - 6} {cx + 50},{hl - 4} {cx},{hl} "
               f"C{cx - 50},{hl - 4} {cx - temple + 6},{hl - 6} {cx - temple},{cy - 30} Z")
        if style == "receding":
            cap = (f"M{cx - fw - 7},{cy - 4} C{cx - fw - 14},{top - 30} {cx - 70},{top - 34} {cx},{top - 32} "
                   f"C{cx + 70},{top - 34} {cx + fw + 14},{top - 30} {cx + fw + 7},{cy - 4} "
                   f"L{cx + temple},{cy - 30} C{cx + temple - 4},{cy - 100} {cx + 50},{cy - 92} {cx + 34},{cy - 118} "
                   f"C{cx + 20},{cy - 128} {cx - 20},{cy - 128} {cx - 34},{cy - 118} "
                   f"C{cx - 50},{cy - 92} {cx - temple + 4},{cy - 100} {cx - temple},{cy - 30} Z")
        if style in ("long", "bob", "bun", "braid"):  # centre parting
            cap = (f"M{cx - fw - 10},{cy + 10} C{cx - fw - 16},{top - 30} {cx - 70},{top - 26} {cx},{top - 16} "
                   f"C{cx + 70},{top - 26} {cx + fw + 16},{top - 30} {cx + fw + 10},{cy + 10} "
                   f"L{cx + fw - 6},{cy - 10} C{cx + fw - 14},{hl} {cx + 40},{hl - 4} {cx + 2},{top + 6} "
                   f"L{cx - 2},{top + 6} C{cx - 40},{hl - 4} {cx - fw + 14},{hl} {cx - fw + 6},{cy - 10} Z")
        add(f'<path d="{cap}" fill="{hair}" filter="url(#hairtex)"/>')
        if style == "side":
            add(f'<path d="M{cx - 36},{top - lift - 10} Q{cx - 28},{top + 4} {cx - 40},{hl - 4}" stroke="#000" stroke-opacity=".4" stroke-width="3" fill="none"/>')
        if style == "curly":
            for k in range(22):
                a = rng.uniform(0, 1)
                px = cx - fw - 4 + a * (2 * fw + 8)
                py = top - lift + rng.uniform(-14, 24) + abs(px - cx) * 0.35
                add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rng.uniform(10, 16):.1f}" fill="{hair}" filter="url(#hairtex)"/>')
        add(f'<path d="M{cx - 60},{top - lift + 4} Q{cx},{top - lift - 10} {cx + 60},{top - lift + 4}" stroke="#fff" stroke-opacity=".12" stroke-width="10" fill="none" filter="url(#softer)"/>')

    if rng.random() < (0.15 if female else 0.2):  # glasses
        for s in (-1, 1):
            ex = cx + s * eye_dx
            add(f'<rect x="{ex - 32}" y="{eye_y - 20}" width="64" height="40" rx="12" fill="#fff" fill-opacity=".06" stroke="#1b1b1b" stroke-width="3.5"/>')
        add(f'<path d="M{cx - eye_dx + 32},{eye_y - 6} Q{cx},{eye_y - 14} {cx + eye_dx - 32},{eye_y - 6}" stroke="#1b1b1b" stroke-width="3" fill="none"/>')

    # ── placard: makes the synthetic origin explicit ────────────────────────
    py = H - 112
    add(f'<rect x="{cx - 170}" y="{py}" width="340" height="86" rx="6" fill="#111418" stroke="#c9a34a" stroke-width="2"/>')
    add(f'<text x="{cx}" y="{py + 32}" text-anchor="middle" font-family="Courier New, monospace" font-weight="700" font-size="24" fill="#f1e7cf">{label}</text>')
    add(f'<text x="{cx}" y="{py + 62}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" letter-spacing="2" fill="#c9a34a">SYNTHETIC ILLUSTRATION</text>')
    add(f'<rect width="{W}" height="{H}" filter="url(#grain)"/>')

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{"".join(parts)}</svg>'


def specs():
    for i in range(MALE_COUNT):
        yield f"male-{i + 1:02d}", 1000 + i * 37, False
    for i in range(FEMALE_COUNT):
        yield f"female-{i + 1:02d}", 5000 + i * 41, True


def main() -> int:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keep_svg = "--svg" in sys.argv
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CRMS_CHROMIUM") or None)
        page = browser.new_page(viewport={"width": W, "height": H})
        for name, seed, female in specs():
            svg = portrait_svg(seed, female, f"CRMS · SAMPLE {name[0].upper()}{name[-2:]}")
            if keep_svg:
                (OUT_DIR / f"{name}.svg").write_text(svg, encoding="utf-8")
            page.set_content(f'<body style="margin:0">{svg}</body>')
            png = page.screenshot(clip={"x": 0, "y": 0, "width": W, "height": H})
            Image.open(io.BytesIO(png)).convert("RGB").save(OUT_DIR / f"{name}.jpg", quality=84, optimize=True)
            print("wrote", name)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
