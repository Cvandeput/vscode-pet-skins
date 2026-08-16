#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aperçus pour le README : bannière animée et planche des états.

    generator/preview.py                 # tous les skins de skins/
    generator/preview.py nixie codex     # seulement ceux-là

Écrit dans `skins/<id>/preview/` :

    banner.gif      le personnage traverse la bannière et joue ses animations
    states.png      une frame représentative de chacun des 21 états
    idle.gif  idle_tracking.gif  love.gif  search.gif

Ces fichiers sont purement décoratifs : contrairement aux sprites et au CSS,
la CI ne les régénère pas (la quantification GIF n'a pas à être un test).

Le cycle de marche n'existe PAS dans VS Code — le pet natif ne se déplace
jamais latéralement (cf. SPRITE-SPEC.md §8). Il est ajouté ici uniquement
pour la bannière. Un skin sans `anchors.feet` glisse au lieu de marcher.

Dépendance : Pillow.
"""

from __future__ import annotations

import math
import os
import sys

from PIL import Image

import petgen as P

ZOOM = 2
FRAME_MS = 55
BANNER_W = 900
STEP = 14


# --------------------------------------------------------------- utilitaires
def big(img, zoom=ZOOM):
    return img.resize((img.width * zoom, img.height * zoom), Image.NEAREST) \
        if zoom != 1 else img


def take(frames, n):
    """Sous-échantillonne une animation trop longue pour la bannière."""
    if n >= len(frames):
        return frames
    return [frames[round(i * (len(frames) - 1) / (n - 1))] for i in range(n)]


def to_gif(images, path, duration=FRAME_MS, colors=32):
    """GIF avec transparence, palette adaptative, dernière entrée = alpha."""
    out = []
    for im in images:
        alpha = im.split()[3]
        q = im.convert('RGB').quantize(colors=colors - 1)
        q.paste(colors - 1, alpha.point(lambda v: 255 if v < 128 else 0))
        out.append(q)
    out[0].save(path, save_all=True, append_images=out[1:], duration=duration,
                loop=0, disposal=2, transparency=colors - 1, optimize=False)


def anims(sk):
    """{clé: [image PIL, ...]} pour tous les états du format.

    Les images sont rendues par `build_all` pendant que le canvas de l'état est
    réglé : depuis 1.133 elles n'ont plus toutes la même taille.
    """
    return {key: e['images'] for key, e in P.build_all(sk).items()}


# ------------------------------------------------------------------- marche
def anim_walk(sk, cycles=1):
    """Déplacement latéral, inventé pour la bannière uniquement."""
    if sk.feet:
        seq = [(0, -1, 0), (0, -1, 0), (0, 0, 1), (0, 0, 1),
               (-1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, 1)]
        frames = []
        for _ in range(cycles):
            for dl, dr, oy in seq:
                g = sk.blank()
                sk.draw_base(g, oy, feet=(dl, dr))
                sk.eyes(g, oy, mode='open')
                frames.append(g)
        return frames

    # personnage flottant : il glisse, le bas ondule
    frames = []
    n = 8 * cycles
    for i in range(n):
        g = sk.blank()
        oy = int(round(math.sin(2 * math.pi * i / 8)))
        wave = P.wave_at(
            {'from': max(0, int(sk.body[3]) - 5), 'amp': 1, 'period': 5,
             'fade': True, 'cycle': 8}, i, n)
        sk.draw_base(g, oy, wave=wave)
        sk.eyes(g, oy, mode='open')
        frames.append(g)
    return frames


# ----------------------------------------------------------------- bannière
def crop_pet(img, spr):
    """Ne garde que la zone du personnage d'une frame large ou haute.

    Depuis 1.133 les frames n'ont plus toutes la même taille ; le pet reste
    ancré en bas à gauche, donc la bannière recadre sur ce coin.
    """
    if img.size == (spr, spr):
        return img
    return img.crop((0, img.height - spr, min(spr, img.width), img.height))


def build_banner(sk):
    spr = sk.frame * ZOOM
    height = spr + 16
    base_y = height - spr - 8
    a = anims(sk)

    def rendered(key):
        return [crop_pet(big(im), spr) for im in a[key]]

    sk.reset_canvas()
    walk = [big(sk.render(g)) for g in anim_walk(sk)]
    idle = rendered('idle')
    speech = rendered('speech')

    show = [
        take(idle, 18), rendered('typing'), take(rendered('rendering-tracking'), 20),
        rendered('clapping-tracking'), rendered('love'), rendered('cool'),
        rendered('yapping'), rendered('jump'), rendered('sing'),
        rendered('search'), rendered('sleep'), rendered('waking'),
    ]

    seq = []                       # (sprite, x, flip, bulle|None)
    stage_x = BANNER_W // 2 - spr // 2

    x, i = -spr, 0
    while x < stage_x:
        seq.append((walk[i % len(walk)], x, False, None))
        x += STEP
        i += 1
    x = stage_x

    for anim in show:
        for f in anim:
            seq.append((f, x, False, None))

    # la bulle, si le skin en a une, apparaît à droite pendant qu'il reste idle
    if sk.speech_bubble:
        for k, bubble in enumerate(speech):
            seq.append((idle[k % len(idle)], x, False, bubble))
        for k in range(6):
            seq.append((idle[k], x, False, speech[k % len(speech)]))

    while x < BANNER_W + 8:
        seq.append((walk[i % len(walk)], x, False, None))
        x += STEP
        i += 1

    x = BANNER_W + 8
    while x > -spr:
        seq.append((walk[i % len(walk)], x, True, None))
        x -= STEP
        i += 1

    out = []
    for sprite, x, flip, bubble in seq:
        canvas = Image.new('RGBA', (BANNER_W, height), (0, 0, 0, 0))
        img = sprite.transpose(Image.FLIP_LEFT_RIGHT) if flip else sprite
        canvas.alpha_composite(img, (int(x), base_y))
        if bubble is not None:
            canvas.alpha_composite(
                bubble, (int(x) + int(spr * 0.72), base_y - int(spr * 0.42)))
        out.append(canvas)
    return out


# ------------------------------------------------------------ planche states
# Les 21 états de 1.133. `press-button`, `typing` et `sing` ont une frame plus
# large que les autres, `sing` est aussi plus haute : la planche ne peut plus
# être une grille de cellules carrées.
STATE_ORDER = ['idle', 'idle-tracking', 'rendering-tracking',
               'clapping-tracking', 'cool', 'love',
               'yapping', 'search', 'sleep', 'waking', 'speech', 'worry',
               'falling', 'jump', 'splat', 'speechless', 'respawn',
               'revive-sign', 'typing', 'press-button', 'sing']

# frame représentative de chaque état : la plus lisible, pas la frame 0
STATE_FRAME = {'idle': 0, 'idle-tracking': 0, 'typing': 0,
               'rendering-tracking': 30, 'clapping-tracking': 3, 'cool': 8,
               'love': 5, 'yapping': 2, 'search': 3, 'sleep': 4, 'waking': 7,
               'speech': 4, 'falling': 3, 'jump': 2, 'press-button': 5,
               'respawn': 4, 'revive-sign': 0, 'sing': 1, 'speechless': 3,
               'splat': 3, 'worry': 0}


def build_states(sk, zoom=2, pad=8, max_width=1400):
    """Mise en page à la volée : les frames n'ont plus toutes la même taille."""
    a = anims(sk)
    picked = []
    for key in STATE_ORDER:
        frames = a.get(key)
        if not frames:
            continue
        idx = min(STATE_FRAME.get(key, 0), len(frames) - 1)
        picked.append(big(frames[idx], zoom))

    rows, cur, cur_w = [], [], 0
    for img in picked:
        w = img.width + pad * 2
        if cur and cur_w + w > max_width:
            rows.append(cur)
            cur, cur_w = [], 0
        cur.append(img)
        cur_w += w
    if cur:
        rows.append(cur)

    widths = [sum(i.width + pad * 2 for i in r) for r in rows]
    heights = [max(i.height for i in r) + pad * 2 for r in rows]
    sheet = Image.new('RGBA', (max(widths), sum(heights)), (0, 0, 0, 0))
    y = 0
    for r, h in zip(rows, heights):
        x = 0
        for img in r:
            # aligné en bas : le pet garde le même sol d'une case à l'autre
            sheet.alpha_composite(img, (x + pad, y + h - pad - img.height))
            x += img.width + pad * 2
        y += h
    return sheet


# ---------------------------------------------------------------------- E/S
def write_previews(sk):
    outdir = os.path.join(os.path.dirname(sk.source), 'preview')
    os.makedirs(outdir, exist_ok=True)
    a = anims(sk)

    to_gif(build_banner(sk), os.path.join(outdir, 'banner.gif'))
    build_states(sk).save(os.path.join(outdir, 'states.png'), optimize=True)

    loops = {'idle': ('idle', 40), 'idle_tracking': ('idle-tracking', 40),
             'love': ('love', 200), 'search': ('search', 500)}
    for name, (key, ms) in loops.items():
        frames = [big(im) for im in a[key]]
        to_gif(frames, os.path.join(outdir, f'{name}.gif'), duration=ms)

    print(f"skin '{sk.name}' : banner.gif, states.png et 4 gifs d'etat")


def main(argv):
    targets = argv or P.all_skin_ids()
    status = 0
    for target in targets:
        try:
            write_previews(P.load_skin(target))
        except P.SkinError as exc:
            print(f'ERREUR [{target}] : {exc}')
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
