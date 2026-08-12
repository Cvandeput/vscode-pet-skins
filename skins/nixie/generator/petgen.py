#!/usr/bin/env python3
"""
Générateur de sprites pour le "pet" natif de VS Code (>= 1.131).

Le dessin n'est PAS codé ici : il est lu depuis un fichier de définition
skin.json (grille de base, palette, repères). Ce script en dérive les 12
animations et écrit les 48 PNG attendus par VS Code.

    python petgen.py                     # utilise ../skin.json
    python petgen.py autre/skin.json     # utilise un autre skin

Le skin.json se produit à la main ou avec l'éditeur : tools/editor.html

Dépendance : Pillow.
"""

import json
import os
import sys
from PIL import Image

# ----------------------------------------------------------------- chargement
HERE = os.path.dirname(os.path.abspath(__file__))
SKIN_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'skin.json')

with open(SKIN_PATH, encoding='utf-8') as fh:
    SKIN = json.load(fh)

SIZE = SKIN.get('grid', 24)
SCALE = SKIN.get('scale', 4)
FRAME = SIZE * SCALE

BASE = [list(row.ljust(SIZE, '.')[:SIZE]) for row in SKIN['base']]
while len(BASE) < SIZE:
    BASE.append(['.'] * SIZE)

R = SKIN['roles']
AN = SKIN['anchors']

EYE_L = tuple(AN['eyes']['left'])
EYE_R = tuple(AN['eyes']['right'])
EYE_X = (EYE_L[0], EYE_R[0])
EYE_Y = EYE_L[1]
EYE_W, EYE_H = AN['eyes'].get('socket', [4, 4])
SCREEN_X = (AN['screen'][0], AN['screen'][2])
SCREEN_Y = (AN['screen'][1], AN['screen'][3])
BODY = AN['body']
FEET = AN['feet']


def _rgba(hexstr):
    h = hexstr.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


PALETTE = {'.': None}
PALETTE.update({k: _rgba(v) for k, v in SKIN['palette'].items()})

# alias de rôles, pour que le code reste lisible
SCREEN, FLICK = R['screen'], R['screenFlicker']
SOCKET, RIM = R['socket'], R['socketRim']
CORE, LIGHT, DARK = R['eyeCore'], R['eyeLight'], R['eyeShadow']
HALO, HALO2 = R['halo'], R['haloStrong']
SPARK, SHADOW = R['spark'], R['shadow']


# ----------------------------------------------------------------- primitives
def blank():
    return [['.'] * SIZE for _ in range(SIZE)]


def put(g, x, y, c):
    if 0 <= x < SIZE and 0 <= y < SIZE:
        g[y][x] = c


def hline(g, x0, x1, y, c):
    for x in range(x0, x1 + 1):
        put(g, x, y, c)


def rect(g, x0, y0, x1, y1, c):
    for y in range(y0, y1 + 1):
        hline(g, x0, x1, y, c)


def render(g):
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    for y in range(SIZE):
        for x in range(SIZE):
            col = PALETTE.get(g[y][x])
            if col:
                px[x, y] = col
    return img.resize((FRAME, FRAME), Image.NEAREST)


def _in_foot(x, y):
    for i, (x0, y0, x1, y1) in enumerate(FEET):
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None


# ----------------------------------------------------------------- personnage
def draw_base(g, oy=0, screen_off=False, flicker=False, feet=(0, 0)):
    """Pose la grille de base, décalée de oy, pieds éventuellement levés."""
    for y in range(SIZE):
        for x in range(SIZE):
            c = BASE[y][x]
            if c == '.':
                continue
            fi = _in_foot(x, y)
            dy = oy + (feet[fi] if fi is not None and fi < len(feet) else 0)
            put(g, x, y + dy, c)

    if flicker:
        for y in range(SCREEN_Y[0], SCREEN_Y[1] + 1):
            for x in range(SCREEN_X[0], SCREEN_X[1] + 1):
                if 0 <= y + oy < SIZE and g[y + oy][x] == SCREEN:
                    g[y + oy][x] = FLICK


def socket(g, oy, ex, ey=None, squash=False):
    ey = EYE_Y if ey is None else ey
    if squash:
        hline(g, ex, ex + EYE_W - 1, ey + EYE_H - 1 + oy, SOCKET)
        return
    hline(g, ex, ex + EYE_W - 1, ey + oy, RIM)
    for y in range(ey + 1, ey + EYE_H):
        hline(g, ex, ex + EYE_W - 1, y + oy, SOCKET)


def halo(g, oy, ex, ey=None):
    ey = EYE_Y if ey is None else ey
    for x in range(ex - 1, ex + EYE_W + 1):
        put(g, x, ey - 1 + oy, HALO)
        put(g, x, ey + EYE_H + oy, HALO)
    for y in range(ey, ey + EYE_H):
        put(g, ex - 1, y + oy, HALO)
        put(g, ex + EYE_W, y + oy, HALO)


def pupil(g, oy, ex, ey=None, dx=0, dy=0, dim=False, squash=False):
    ey = EYE_Y if ey is None else ey
    core, hi, lo = (DARK, DARK, DARK) if dim else (CORE, LIGHT, DARK)
    x, y = ex + 1 + dx, ey + 1 + dy + oy
    if squash:
        put(g, x, ey + EYE_H - 1 + oy, core)
        put(g, x + 1, ey + EYE_H - 1 + oy, core)
        return
    put(g, x, y, hi);       put(g, x + 1, y, core)
    put(g, x, y + 1, core); put(g, x + 1, y + 1, lo)


def eyes(g, oy, mode='open', dx=0, dy=0, tracking=False, squash=False):
    """mode : open | closed | dim | hearts | narrow | none"""
    for ex in EYE_X:
        if mode == 'none':
            socket(g, oy, ex, squash=squash)
            continue
        if mode == 'closed':
            socket(g, oy, ex)
            hline(g, ex + 1, ex + EYE_W - 2, EYE_Y + 2 + oy, DARK)
            continue
        if mode == 'hearts':
            socket(g, oy, ex)
            put(g, ex, EYE_Y + 1 + oy, CORE); put(g, ex + 2, EYE_Y + 1 + oy, CORE)
            hline(g, ex, ex + EYE_W - 1, EYE_Y + 2 + oy, CORE)
            put(g, ex + 1, EYE_Y + 3 + oy, CORE); put(g, ex + 2, EYE_Y + 3 + oy, CORE)
            put(g, ex, EYE_Y + 1 + oy, LIGHT)
            halo(g, oy, ex)
            continue
        if mode == 'narrow':
            socket(g, oy, ex)
            hline(g, ex + 1, ex + EYE_W - 2, EYE_Y + 2 + oy, CORE)
            halo(g, oy, ex)
            continue
        socket(g, oy, ex, squash=squash)
        pupil(g, oy, ex, dx=dx, dy=dy, dim=(mode == 'dim'), squash=squash)
        halo(g, oy, ex)


# ----------------------------------------------------------------- animations
def anim_idle(tracking):
    """50 frames. Palier à f20, clignement f23-f27, scintillement f8 et f44."""
    frames = []
    for i in range(50):
        g = blank()
        oy = 0 if i < 20 else 1
        draw_base(g, oy, flicker=(i in (8, 44)))
        eyes(g, oy, mode=('none' if tracking else 'open'), squash=(23 <= i <= 27))
        frames.append(g)
    return frames


def anim_rendering():
    """50 frames, tracking. Barre de progression + ligne de balayage."""
    bar_y = SCREEN_Y[1] - 1
    span = SCREEN_Y[1] - SCREEN_Y[0] + 1
    frames = []
    for i in range(50):
        g = blank()
        draw_base(g, 0)
        scan = SCREEN_Y[0] + (i % span)
        if not (EYE_Y <= scan < EYE_Y + EYE_H):
            hline(g, SCREEN_X[0], SCREEN_X[1], scan, FLICK)
        eyes(g, 0, mode='none')
        hline(g, SCREEN_X[0], SCREEN_X[1], bar_y, FLICK)
        filled = SCREEN_X[0] + round((SCREEN_X[1] - SCREEN_X[0]) * i / 49)
        hline(g, SCREEN_X[0], filled, bar_y, HALO2)
        put(g, filled, bar_y, CORE)
        frames.append(g)
    return frames


def anim_clapping():
    """13 frames, tracking. Sauts + étincelles."""
    offsets = [0, -1, -2, -2, -1, 0, -1, -2, -2, -1, 0, -1, 0]
    frames = []
    for oy in offsets:
        g = blank()
        draw_base(g, oy)
        eyes(g, oy, mode='none')
        if oy <= -2:
            put(g, BODY[0] - 1, SCREEN_Y[0] + oy, SPARK)
            put(g, BODY[2] + 1, SCREEN_Y[0] + oy, SPARK)
            put(g, BODY[0] - 2, SCREEN_Y[0] + 3 + oy, SPARK)
            put(g, BODY[2] + 2, SCREEN_Y[0] + 3 + oy, SPARK)
        frames.append(g)
    return frames


def anim_cool():
    """9 frames. Lunettes qui descendent, puis éclat."""
    top0 = EYE_Y - 3
    tops = [top0, top0 + 1, top0 + 2, EYE_Y, EYE_Y, EYE_Y, EYE_Y, EYE_Y, EYE_Y]
    frames = []
    for i, top in enumerate(tops):
        g = blank()
        draw_base(g, 0)
        eyes(g, 0, mode='open')
        rect(g, SCREEN_X[0], top, SCREEN_X[1], top + 2, SOCKET)
        hline(g, SCREEN_X[0], SCREEN_X[1], top - 1, SHADOW)
        for ex in EYE_X:
            put(g, ex + 1, top + 1, DARK); put(g, ex + 2, top + 1, DARK)
        if i >= 6:
            gx = SCREEN_X[0] + (i - 6) * 4
            put(g, gx, top + 2, SPARK); put(g, gx + 1, top + 1, SPARK)
        frames.append(g)
    return frames


def anim_sleep():
    """8 frames. Dalle éteinte, yeux fermés, respiration lente."""
    frames = []
    for oy in [1, 1, 1, 2, 2, 2, 1, 1]:
        g = blank()
        draw_base(g, oy, screen_off=True)
        eyes(g, oy, mode='closed')
        frames.append(g)
    return frames


def anim_waking():
    """8 frames. Amorçage CRT puis allumage progressif."""
    mid = (SCREEN_Y[0] + SCREEN_Y[1]) // 2
    cx = (SCREEN_X[0] + SCREEN_X[1]) // 2
    frames = []
    for i in range(8):
        g = blank()
        draw_base(g, 0, screen_off=(i == 0))
        if i == 1:
            hline(g, cx - 3, cx + 3, mid, SPARK)
        elif i == 2:
            hline(g, SCREEN_X[0], SCREEN_X[1], mid, SPARK)
        elif i == 3:
            rect(g, SCREEN_X[0], SCREEN_Y[0], SCREEN_X[1], SCREEN_Y[1], SPARK)
        elif i == 4:
            eyes(g, 0, mode='none')
        elif i == 5:
            eyes(g, 0, mode='dim')
        else:
            eyes(g, 0, mode='open')
        frames.append(g)
    return frames


def anim_typing():
    """8 frames. Regard qui balaie + curseur clignotant."""
    frames = []
    for i, dx in enumerate([-1, 0, 1, 1, 0, -1, 0, 0]):
        g = blank()
        draw_base(g, 0)
        eyes(g, 0, mode='open', dx=dx)
        if i % 2 == 0:
            put(g, SCREEN_X[0] + 1, SCREEN_Y[1] - 1, CORE)
            put(g, SCREEN_X[0] + 2, SCREEN_Y[1] - 1, CORE)
        frames.append(g)
    return frames


def anim_love():
    """6 frames. Coeurs + petit coeur qui s'élève. Dernière frame stable."""
    cx = (SCREEN_X[0] + SCREEN_X[1]) // 2
    frames = []
    for i in range(6):
        g = blank()
        draw_base(g, 0)
        eyes(g, 0, mode='hearts')
        if i >= 3:
            hy = max(0, BODY[1] - 1 - (i - 3) // 2)
            put(g, cx - 1, hy, CORE); put(g, cx + 1, hy, CORE)
            put(g, cx, hy + 1, CORE)
        frames.append(g)
    return frames


def anim_yapping():
    """5 frames. Bouche qui s'ouvre, yeux plissés. Frame 2 = pose longue."""
    cx = (SCREEN_X[0] + SCREEN_X[1]) // 2
    my = SCREEN_Y[1] - 1
    frames = []
    for w in [1, 3, 5, 3, 2]:
        g = blank()
        draw_base(g, 0)
        eyes(g, 0, mode='narrow')
        hline(g, cx - w // 2, cx + 1 + w // 2, my, CORE)
        if w >= 3:
            hline(g, cx - w // 2 + 1, cx + w // 2, my + 1, DARK)
        frames.append(g)
    return frames


def anim_search():
    """4 frames. Le pet émerge par le bas et regarde sur le côté."""
    frames = []
    for oy in [18, 12, 6, 0]:
        g = blank()
        draw_base(g, oy)
        eyes(g, oy, mode='open', dx=1)
        frames.append(g)
    return frames


def anim_speech():
    """6 frames. LA BULLE DE DIALOGUE, pas le personnage."""
    fill, shine = R['bubbleFill'], R['bubbleShine']
    boxes = [(10, 10, 13, 12), (8, 8, 15, 13), (6, 6, 17, 15),
             (6, 6, 17, 15), (6, 6, 17, 15), (6, 6, 17, 15)]
    frames = []
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        g = blank()
        rect(g, x0, y0, x1, y1, fill)
        hline(g, x0, x1, y0, SOCKET); hline(g, x0, x1, y1, SOCKET)
        for y in range(y0, y1 + 1):
            put(g, x0, y, SOCKET); put(g, x1, y, SOCKET)
        hline(g, x0 + 1, x1 - 1, y0 + 1, shine)
        put(g, x0 + 2, y1 + 1, SOCKET); put(g, x0 + 3, y1 + 1, SOCKET)
        put(g, x0 + 2, y1 + 2, SOCKET)
        if i >= 2:
            cy = (y0 + y1) // 2
            for k, dx in enumerate((9, 11, 13)):
                lit = (i - 2) % 3 == k or i == 5
                put(g, dx, cy, CORE if lit else SHADOW)
        frames.append(g)
    return frames


# ----------------------------------------------------------------- assemblage
def sheet(frames):
    img = Image.new('RGBA', (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, g in enumerate(frames):
        img.paste(render(g), (i * FRAME, 0))
    return img


def build_all():
    return {
        'idle-{v}-96':               (anim_idle(False),  50),
        'idle-{v}-tracking-96':      (anim_idle(True),   50),
        'rendering-{v}-tracking-96': (anim_rendering(),  50),
        'clapping-{v}-tracking-96':  (anim_clapping(),   13),
        'cool-{v}-96':               (anim_cool(),        9),
        'sleep-{v}-96':              (anim_sleep(),       8),
        'waking-{v}-96':             (anim_waking(),      8),
        'typing-{v}-96':             (anim_typing(),      8),
        'love-{v}-96':               (anim_love(),        6),
        'speech-{v}-96':             (anim_speech(),      6),
        'yapping-{v}-96':            (anim_yapping(),     5),
        'search-{v}-96':             (anim_search(),      4),
    }


def main(outdir='out'):
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(outdir, 'preview'), exist_ok=True)

    written, errors = 0, []
    for base, (frames, expected) in build_all().items():
        if len(frames) != expected:
            errors.append(f'{base}: {len(frames)} frames au lieu de {expected}')
            continue
        sh = sheet(frames)
        single = render(frames[0])
        for variant in ('stable', 'insiders'):
            name = base.format(v=variant)
            sh.save(os.path.join(outdir, f'buddy-{name}.spritesheet.png'))
            single.save(os.path.join(outdir, f'buddy-{name}.png'))
            written += 2
        for i, g in enumerate(frames):
            render(g).save(os.path.join(
                outdir, 'preview', f'{base.format(v="x")}_{i:02d}.png'))

    pal = Image.new('RGBA', (len(PALETTE) * 16, 16), (0, 0, 0, 0))
    for i, (_, c) in enumerate(PALETTE.items()):
        if c:
            pal.paste(Image.new('RGBA', (16, 16), c), (i * 16, 0))
    pal.save(os.path.join(outdir, 'palette.png'))

    print(f"skin '{SKIN.get('name', '?')}' : {written} fichiers ecrits dans {outdir}/")
    for e in errors:
        print('ERREUR:', e)


if __name__ == '__main__':
    main()
