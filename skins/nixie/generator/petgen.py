#!/usr/bin/env python3
"""
Générateur de sprites pour le "pet" natif de VS Code (>= 1.131).
Mascotte : écran d'ordinateur sur pieds, châssis gris foncé, yeux rouge-orangé.

Grille logique 24x24, agrandie x4 (nearest) -> frames 96x96.
Sortie : ./out avec les 48 fichiers aux noms exacts attendus par VS Code.

Dépendance : Pillow.
"""

import os
from PIL import Image

# ----------------------------------------------------------------- palette
def blend(bg, fg, alpha):
    """Compose fg sur bg avec alpha 0-255, renvoie une couleur opaque."""
    a = alpha / 255.0
    return tuple(round(bg[i] + (fg[i] - bg[i]) * a) for i in range(3)) + (255,)

_SCREEN = (0x12, 0x14, 0x16, 255)
_GLOW   = (0xFF, 0x6A, 0x2B, 255)

PALETTE = {
    '.': None,                          # transparent
    'A': (0x45, 0x4B, 0x52, 255),       # carcasse_clair
    'B': (0x2E, 0x33, 0x38, 255),       # carcasse_base
    'C': (0x1B, 0x1F, 0x23, 255),       # carcasse_ombre
    'D': (0x0E, 0x11, 0x14, 255),       # contour
    'E': _SCREEN,                       # dalle_fond
    'F': (0x1C, 0x20, 0x24, 255),       # dalle_reflet
    'G': _GLOW,                         # oeil_coeur
    'H': (0xFF, 0xA5, 0x5C, 255),       # oeil_clair
    'I': (0xC4, 0x38, 0x0C, 255),       # oeil_ombre
    'J': (0xE8, 0xED, 0xF2, 255),       # blanc_specular
    'K': blend(_SCREEN, _GLOW, 40),     # halo sur la dalle
    'L': blend(_SCREEN, _GLOW, 90),     # halo intense (barre de progression)
}

SIZE = 24          # grille logique
SCALE = 4          # -> 96 px
FRAME = SIZE * SCALE

# géométrie du visage — imposée, cohérente avec les surcharges CSS
EYE_X = (6, 14)    # coin gauche des orbites 4x4
EYE_Y = 10
SCREEN_X = (5, 18)  # intérieur de la dalle
SCREEN_Y = (8, 16)

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
            col = PALETTE[g[y][x]]
            if col:
                px[x, y] = col
    return img.resize((FRAME, FRAME), Image.NEAREST)


# ----------------------------------------------------------------- personnage
def draw_base(g, oy=0, screen_off=False, flicker=False):
    """Châssis + pieds + dalle vide. oy = décalage vertical en cellules."""
    fill = 'E' if not screen_off else 'E'
    if flicker:
        fill = 'F'

    hline(g, 2, 21, 2 + oy, 'D')                                    # bord haut

    put(g, 2, 3 + oy, 'D'); put(g, 3, 3 + oy, 'J')                  # speculaire
    hline(g, 4, 20, 3 + oy, 'A'); put(g, 21, 3 + oy, 'D')

    for y in (4, 5, 6):                                             # front
        put(g, 2, y + oy, 'D'); put(g, 3, y + oy, 'A')
        hline(g, 4, 19, y + oy, 'B')
        put(g, 20, y + oy, 'C'); put(g, 21, y + oy, 'D')

    for y in (7, 17):                                               # cadre dalle
        put(g, 2, y + oy, 'D'); put(g, 3, y + oy, 'B')
        hline(g, 4, 19, y + oy, 'D')
        put(g, 20, y + oy, 'C'); put(g, 21, y + oy, 'D')

    for y in range(SCREEN_Y[0], SCREEN_Y[1] + 1):                   # intérieur
        put(g, 2, y + oy, 'D'); put(g, 3, y + oy, 'B'); put(g, 4, y + oy, 'D')
        hline(g, SCREEN_X[0], SCREEN_X[1], y + oy, fill)
        put(g, 19, y + oy, 'D'); put(g, 20, y + oy, 'C'); put(g, 21, y + oy, 'D')

    put(g, 2, 18 + oy, 'D'); hline(g, 3, 20, 18 + oy, 'C'); put(g, 21, 18 + oy, 'D')
    hline(g, 2, 21, 19 + oy, 'D')                                   # bord bas

    for fx in (5, 15):                                              # pieds
        hline(g, fx, fx + 3, 20 + oy, 'D')
        put(g, fx, 21 + oy, 'D'); put(g, fx + 1, 21 + oy, 'C')
        put(g, fx + 2, 21 + oy, 'C'); put(g, fx + 3, 21 + oy, 'D')
        hline(g, fx, fx + 3, 22 + oy, 'D')


def socket(g, oy, ex, ey=EYE_Y, squash=False):
    """Orbite creusée 4x4 : liseré F en haut, intérieur D."""
    if squash:
        hline(g, ex, ex + 3, ey + 3 + oy, 'D')
        return
    hline(g, ex, ex + 3, ey + oy, 'F')
    for y in range(ey + 1, ey + 4):
        hline(g, ex, ex + 3, y + oy, 'D')


def halo(g, oy, ex, ey=EYE_Y):
    """Anneau de halo d'exactement 1 cellule autour de l'orbite."""
    for x in range(ex - 1, ex + 5):
        put(g, x, ey - 1 + oy, 'K'); put(g, x, ey + 4 + oy, 'K')
    for y in range(ey, ey + 4):
        put(g, ex - 1, y + oy, 'K'); put(g, ex + 4, y + oy, 'K')


def pupil(g, oy, ex, ey=EYE_Y, dx=0, dy=0, dim=False, squash=False):
    """Pupille 2x2 : H haut-gauche, I bas-droite, G sur l'autre diagonale."""
    core, hi, lo = ('I', 'I', 'I') if dim else ('G', 'H', 'I')
    x, y = ex + 1 + dx, ey + 1 + dy + oy
    if squash:
        put(g, x, ey + 3 + oy, core); put(g, x + 1, ey + 3 + oy, core)
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
            hline(g, ex + 1, ex + 2, EYE_Y + 2 + oy, 'I')
            continue
        if mode == 'hearts':
            socket(g, oy, ex)
            put(g, ex,     EYE_Y + 1 + oy, 'G'); put(g, ex + 2, EYE_Y + 1 + oy, 'G')
            hline(g, ex, ex + 3, EYE_Y + 2 + oy, 'G')
            put(g, ex + 1, EYE_Y + 3 + oy, 'G'); put(g, ex + 2, EYE_Y + 3 + oy, 'G')
            put(g, ex,     EYE_Y + 1 + oy, 'H')
            halo(g, oy, ex)
            continue
        if mode == 'narrow':
            socket(g, oy, ex)
            hline(g, ex + 1, ex + 2, EYE_Y + 2 + oy, 'G')
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
        blink = 23 <= i <= 27
        draw_base(g, oy, flicker=(i in (8, 44)))
        eyes(g, oy, mode=('none' if tracking else 'open'), squash=blink)
        frames.append(g)
    return frames


def anim_rendering():
    """50 frames, tracking. Barre de progression + ligne de balayage."""
    frames = []
    for i in range(50):
        g = blank()
        draw_base(g, 0)
        scan = SCREEN_Y[0] + (i % 9)
        if scan not in range(EYE_Y, EYE_Y + 4):
            hline(g, SCREEN_X[0], SCREEN_X[1], scan, 'F')
        eyes(g, 0, mode='none')
        hline(g, SCREEN_X[0], SCREEN_X[1], 15, 'F')                 # rail
        filled = SCREEN_X[0] + round((SCREEN_X[1] - SCREEN_X[0]) * i / 49)
        hline(g, SCREEN_X[0], filled, 15, 'L')
        if filled >= SCREEN_X[0]:
            put(g, filled, 15, 'G')
        frames.append(g)
    return frames


def anim_clapping():
    """13 frames, tracking. Sauts + étincelles."""
    offsets = [0, -1, -2, -2, -1, 0, -1, -2, -2, -1, 0, -1, 0]
    frames = []
    for i, oy in enumerate(offsets):
        g = blank()
        draw_base(g, oy)
        eyes(g, oy, mode='none')
        if oy <= -2:
            put(g, 1, 8 + oy, 'J'); put(g, 22, 8 + oy, 'J')
            put(g, 0, 11 + oy, 'J'); put(g, 23, 11 + oy, 'J')
        frames.append(g)
    return frames


def anim_cool():
    """9 frames. Lunettes qui descendent, puis éclat."""
    tops = [7, 8, 9, 10, 10, 10, 10, 10, 10]
    frames = []
    for i, top in enumerate(tops):
        g = blank()
        draw_base(g, 0)
        eyes(g, 0, mode='open')
        rect(g, SCREEN_X[0], top, SCREEN_X[1], top + 2, 'D')        # verres
        hline(g, SCREEN_X[0], SCREEN_X[1], top - 1, 'C')            # monture
        for ex in EYE_X:                                            # yeux derrière
            put(g, ex + 1, top + 1, 'I'); put(g, ex + 2, top + 1, 'I')
        if i >= 6:
            gx = SCREEN_X[0] + (i - 6) * 4
            put(g, gx, top + 2, 'J'); put(g, gx + 1, top + 1, 'J')
        frames.append(g)
    return frames


def anim_sleep():
    """8 frames. Dalle éteinte, yeux fermés, respiration lente."""
    offsets = [1, 1, 1, 2, 2, 2, 1, 1]
    frames = []
    for oy in offsets:
        g = blank()
        draw_base(g, oy, screen_off=True)
        eyes(g, oy, mode='closed')
        frames.append(g)
    return frames


def anim_waking():
    """8 frames. Amorçage CRT puis allumage progressif."""
    frames = []
    for i in range(8):
        g = blank()
        draw_base(g, 0, screen_off=(i == 0))
        if i == 1:
            hline(g, 9, 14, 12, 'J')
        elif i == 2:
            hline(g, SCREEN_X[0], SCREEN_X[1], 12, 'J')
        elif i == 3:
            rect(g, SCREEN_X[0], SCREEN_Y[0], SCREEN_X[1], SCREEN_Y[1], 'J')
        elif i == 4:
            eyes(g, 0, mode='none')
        elif i == 5:
            eyes(g, 0, mode='dim')
        elif i >= 6:
            eyes(g, 0, mode='open')
        frames.append(g)
    return frames


def anim_typing():
    """8 frames. Regard qui balaie + curseur clignotant."""
    scan = [-1, 0, 1, 1, 0, -1, 0, 0]
    frames = []
    for i, dx in enumerate(scan):
        g = blank()
        draw_base(g, 0)
        eyes(g, 0, mode='open', dx=dx)
        if i % 2 == 0:
            put(g, 6, 15, 'G'); put(g, 7, 15, 'G')
        frames.append(g)
    return frames


def anim_love():
    """6 frames. Coeurs + petit coeur qui s'élève. Dernière frame stable."""
    frames = []
    for i in range(6):
        g = blank()
        draw_base(g, 0)
        eyes(g, 0, mode='hearts')
        if i >= 3:
            hy = 1 - (i - 3) // 2
            put(g, 11, hy, 'G'); put(g, 13, hy, 'G')
            put(g, 12, hy + 1, 'G')
        frames.append(g)
    return frames


def anim_yapping():
    """5 frames. Bouche qui s'ouvre, yeux plissés. Frame 2 = pose longue."""
    widths = [1, 3, 5, 3, 2]
    frames = []
    for w in widths:
        g = blank()
        draw_base(g, 0)
        eyes(g, 0, mode='narrow')
        cx = 11
        hline(g, cx - w // 2, cx + 1 + w // 2, 15, 'G')
        if w >= 3:
            hline(g, cx - w // 2 + 1, cx + w // 2, 16, 'I')
        frames.append(g)
    return frames


def anim_search():
    """4 frames. Le pet émerge par le bas et regarde sur le côté."""
    offsets = [18, 12, 6, 0]
    frames = []
    for oy in offsets:
        g = blank()
        draw_base(g, oy)
        eyes(g, oy, mode='open', dx=1)
        frames.append(g)
    return frames


def anim_speech():
    """6 frames. LA BULLE DE DIALOGUE, pas le personnage."""
    boxes = [(10, 10, 13, 12), (8, 8, 15, 13), (6, 6, 17, 15),
             (6, 6, 17, 15), (6, 6, 17, 15), (6, 6, 17, 15)]
    frames = []
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        g = blank()
        rect(g, x0, y0, x1, y1, 'A')
        hline(g, x0, x1, y0, 'D'); hline(g, x0, x1, y1, 'D')
        for y in range(y0, y1 + 1):
            put(g, x0, y, 'D'); put(g, x1, y, 'D')
        rect(g, x0 + 1, y0 + 1, x1 - 1, y0 + 1, 'J')                # brillance
        put(g, x0 + 2, y1 + 1, 'D'); put(g, x0 + 3, y1 + 1, 'D')    # queue
        put(g, x0 + 2, y1 + 2, 'D')
        if i >= 2:
            cy = (y0 + y1) // 2
            dots = [(9, cy), (11, cy), (13, cy)]
            for k, (dx, dy) in enumerate(dots):
                lit = (i - 2) % 3 == k or i == 5
                put(g, dx, dy, 'G' if lit else 'C')
        frames.append(g)
    return frames


# ----------------------------------------------------------------- assemblage
def sheet(frames):
    img = Image.new('RGBA', (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, g in enumerate(frames):
        img.paste(render(g), (i * FRAME, 0))
    return img


# nom de base -> (frames, nb attendu)
def build_all():
    return {
        'idle-{v}-96':                 (anim_idle(False),  50),
        'idle-{v}-tracking-96':        (anim_idle(True),   50),
        'rendering-{v}-tracking-96':   (anim_rendering(),  50),
        'clapping-{v}-tracking-96':    (anim_clapping(),   13),
        'cool-{v}-96':                 (anim_cool(),        9),
        'sleep-{v}-96':                (anim_sleep(),       8),
        'waking-{v}-96':               (anim_waking(),      8),
        'typing-{v}-96':               (anim_typing(),      8),
        'love-{v}-96':                 (anim_love(),        6),
        'speech-{v}-96':               (anim_speech(),      6),
        'yapping-{v}-96':              (anim_yapping(),     5),
        'search-{v}-96':               (anim_search(),      4),
    }


def main(outdir='out'):
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(outdir, 'preview'), exist_ok=True)

    anims = build_all()
    written = 0
    errors = []

    for base, (frames, expected) in anims.items():
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
            render(g).save(os.path.join(outdir, 'preview',
                                        f'{base.format(v="x")}_{i:02d}.png'))

    pal = Image.new('RGBA', (len(PALETTE) * 16, 16), (0, 0, 0, 0))
    for i, (k, c) in enumerate(PALETTE.items()):
        if c:
            pal.paste(Image.new('RGBA', (16, 16), c), (i * 16, 0))
    pal.save(os.path.join(outdir, 'palette.png'))

    print(f'{written} fichiers écrits dans {outdir}/')
    for e in errors:
        print('ERREUR:', e)


if __name__ == '__main__':
    main()
