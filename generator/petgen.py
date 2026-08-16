#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de sprites pour le « pet » natif de VS Code (>= 1.131).

Ce fichier ne contient AUCUN dessin et AUCUNE hypothèse sur la morphologie du
personnage. C'est un interpréteur : tout vient de `skins/<id>/skin.json`.

    generator/petgen.py                 # regénère tous les skins de skins/
    generator/petgen.py nixie vapor     # seulement ces skins
    generator/petgen.py chemin/skin.json
    generator/petgen.py --out DIR nixie # écrit ailleurs, sans toucher au dépôt

Pour chaque skin, la sortie est reproductible au bit près :

    skins/<id>/sprites/buddy-*.png      les 48 fichiers attendus par VS Code
    skins/<id>/css/pet.css              dérivé de palette + anchors.eyes

La CI regénère et vérifie que `git diff` est vide (cf. .github/workflows/ci.yml).

Chaque animation de `skin.json` est soit une primitive paramétrée :

    "typing": { "builtin": "typing", "params": { "cursorBlinks": 1 } }

soit une liste explicite de frames, au même format que `base` :

    "cool": { "frames": [ ["........", ...], ["........", ...] ] }

Les primitives dégradent proprement quand un repère manque : `anchors.feet`
vide (personnage flottant), `anchors.screen` absent, rôle de palette non
défini — rien ne plante, l'effet concerné est simplement omis ou remplacé.

Dépendance : Pillow.
"""

from __future__ import annotations

import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKINS_DIR = os.path.join(REPO, 'skins')

# --------------------------------------------------------------------- slots
# (clé d'animation, gabarit de nom, nombre de frames, sprite « tracking »)
#
# Le nombre de frames est IMPOSÉ par des tables de durées codées en dur dans le
# JavaScript de VS Code. Toute divergence désynchronise l'animation.
SLOTS = [
    ('idle',               'idle-{v}-96',               50, False),
    ('idle-tracking',      'idle-{v}-tracking-96',      50, True),
    ('rendering-tracking', 'rendering-{v}-tracking-96', 50, True),
    ('clapping-tracking',  'clapping-{v}-tracking-96',  13, True),
    ('cool',               'cool-{v}-96',                9, False),
    ('sleep',              'sleep-{v}-96',               8, False),
    ('waking',             'waking-{v}-96',              8, False),
    ('typing',             'typing-{v}-96',              8, False),
    ('love',               'love-{v}-96',                6, False),
    ('speech',             'speech-{v}-96',              6, False),
    ('yapping',            'yapping-{v}-96',             5, False),
    ('search',             'search-{v}-96',              4, False),
]

FRAME_COUNTS = {key: n for key, _, n, _ in SLOTS}

# Animation par défaut de chaque slot, quand `skin.json` n'en dit rien.
DEFAULT_ANIMATIONS = {
    'idle':               {'builtin': 'idle'},
    'idle-tracking':      {'builtin': 'idle'},
    'rendering-tracking': {'builtin': 'rendering'},
    'clapping-tracking':  {'builtin': 'clapping'},
    'cool':               {'builtin': 'cool'},
    'sleep':              {'builtin': 'sleep'},
    'waking':             {'builtin': 'waking'},
    'typing':             {'builtin': 'typing'},
    'love':               {'builtin': 'love'},
    'speech':             {'builtin': 'speech'},
    'yapping':            {'builtin': 'yapping'},
    'search':             {'builtin': 'search'},
}


class SkinError(Exception):
    """Erreur de définition d'un skin, remontée avec un message lisible."""


# ------------------------------------------------------------------ outillage
def _hexa(value):
    h = str(value).lstrip('#')
    if len(h) not in (6, 8):
        raise SkinError(f"couleur invalide : {value!r}")
    rgba = tuple(int(h[i:i + 2], 16) for i in range(0, len(h), 2))
    return rgba if len(rgba) == 4 else rgba + (255,)


def _grid_from_rows(rows, size):
    """Normalise une liste de chaînes en grille size x size."""
    out = [list(str(r).ljust(size, '.')[:size]) for r in rows[:size]]
    while len(out) < size:
        out.append(['.'] * size)
    return out


def _resample(seq, n):
    """Étire ou comprime une séquence de repères sur n frames."""
    seq = list(seq)
    if not seq:
        return [0] * n
    if len(seq) == n:
        return seq
    if n == 1:
        return [seq[0]]
    return [seq[round(i * (len(seq) - 1) / (n - 1))] for i in range(n)]


def wave_at(params, i, n):
    """Instancie les paramètres d'ondulation pour la frame i."""
    if not params:
        return None
    cycle = max(1, int(params.get('cycle', n)))
    w = dict(params)
    w['phase'] = (i % cycle) / cycle
    w['step'] = i
    return w


# ---------------------------------------------------------------------- skin
class Skin:
    """Un skin chargé : palette, grille de base, repères, animations."""

    def __init__(self, data, source=None):
        self.data = data
        self.source = source
        self.id = data.get('id') or (
            os.path.basename(os.path.dirname(source)) if source else 'skin')
        self.name = data.get('name', self.id)

        self.size = int(data.get('grid', 24))
        self.scale = int(data.get('scale', 4))
        self.frame = self.size * self.scale
        if self.frame != 96:
            raise SkinError(
                f"grid x scale doit valoir 96 (ici {self.size} x {self.scale} "
                f"= {self.frame})")

        if not data.get('base'):
            raise SkinError("`base` manquant")
        self.base = _grid_from_rows(data['base'], self.size)

        self.palette = {'.': None}
        for key, value in (data.get('palette') or {}).items():
            self.palette[key] = _hexa(value)

        self.roles = data.get('roles') or {}

        anchors = data.get('anchors') or {}
        eyes = anchors.get('eyes') or {}
        self.eye_l = tuple(eyes.get('left', [6, 10]))
        self.eye_r = tuple(eyes.get('right', [14, 10]))
        if not (len(self.eye_l) == 2 and len(self.eye_r) == 2):
            raise SkinError("anchors.eyes.left / .right doivent etre [x, y]")
        socket = eyes.get('socket', [4, 4])
        self.eye_w, self.eye_h = int(socket[0]), int(socket[1])
        self.eye_style = eyes.get('style', 'pupil')   # pupil | slit
        self.eye_y = int(self.eye_l[1])
        self.eye_x = (int(self.eye_l[0]), int(self.eye_r[0]))

        self.screen = tuple(anchors['screen']) if anchors.get('screen') else None
        self.body = tuple(anchors.get('body', [0, 0, self.size - 1, self.size - 1]))
        self.feet = [tuple(f) for f in (anchors.get('feet') or [])]
        self.mouth = tuple(anchors['mouth']) if anchors.get('mouth') else None
        self.bubble = tuple(anchors['bubble']) if anchors.get('bubble') else None

        self.speech_bubble = bool(data.get('speechBubble', True))

        self.animations = dict(DEFAULT_ANIMATIONS)
        self.animations.update(data.get('animations') or {})

        # rôles résolus une fois pour toutes ; None = effet omis
        self.c_screen = self.role('screen')
        self.c_screen_off = self.role('screenOff', 'outline', 'shadow')
        self.c_flick = self.role('screenFlicker', 'screen')
        self.c_socket = self.role('socket', 'outline')
        self.c_rim = self.role('socketRim', 'socket', 'outline')
        self.c_core = self.role('eyeCore')
        self.c_light = self.role('eyeLight', 'eyeCore')
        self.c_dark = self.role('eyeShadow', 'eyeCore')
        self.c_halo = self.role('halo')
        self.c_halo2 = self.role('haloStrong', 'halo')
        self.c_spark = self.role('spark', 'eyeLight', 'eyeCore')
        self.c_shadow = self.role('shadow', 'outline')
        self.c_out = self.role('outline', 'shadow')
        self.c_bubble = self.role('bubbleFill')
        self.c_shine = self.role('bubbleShine', 'spark')
        self.c_page = self.role('pageFront', 'bubbleFill', 'spark')
        self.c_page2 = self.role('pageBack', 'shadow', 'outline')
        self.c_ink = self.role('ink', 'outline', 'shadow')
        # les coeurs de `love` : sur une silhouette deja claire, eyeCore s'y
        # noie — un skin peut donner une couleur d'accent dediee.
        self.c_heart = self.role('heart', 'eyeCore')

        if not self.c_core:
            raise SkinError("le role `eyeCore` est obligatoire")

    # ---------------------------------------------------------------- rôles
    def role(self, *names):
        """Premier rôle défini ET présent dans la palette, sinon None."""
        for name in names:
            char = self.roles.get(name)
            if char and char in self.palette and self.palette[char]:
                return char
        return None

    def color(self, *names):
        """Couleur hexadécimale d'un rôle, pour le CSS."""
        char = self.role(*names)
        if not char:
            return None
        r, g, b, _ = self.palette[char]
        return f'#{r:02X}{g:02X}{b:02X}'

    def screen_rect(self):
        """`anchors.screen`, ou un bandeau dérivé du corps si absent."""
        if self.screen:
            return tuple(int(v) for v in self.screen)
        x0, y0, x1, y1 = self.body
        return (x0 + 1, max(y0, y1 - 6), x1 - 1, max(y0 + 1, y1 - 1))

    def mouth_pos(self):
        if self.mouth:
            return int(self.mouth[0]), int(self.mouth[1])
        x0, y0, x1, y1 = self.screen_rect()
        return (x0 + x1) // 2, y1 - 1

    # ------------------------------------------------------------- primitives
    def blank(self):
        return [['.'] * self.size for _ in range(self.size)]

    def put(self, g, x, y, c):
        if c and 0 <= x < self.size and 0 <= y < self.size:
            g[y][x] = c

    def hline(self, g, x0, x1, y, c):
        for x in range(int(x0), int(x1) + 1):
            self.put(g, x, y, c)

    def vline(self, g, x, y0, y1, c):
        for y in range(int(y0), int(y1) + 1):
            self.put(g, x, y, c)

    def rect(self, g, x0, y0, x1, y1, c):
        for y in range(int(y0), int(y1) + 1):
            self.hline(g, x0, x1, y, c)

    def render(self, g):
        img = Image.new('RGBA', (self.size, self.size), (0, 0, 0, 0))
        px = img.load()
        for y in range(self.size):
            for x in range(self.size):
                col = self.palette.get(g[y][x])
                if col:
                    px[x, y] = col
        return img.resize((self.frame, self.frame), Image.NEAREST)

    # ------------------------------------------------------------ personnage
    def _in_foot(self, x, y):
        for i, (x0, y0, x1, y1) in enumerate(self.feet):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        return None

    def _squeeze_map(self, squeeze):
        """y source -> y destination, `squeeze` lignes retirees, bas ancre."""
        if squeeze <= 0:
            return {y: y for y in range(self.size)}
        y0, y1 = int(self.body[1]), int(self.body[3])
        span = list(range(y0, y1 + 1))
        k = max(0, min(int(squeeze), len(span) - 1))
        drop = {span[round((i + 1) * len(span) / (k + 1)) - 1] for i in range(k)}
        ymap, shift = {}, 0
        for y in range(self.size - 1, -1, -1):
            if y in drop:
                ymap[y] = None
                shift += 1
            else:
                ymap[y] = y + shift
        return ymap

    def squeeze_shift(self, squeeze):
        """Déplacement vertical subi par la rangée des orbites sous `squeeze`.

        `draw_base` tasse le corps ; sans ce décalage, les yeux resteraient à
        leur place pendant que le visage descend, et sortiraient du corps.
        """
        if squeeze <= 0:
            return 0
        ymap = self._squeeze_map(squeeze)
        for y in range(self.eye_y, self.size):
            if ymap.get(y) is not None:
                return ymap[y] - self.eye_y
        return 0

    @staticmethod
    def _dissolve(x, y, depth, wave):
        """Trouage déterministe : plus on descend, plus le corps se dissipe."""
        if depth <= 0:
            return False
        k = max(2, int(wave.get('fadeFrom', 6)) - depth)
        return ((x * 3 + y * 5 + int(wave.get('step', 0)) * 7) % k) == 0

    def draw_base(self, g, oy=0, flicker=False, feet=(0, 0), wave=None,
                  squeeze=0, screen_off=False):
        """Pose la grille de base.

        oy         décalage vertical global
        feet       levée de chaque zone de `anchors.feet` (ignoré si vide)
        wave       ondulation horizontale du bas du corps, cf. wave_at
        squeeze    tassement vertical, bas ancré
        flicker    la dalle passe en couleur `screenFlicker`
        screen_off la dalle passe en couleur `screenOff`
        """
        ymap = self._squeeze_map(squeeze)
        for y in range(self.size):
            ty = ymap[y]
            if ty is None:
                continue
            for x in range(self.size):
                c = self.base[y][x]
                if c == '.':
                    continue
                dx = 0
                if wave and y >= int(wave.get('from', self.size)):
                    depth = y - int(wave.get('from', self.size))
                    period = max(1, int(wave.get('period', 6)))
                    dx = int(round(float(wave.get('amp', 1)) * math.sin(
                        2 * math.pi * (float(wave.get('phase', 0.0))
                                       + depth / period))))
                    if wave.get('fade') and self._dissolve(x, y, depth, wave):
                        continue
                if screen_off and c == self.c_screen and self.c_screen_off:
                    c = self.c_screen_off
                foot = self._in_foot(x, y)
                fdy = feet[foot] if foot is not None and foot < len(feet) else 0
                self.put(g, x + dx, ty + oy + fdy, c)

        if flicker and self.screen and self.c_flick and self.c_screen:
            x0, y0, x1, y1 = self.screen_rect()
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if 0 <= y + oy < self.size and 0 <= x < self.size:
                        if g[y + oy][x] == self.c_screen:
                            g[y + oy][x] = self.c_flick

    # ------------------------------------------------------------------ yeux
    def socket(self, g, oy, ex, ey=None, squash=False):
        ey = self.eye_y if ey is None else ey
        if squash:
            self.hline(g, ex, ex + self.eye_w - 1, ey + self.eye_h - 1 + oy,
                       self.c_socket)
            return
        self.hline(g, ex, ex + self.eye_w - 1, ey + oy, self.c_rim)
        for y in range(ey + 1, ey + self.eye_h):
            self.hline(g, ex, ex + self.eye_w - 1, y + oy, self.c_socket)

    def halo(self, g, oy, ex, ey=None):
        if not self.c_halo:
            return
        ey = self.eye_y if ey is None else ey
        for x in range(ex - 1, ex + self.eye_w + 1):
            self.put(g, x, ey - 1 + oy, self.c_halo)
            self.put(g, x, ey + self.eye_h + oy, self.c_halo)
        for y in range(ey, ey + self.eye_h):
            self.put(g, ex - 1, y + oy, self.c_halo)
            self.put(g, ex + self.eye_w, y + oy, self.c_halo)

    def pupil(self, g, oy, ex, ey=None, dx=0, dy=0, dim=False, squash=False):
        ey = self.eye_y if ey is None else ey
        if dim:
            core = hi = lo = self.c_dark
        else:
            core, hi, lo = self.c_core, self.c_light, self.c_dark
        x = ex + max(0, (self.eye_w - 2) // 2) + dx
        y = ey + max(0, (self.eye_h - 2) // 2) + dy + oy
        if squash:
            self.put(g, x, ey + self.eye_h - 1 + oy, core)
            self.put(g, x + 1, ey + self.eye_h - 1 + oy, core)
            return
        self.put(g, x, y, hi)
        self.put(g, x + 1, y, core)
        self.put(g, x, y + 1, core)
        self.put(g, x + 1, y + 1, lo)

    def _slit(self, g, oy, ex, color=None):
        """Fente lumineuse : yeux étroits, sans pupille carrée."""
        y = self.eye_y + max(1, self.eye_h // 2) + oy
        inset = 1 if self.eye_w >= 4 else 0
        self.hline(g, ex + inset, ex + self.eye_w - 1 - inset, y,
                   color or self.c_core)

    def eyes(self, g, oy, mode='open', dx=0, dy=0, squash=False, squeeze=0):
        """mode : open | closed | dim | hearts | narrow | none

        `squeeze` doit reprendre la valeur passée à `draw_base` : les orbites
        suivent alors le tassement du corps au lieu de rester en l'air.
        """
        oy += self.squeeze_shift(squeeze)
        for ex in self.eye_x:
            if mode == 'none':
                # sprite « tracking » : orbite creuse, VS Code pose la pupille
                self.socket(g, oy, ex, squash=squash)
                continue
            if mode == 'closed':
                self.socket(g, oy, ex)
                self.hline(g, ex + 1, ex + self.eye_w - 2,
                           self.eye_y + min(2, self.eye_h - 1) + oy, self.c_dark)
                continue
            if mode == 'hearts' and self.eye_h >= 4 and self.eye_w >= 3:
                self.socket(g, oy, ex)
                ey = self.eye_y
                self.put(g, ex, ey + 1 + oy, self.c_light)
                self.put(g, ex + 2, ey + 1 + oy, self.c_core)
                self.hline(g, ex, ex + self.eye_w - 1, ey + 2 + oy, self.c_core)
                self.put(g, ex + 1, ey + 3 + oy, self.c_core)
                self.put(g, ex + 2, ey + 3 + oy, self.c_core)
                self.halo(g, oy, ex)
                continue
            if mode in ('narrow', 'hearts'):
                self.socket(g, oy, ex)
                self._slit(g, oy, ex)
                self.halo(g, oy, ex)
                continue
            # open / dim
            self.socket(g, oy, ex, squash=squash)
            if self.eye_style == 'slit' and not squash:
                self._slit(g, oy, ex, self.c_dark if mode == 'dim' else None)
            else:
                self.pupil(g, oy, ex, dx=dx, dy=dy,
                           dim=(mode == 'dim'), squash=squash)
            self.halo(g, oy, ex)


# ------------------------------------------------------------------ builtins
# Signature commune : (skin, nb_frames, params, tracking) -> [grille, ...]
# `tracking` force les orbites creuses (VS Code superpose ses propres pupilles).

def _eye_mode(p, tracking):
    return 'none' if tracking else p.get('eyes', 'open')


def bi_still(sk, n, p, tracking):
    """Pose fixe. Repli sûr quand un skin ne veut rien animer."""
    out = []
    for _ in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode=_eye_mode(p, tracking))
        out.append(g)
    return out


def bi_blank(sk, n, p, tracking):
    """Frames entièrement transparentes."""
    return [sk.blank() for _ in range(n)]


def bi_idle(sk, n, p, tracking):
    """Respiration en palier + clignement + scintillement de la dalle.

    Les repères par défaut reproduisent la synchronisation attendue par les
    keyframes CSS de VS Code : palier à 40 % du cycle, clignement au milieu.
    """
    bob = int(p.get('bob', 1))
    bob_at = int(p.get('bobAt', round(n * 0.40)))
    blink = p.get('blink', [round(n * 0.46), round(n * 0.54)])
    flicker = set(p.get('flicker', [round(n * 0.16), round(n * 0.88)]
                        if sk.screen else []))
    wave = p.get('wave')
    mode = _eye_mode(p, tracking)
    out = []
    for i in range(n):
        g = sk.blank()
        oy = bob if i >= bob_at else 0
        sk.draw_base(g, oy, flicker=(i in flicker), wave=wave_at(wave, i, n))
        sk.eyes(g, oy, mode=mode,
                squash=bool(blink) and blink[0] <= i <= blink[1])
        out.append(g)
    return out


def bi_float(sk, n, p, tracking):
    """Flottement vertical sinusoïdal, bas du corps qui ondule et se dissipe.

    Aucun contact avec le sol : ne lit jamais `anchors.feet`.
    """
    amp = float(p.get('amp', 1.0))
    cycle = max(1, int(p.get('cycle', n)))
    offset = int(p.get('offset', 0))
    squeeze = int(p.get('squeeze', 0))
    blink = p.get('blink', [round(n * 0.46), round(n * 0.54)] if n >= 10 else [])
    mode = _eye_mode(p, tracking)
    wave = dict(p.get('wave') or {
        'from': max(0, int(sk.body[3]) - 5), 'amp': 1, 'period': 5, 'fade': True})
    wave.setdefault('cycle', max(2, cycle // 2))
    sparks = p.get('sparks', 0)
    out = []
    for i in range(n):
        g = sk.blank()
        oy = offset + int(round(amp * math.sin(2 * math.pi * i / cycle)))
        sk.draw_base(g, oy, wave=wave_at(wave, i, n), squeeze=squeeze)
        sk.eyes(g, oy, mode=mode, squeeze=squeeze,
                squash=bool(blink) and blink[0] <= i <= blink[1])
        if sparks and sk.c_spark:
            k = i % max(2, int(sparks))
            sk.put(g, int(sk.body[0]) + k, int(sk.body[1]) + oy - 1, sk.c_spark)
            sk.put(g, int(sk.body[2]) - k, int(sk.body[1]) + oy + 1, sk.c_spark)
        out.append(g)
    return out


def bi_rendering(sk, n, p, tracking):
    """Ligne de balayage + barre de progression dans la zone `screen`.

    Sans `anchors.screen`, la barre se pose sur le bandeau bas du corps.
    """
    x0, y0, x1, y1 = tuple(p.get('rect') or sk.screen_rect())
    bar_y = y1 - 1
    span = max(1, y1 - y0 + 1)
    mode = _eye_mode(p, tracking)
    fill = sk.c_halo2 or sk.c_core
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        scan = y0 + (i % span)
        if not (sk.eye_y <= scan < sk.eye_y + sk.eye_h) and sk.c_flick:
            sk.hline(g, x0, x1, scan, sk.c_flick)
        sk.eyes(g, 0, mode=mode)
        if sk.c_flick:
            sk.hline(g, x0, x1, bar_y, sk.c_flick)
        filled = x0 + round((x1 - x0) * i / max(1, n - 1))
        sk.hline(g, x0, filled, bar_y, fill)
        sk.put(g, filled, bar_y, sk.c_core)
        out.append(g)
    return out


def bi_clapping(sk, n, p, tracking):
    """Sauts + étincelles de part et d'autre du corps."""
    offsets = _resample(p.get('offsets',
                              [0, -1, -2, -2, -1, 0, -1, -2, -2, -1, 0, -1, 0]), n)
    peak = min(offsets)
    mode = _eye_mode(p, tracking)
    bx0, _, bx1, _ = (int(v) for v in sk.body)
    # les etincelles partent a hauteur de « visage », pas du sommet du corps
    sy = int(p.get('sparkY', sk.screen_rect()[1]))
    out = []
    for oy in offsets:
        g = sk.blank()
        sk.draw_base(g, oy)
        sk.eyes(g, oy, mode=mode)
        if oy <= peak and sk.c_spark:
            sk.put(g, bx0 - 1, sy + oy, sk.c_spark)
            sk.put(g, bx1 + 1, sy + oy, sk.c_spark)
            sk.put(g, bx0 - 2, sy + 3 + oy, sk.c_spark)
            sk.put(g, bx1 + 2, sy + 3 + oy, sk.c_spark)
        out.append(g)
    return out


def bi_cool(sk, n, p, tracking):
    """Lunettes noires qui descendent sur les orbites, puis éclat."""
    drop = max(1, int(p.get('drop', 3)))
    ey = sk.eye_y
    gx0 = min(sk.eye_x) - 1
    gx1 = max(sk.eye_x) + sk.eye_w
    tops = [ey - drop + i for i in range(drop)] + [ey] * max(0, n - drop)
    tops = tops[:n]
    thick = max(1, min(3, sk.eye_h))
    mode = _eye_mode(p, tracking)
    shine_from = max(0, n - 3)
    out = []
    for i, top in enumerate(tops):
        g = sk.blank()
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode=mode)
        sk.rect(g, gx0, top, gx1, top + thick - 1, sk.c_socket)
        sk.hline(g, gx0, gx1, top - 1, sk.c_shadow)
        for ex in sk.eye_x:
            sk.put(g, ex + 1, top + thick // 2, sk.c_dark)
            sk.put(g, ex + 2, top + thick // 2, sk.c_dark)
        if i >= shine_from and sk.c_spark:
            gx = gx0 + (i - shine_from) * 4
            sk.put(g, gx, top + thick - 1, sk.c_spark)
            sk.put(g, gx + 1, top + thick // 2, sk.c_spark)
        out.append(g)
    return out


def bi_sleep(sk, n, p, tracking):
    """Le personnage s'affaisse, dalle éteinte, yeux fermés."""
    settle = _resample(p.get('settle', [1, 1, 1, 2, 2, 2, 1, 1]), n)
    squeeze = _resample(p.get('squeeze', [0] * n), n)
    wave = p.get('wave')
    screen_off = p.get('screenOff', True)
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, settle[i], squeeze=squeeze[i], screen_off=screen_off,
                     wave=wave_at(wave, i, n))
        sk.eyes(g, settle[i], mode=p.get('eyes', 'closed'), squeeze=squeeze[i])
        out.append(g)
    return out


def bi_waking(sk, n, p, tracking):
    """Réveil.

    mode `crt`  : amorçage d'un écran (défaut si `anchors.screen` existe)
    mode `rise` : le corps se regonfle et le regard revient (défaut sinon)
    """
    mode = p.get('mode') or ('crt' if sk.screen else 'rise')
    if mode == 'crt':
        x0, y0, x1, y1 = tuple(p.get('rect') or sk.screen_rect())
        mid = (y0 + y1) // 2
        cx = (x0 + x1) // 2
        out = []
        for i in range(n):
            g = sk.blank()
            sk.draw_base(g, 0, screen_off=(i == 0))
            if i == 1:
                sk.hline(g, cx - 3, cx + 3, mid, sk.c_spark)
            elif i == 2:
                sk.hline(g, x0, x1, mid, sk.c_spark)
            elif i == 3:
                sk.rect(g, x0, y0, x1, y1, sk.c_spark)
            elif i == 4:
                sk.eyes(g, 0, mode='none')
            elif i == 5:
                sk.eyes(g, 0, mode='dim')
            else:
                sk.eyes(g, 0, mode='open')
            out.append(g)
        return out

    settle = _resample(p.get('settle', [2, 2, 1, 1, 1, 0, 0, 0]), n)
    squeeze = _resample(p.get('squeeze', [0] * n), n)
    eye_seq = _resample(p.get('eyeSeq',
                              ['closed', 'closed', 'closed', 'dim', 'dim',
                               'open', 'open', 'open']), n)
    wave = p.get('wave')
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, settle[i], squeeze=squeeze[i],
                     wave=wave_at(wave, i, n))
        sk.eyes(g, settle[i], mode='none' if tracking else eye_seq[i],
                squeeze=squeeze[i])
        out.append(g)
    return out


def bi_typing(sk, n, p, tracking):
    """Le regard balaie, un curseur clignote.

    `cursorBlinks` = nombre de clignotements par cycle d'animation. La valeur
    par défaut est 1 : allumé sur la première moitié du cycle, éteint sur la
    seconde. Au-delà de 2, le clignotement redevient illisible.
    """
    gaze = _resample(p.get('gaze', [-1, 0, 1, 1, 0, -1, 0, 0]), n)
    blinks = max(1, int(p.get('cursorBlinks', 1)))
    x0, _, _, y1 = tuple(p.get('rect') or sk.screen_rect())
    cx = int(p.get('cursorX', x0 + 1))
    cy = int(p.get('cursorY', y1 - 1))
    width = max(1, int(p.get('cursorWidth', 2)))
    mode = _eye_mode(p, tracking)
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode=mode, dx=gaze[i])
        if ((i * 2 * blinks) // n) % 2 == 0:
            sk.hline(g, cx, cx + width - 1, cy, sk.c_core)
        out.append(g)
    return out


def bi_love(sk, n, p, tracking):
    """Yeux en cœur et petit cœur qui s'élève. Dernière frame stable."""
    # `heartX` accepte un entier ou une liste : les silhouettes claires ont
    # besoin que les coeurs montent DANS LE VIDE, pas par-dessus le corps, ou
    # ils s'y noient. `heartY` donne la ligne de depart.
    xs = p.get('heartX', (sk.body[0] + sk.body[2]) // 2)
    xs = [int(x) for x in (xs if isinstance(xs, list) else [xs])]
    top = int(p.get('heartY', sk.body[1]))
    rise_from = int(p.get('riseFrom', max(1, n // 2)))
    mode = 'none' if tracking else p.get('eyes', 'hearts')
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode=mode)
        if i >= rise_from:
            hy = max(0, top - 1 - (i - rise_from) // 2)
            for cx in xs:
                sk.put(g, cx - 1, hy, sk.c_heart)
                sk.put(g, cx + 1, hy, sk.c_heart)
                sk.put(g, cx, hy + 1, sk.c_heart)
        out.append(g)
    return out


def bi_yapping(sk, n, p, tracking):
    """Bouche qui s'ouvre et se referme, yeux plissés."""
    widths = _resample(p.get('widths', [1, 3, 5, 3, 2]), n)
    cx, my = sk.mouth_pos()
    mode = 'none' if tracking else p.get('eyes', 'narrow')
    out = []
    for w in widths:
        g = sk.blank()
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode=mode)
        sk.hline(g, cx - w // 2, cx + 1 + w // 2, my, sk.c_core)
        if w >= 3:
            sk.hline(g, cx - w // 2 + 1, cx + w // 2, my + 1, sk.c_dark)
        out.append(g)
    return out


def bi_search(sk, n, p, tracking):
    """Coup d'œil vertical : le pet remonte de sous la zone de saisie.

    Ce n'est PAS un cycle de marche (cf. SPRITE-SPEC.md §8).
    """
    depth = int(p.get('depth', sk.size - 6))
    mode = _eye_mode(p, tracking)
    gaze = int(p.get('gaze', 1))
    prop = p.get('prop')
    out = []
    for i in range(n):
        oy = round(depth * (1 - i / max(1, n - 1)))
        g = sk.blank()
        sk.draw_base(g, oy)
        sk.eyes(g, oy, mode=mode, dx=gaze)
        if prop == 'magnifier' and sk.c_spark:
            _magnifier(sk, g, int(p.get('propX', sk.body[2] - 1)),
                       int(p.get('propY', sk.body[1])) + oy, i, n)
        out.append(g)
    return out


def _magnifier(sk, g, x, y, i, n):
    """Petite loupe qui se lève sur les dernières frames."""
    lift = round(2 * i / max(1, n - 1))
    y -= lift
    ring = sk.c_spark
    sk.hline(g, x, x + 2, y, ring)
    sk.hline(g, x, x + 2, y + 3, ring)
    sk.vline(g, x - 1, y + 1, y + 2, ring)
    sk.vline(g, x + 3, y + 1, y + 2, ring)
    sk.rect(g, x, y + 1, x + 2, y + 2, sk.c_shine or sk.c_light)
    sk.put(g, x + 4, y + 4, sk.c_ink)
    sk.put(g, x + 5, y + 5, sk.c_ink)


def bi_speech(sk, n, p, tracking):
    """La bulle de dialogue — pas le personnage.

    VS Code boucle cette animation à l'infini. La bulle est donc dessinée à sa
    taille définitive DÈS la frame 0 et n'est plus jamais redessinée en plus
    petit : seuls les trois points s'animent, et leur cycle boucle proprement
    (un seul point allumé à la fois, jamais d'état « tous allumés » final).

    `speechBubble: false` dans skin.json rend les 6 frames transparentes.
    """
    if not (sk.speech_bubble or p.get('force')):
        return [sk.blank() for _ in range(n)]
    if not sk.c_bubble:
        return [sk.blank() for _ in range(n)]

    x0, y0, x1, y1 = tuple(p.get('rect') or sk.bubble or (6, 6, 17, 15))
    dots = int(p.get('dots', 3))
    out = []
    for i in range(n):
        g = sk.blank()
        sk.rect(g, x0, y0, x1, y1, sk.c_bubble)
        sk.hline(g, x0, x1, y0, sk.c_socket)
        sk.hline(g, x0, x1, y1, sk.c_socket)
        for y in range(y0, y1 + 1):
            sk.put(g, x0, y, sk.c_socket)
            sk.put(g, x1, y, sk.c_socket)
        sk.hline(g, x0 + 1, x1 - 1, y0 + 1, sk.c_shine)
        sk.put(g, x0 + 2, y1 + 1, sk.c_socket)
        sk.put(g, x0 + 3, y1 + 1, sk.c_socket)
        sk.put(g, x0 + 2, y1 + 2, sk.c_socket)
        cy = (y0 + y1) // 2
        step = max(2, (x1 - x0) // (dots + 1))
        first = x0 + step
        for k in range(dots):
            sk.put(g, first + k * step, cy,
                   sk.c_core if i % dots == k else sk.c_shadow)
        out.append(g)
    return out


def bi_pages(sk, n, p, tracking):
    """Pages qui tournent au-dessus de la reliure.

    Prévu pour les silhouettes de type livre : une page en vol traverse le
    rectangle `rect` de droite à gauche, en se bombant au passage.
    """
    x0, y0, x1, y1 = tuple(p.get('rect') or sk.screen_rect())
    turns = max(1, int(p.get('turns', 1)))
    mode = _eye_mode(p, tracking)
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        t = ((i * turns) % n) / n
        px = x1 - t * (x1 - x0)
        bulge = round(2 * math.sin(math.pi * t))
        half = max(0, round(1.5 * math.sin(math.pi * t)))
        col = int(round(px))
        for dx in range(-half, half + 1):
            sk.vline(g, col + dx, y0 - bulge, y1, sk.c_page)
        sk.vline(g, col + half + 1, y0 - bulge, y1, sk.c_page2)
        sk.hline(g, col - half, col + half, y0 - bulge, sk.c_ink)
        sk.eyes(g, 0, mode=mode)
        out.append(g)
    return out


BUILTINS = {
    'still': bi_still,
    'blank': bi_blank,
    'idle': bi_idle,
    'float': bi_float,
    'rendering': bi_rendering,
    'clapping': bi_clapping,
    'cool': bi_cool,
    'sleep': bi_sleep,
    'waking': bi_waking,
    'typing': bi_typing,
    'love': bi_love,
    'yapping': bi_yapping,
    'search': bi_search,
    'speech': bi_speech,
    'pages': bi_pages,
}


# --------------------------------------------------------------- compilation
def build_animation(sk, key, expected, tracking):
    """Compile une entrée d'animation en une liste de `expected` grilles."""
    spec = sk.animations.get(key, DEFAULT_ANIMATIONS[key])

    if isinstance(spec, str):
        spec = {'builtin': spec}
    if isinstance(spec, list):
        spec = {'frames': spec}
    if not isinstance(spec, dict):
        raise SkinError(f"{key} : definition d'animation invalide")

    if 'frames' in spec:
        rows = spec['frames']
        frames = [_grid_from_rows(f, sk.size) for f in rows]
    else:
        name = spec.get('builtin', 'still')
        fn = BUILTINS.get(name)
        if fn is None:
            raise SkinError(
                f"{key} : primitive inconnue '{name}'. "
                f"Disponibles : {', '.join(sorted(BUILTINS))}")
        params = spec.get('params') or {}
        if spec.get('tracking') is not None:
            tracking = bool(spec['tracking'])
        frames = fn(sk, expected, params, tracking)

    if len(frames) != expected:
        raise SkinError(
            f"{key} : {len(frames)} frames au lieu de {expected} "
            f"(le nombre de frames est impose par VS Code)")
    return frames


def sheet(sk, frames):
    img = Image.new('RGBA', (sk.frame * len(frames), sk.frame), (0, 0, 0, 0))
    for i, g in enumerate(frames):
        img.paste(sk.render(g), (i * sk.frame, 0))
    return img


def build_all(sk):
    """{clé: (frames, gabarit)} pour les 12 animations."""
    out = {}
    for key, template, count, tracking in SLOTS:
        out[key] = (build_animation(sk, key, count, tracking), template)
    return out


# ----------------------------------------------------------------------- CSS
CSS_HEADER = """\
/* ------------------------------------------------------------------
   {name} — surcharges CSS des pupilles DOM

   FICHIER GENERE. Ne pas editer a la main : il est produit par
   generator/petgen.py a partir de skins/{id}/skin.json, et la CI verifie
   qu'il est a jour (une regeneration ne doit produire aucun diff).

   Sur les etats idle / rendering / clapping, VS Code superpose des pupilles
   en DOM qui suivent le curseur. Elles sont codees en dur en #191a1b et
   placees pour l'ancien personnage : il faut les repositionner et les
   recolorer.

   Conversion : 1 cellule de la grille {size}x{size} = {scale} px image = 2 px CSS.
       orbite gauche  ({lx}, {ly}) -> left: {cl}px, top: {ct}px
       orbite droite  ({rx}, {ry}) -> left: {cr}px, top: {ct}px
   ------------------------------------------------------------------ */
"""


def build_css(sk):
    """Le pet.css d'un skin, derive de palette + anchors.eyes. Source unique."""
    cell = 2  # px CSS par cellule de grille
    lx, ly = int(sk.eye_l[0]), int(sk.eye_l[1])
    rx, ry = int(sk.eye_r[0]), int(sk.eye_r[1])
    w, h = sk.eye_w * cell, sk.eye_h * cell
    core = sk.color('eyeCore')

    lines = [CSS_HEADER.format(
        name=sk.name, id=sk.id, size=sk.size, scale=sk.scale,
        lx=lx, ly=ly, rx=rx, ry=ry,
        cl=lx * cell, cr=rx * cell, ct=ly * cell)]

    lines.append(f'.chat-pet-eye        {{ top: {ly * cell}px; '
                 f'width: {w}px; height: {h}px; }}')
    lines.append(f'.chat-pet-eye.left   {{ left: {lx * cell}px; }}')
    lines.append(f'.chat-pet-eye.right  {{ left: {rx * cell}px; }}')

    # La pupille native fait 4x4 px a (2, 2) : recentrer si l'orbite differe.
    px, py = (w - 4) // 2, (h - 4) // 2
    if (px, py) != (2, 2):
        lines.append('')
        lines.append(f'.chat-pet-pupil      {{ left: {px}px; top: {py}px; }}')

    lines.append('')
    lines.append(f'/* Couleur du regard : role eyeCore de la palette. */')
    lines.append(f'.chat-pet-pupil      {{ background: {core}; }}')
    lines.append('')
    lines.append('/* Les croix affichees pendant le drag sont codees en dur en')
    lines.append('   #191a1b dans le CSS natif : sans ces deux regles, le pet a')
    lines.append('   des yeux colores sauf quand on le deplace. */')
    lines.append('.chat-pet-button.dragging .chat-pet-eye::before,')
    lines.append(f'.chat-pet-button.dragging .chat-pet-eye::after '
                 f'{{ background: {core}; }}')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------- E/S
def load_skin(target):
    """Accepte un id de skin, un dossier de skin, ou un chemin de skin.json."""
    path = target
    if not os.path.exists(path):
        path = os.path.join(SKINS_DIR, target, 'skin.json')
    elif os.path.isdir(path):
        path = os.path.join(path, 'skin.json')
    if not os.path.isfile(path):
        raise SkinError(f"skin introuvable : {target}")
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    return Skin(data, source=os.path.abspath(path))


def write_skin(sk, outdir=None):
    """Écrit les 48 PNG et le pet.css. Retourne la liste des fichiers écrits."""
    root = outdir or os.path.dirname(sk.source)
    sprites = os.path.join(root, 'sprites')
    css_dir = os.path.join(root, 'css')
    os.makedirs(sprites, exist_ok=True)
    os.makedirs(css_dir, exist_ok=True)

    written = []
    for key, (frames, template) in build_all(sk).items():
        strip = sheet(sk, frames)
        single = sk.render(frames[0])
        for variant in ('stable', 'insiders'):
            name = template.format(v=variant)
            for img, suffix in ((strip, '.spritesheet.png'), (single, '.png')):
                path = os.path.join(sprites, f'buddy-{name}{suffix}')
                img.save(path, optimize=True)
                written.append(path)

    css_path = os.path.join(css_dir, 'pet.css')
    with open(css_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(build_css(sk))
    written.append(css_path)
    return written


def all_skin_ids():
    if not os.path.isdir(SKINS_DIR):
        return []
    return sorted(
        d for d in os.listdir(SKINS_DIR)
        if os.path.isfile(os.path.join(SKINS_DIR, d, 'skin.json')))


def main(argv):
    outdir = None
    targets = []
    args = list(argv)
    while args:
        a = args.pop(0)
        if a in ('-o', '--out'):
            outdir = args.pop(0)
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            targets.append(a)

    if not targets:
        targets = all_skin_ids()
        if not targets:
            print('Aucun skin dans skins/.')
            return 1

    status = 0
    for target in targets:
        try:
            sk = load_skin(target)
            files = write_skin(sk, outdir)
        except SkinError as exc:
            print(f'ERREUR [{target}] : {exc}')
            status = 1
            continue
        pngs = sum(1 for f in files if f.endswith('.png'))
        print(f"skin '{sk.name}' ({sk.id}) : {pngs} PNG + pet.css")
        if pngs != 48:
            print(f'  ERREUR : {pngs} PNG au lieu de 48')
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
