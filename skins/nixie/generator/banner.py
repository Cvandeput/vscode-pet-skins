#!/usr/bin/env python3
"""
Génère la bannière animée du README : Nixie traverse l'image de gauche à
droite, joue toutes ses animations au centre, puis repart vers la gauche.

Le cycle de marche n'existe PAS dans VS Code — le pet natif ne se déplace
jamais latéralement (cf. SPRITE-SPEC.md §8). Il est ajouté ici uniquement
pour la bannière.

Dépendance : Pillow. À lancer depuis ce dossier.

    python banner.py            # écrit banner.gif
"""

from PIL import Image
import petgen as P

ZOOM = 2                 # agrandissement du sprite dans la bannière
SPR = P.FRAME * ZOOM     # 192
W, H = 900, SPR + 16     # dimensions de la bannière
BASE_Y = H - SPR - 8     # ligne de sol
STEP = 14                # pixels par frame de marche
FRAME_MS = 55

# ------------------------------------------------------------------ marche
def anim_walk(cycles=1):
    """Cycle de marche 8 frames : les pieds alternent, le corps rebondit."""
    seq = [(0, -1, 0), (0, -1, 0), (0, 0, 1), (0, 0, 1),
           (-1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, 1)]
    frames = []
    for _ in range(cycles):
        for dl, dr, oy in seq:
            g = P.blank()
            P.draw_base(g, oy, feet=(dl, dr))
            P.eyes(g, oy, mode='open')
            frames.append(big(P.render(g)))
    return frames


def take(frames, n):
    """Sous-échantillonne une animation trop longue pour la bannière."""
    if n >= len(frames):
        return frames
    return [frames[round(i * (len(frames) - 1) / (n - 1))] for i in range(n)]


def big(img):
    return img.resize((SPR, SPR), Image.NEAREST) if ZOOM != 1 else img


def render_all(grids):
    return [big(P.render(g)) for g in grids]


# ------------------------------------------------------------------ montage
def build():
    walk = anim_walk()
    idle      = render_all(P.anim_idle(False))
    typing    = render_all(P.anim_typing())
    rendering = render_all(P.anim_rendering())
    clapping  = render_all(P.anim_clapping())
    love      = render_all(P.anim_love())
    cool      = render_all(P.anim_cool())
    yapping   = render_all(P.anim_yapping())
    search    = render_all(P.anim_search())
    sleep     = render_all(P.anim_sleep())
    waking    = render_all(P.anim_waking())
    speech    = render_all(P.anim_speech())

    frames = []            # liste de (sprite, x, flip, bulle|None)
    stage_x = W // 2 - SPR // 2

    # 1. entrée par la gauche
    x = -SPR
    i = 0
    while x < stage_x:
        frames.append((walk[i % len(walk)], x, False, None))
        x += STEP
        i += 1
    x = stage_x

    # 2. démonstration sur place, dans l'ordre d'une session de travail
    show = [
        take(idle, 18), typing, take(rendering, 20), clapping,
        love, cool, yapping, take(search, 4), sleep, waking,
    ]
    for anim in show:
        for f in anim:
            frames.append((f, x, False, None))

    # bulle de dialogue : le pet reste idle, la bulle apparaît à sa droite
    for k, b in enumerate(speech):
        frames.append((idle[k % len(idle)], x, False, b))
    for k in range(6):
        frames.append((idle[k], x, False, speech[-1]))

    # 3. sortie par la droite
    while x < W + 8:
        frames.append((walk[i % len(walk)], x, False, None))
        x += STEP
        i += 1

    # 4. retour vers la gauche, sprite miroir
    x = W + 8
    while x > -SPR:
        frames.append((walk[i % len(walk)], x, True, None))
        x -= STEP
        i += 1

    return frames


def compose(frames):
    out = []
    for spr, x, flip, bubble in frames:
        c = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        s = spr.transpose(Image.FLIP_LEFT_RIGHT) if flip else spr
        c.alpha_composite(s, (int(x), BASE_Y))
        if bubble is not None:
            c.alpha_composite(bubble, (int(x) + int(SPR * 0.72), BASE_Y - int(SPR * 0.42)))
        out.append(c)
    return out


def to_gif(images, path, duration=FRAME_MS, colors=16):
    res = []
    for im in images:
        alpha = im.split()[3]
        q = im.convert('RGB').quantize(colors=colors - 1)
        q.paste(colors - 1, alpha.point(lambda v: 255 if v < 128 else 0))
        res.append(q)
    res[0].save(path, save_all=True, append_images=res[1:], duration=duration,
                loop=0, disposal=2, transparency=colors - 1, optimize=False)


if __name__ == '__main__':
    imgs = compose(build())
    to_gif(imgs, 'banner.gif')
    im = Image.open('banner.gif')
    print(f'banner.gif  {im.size[0]}x{im.size[1]}  {im.n_frames} frames')
