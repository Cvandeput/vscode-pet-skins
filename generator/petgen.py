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
    generator/petgen.py --format 1.133  # autre descripteur de format

La liste des états, le nombre de frames et la géométrie de chaque frame ne
sont PAS codés ici : ils viennent de `schema/formats/<id>.json`, relevé sur une
installation réelle par `tools/probe_format.py`. En 1.133 : 21 états, 82
fichiers, et la frame n'est plus carrée sur les états à accessoire.

Pour chaque skin, la sortie est reproductible au bit près :

    skins/<id>/sprites/buddy-*.png      les 82 fichiers attendus par VS Code
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
FORMATS_DIR = os.path.join(REPO, 'schema', 'formats')
DEFAULT_FORMAT = '1.133'


class SkinError(Exception):
    """Erreur de définition d'un skin, remontée avec un message lisible."""


# -------------------------------------------------------------------- format
# Le descripteur `schema/formats/<id>.json` est la source de vérité : liste des
# états, nombre de frames (imposé par des tables de durées codées en dur dans
# le JavaScript de VS Code), et géométrie de chaque frame.
#
# Nom de fichier : buddy-<state>-<variant>[-tracking]-<suffix>[.spritesheet].png
# Le suffixe est la HAUTEUR de la frame, pas sa largeur.
def _state_entry(state, path):
    for field in ('key', 'state', 'suffix', 'frameWidth', 'frameHeight', 'frames'):
        if field not in state:
            raise SkinError(f"{path} : champ `{field}` manquant sur un etat")
    tracking = bool(state.get('tracking'))
    name = (f"{state['state']}-{{v}}"
            + ('-tracking' if tracking else '')
            + f"-{int(state['suffix'])}")
    return {
        'key': str(state['key']),
        'state': str(state['state']),
        'tracking': tracking,
        'template': name,
        'frame_w': int(state['frameWidth']),
        'frame_h': int(state['frameHeight']),
        'frames': int(state['frames']),
        'spritesheet': bool(state.get('spritesheet', True)),
    }


def load_format(spec=None):
    """Charge un descripteur : un id (`1.133`) ou un chemin de fichier."""
    spec = spec or DEFAULT_FORMAT
    path = spec if os.path.isfile(spec) else os.path.join(
        FORMATS_DIR, f'{spec}.json')
    if not os.path.isfile(path):
        raise SkinError(
            f"format introuvable : {spec} (ni un fichier, ni un descripteur de "
            f"{os.path.relpath(FORMATS_DIR, REPO)})")
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    states = data.get('states') or []
    if not states:
        raise SkinError(f"{path} : aucun etat dans le descripteur")
    entries = [_state_entry(s, path) for s in states]
    seen = set()
    for e in entries:
        if e['key'] in seen:
            raise SkinError(f"{path} : etat '{e['key']}' en double")
        seen.add(e['key'])
    return {'id': data.get('id') or str(spec), 'path': path, 'states': entries}


# Animation par défaut de chaque état, quand `skin.json` n'en dit rien.
DEFAULT_ANIMATIONS = {
    'idle':               {'builtin': 'idle'},
    'idle-tracking':      {'builtin': 'idle'},
    'rendering-tracking': {'builtin': 'rendering'},
    'clapping-tracking':  {'builtin': 'clapping'},
    'cool':               {'builtin': 'cool'},
    'sleep':              {'builtin': 'sleep'},
    'waking':             {'builtin': 'waking'},
    'typing':             {'builtin': 'typing', 'params': {'prop': 'screen'}},
    'love':               {'builtin': 'love'},
    'speech':             {'builtin': 'speech'},
    'yapping':            {'builtin': 'yapping'},
    'search':             {'builtin': 'search'},
    'falling':            {'builtin': 'falling'},
    'jump':               {'builtin': 'jump'},
    'press-button':       {'builtin': 'press-button'},
    'respawn':            {'builtin': 'respawn'},
    'revive-sign':        {'builtin': 'revive-sign'},
    'sing':               {'builtin': 'sing'},
    'speechless':         {'builtin': 'speechless'},
    'splat':              {'builtin': 'splat'},
    'worry':              {'builtin': 'worry'},
}


# ------------------------------------------------------------------ outillage
def _hexa(value):
    h = str(value).lstrip('#')
    if len(h) not in (6, 8):
        raise SkinError(f"couleur invalide : {value!r}")
    rgba = tuple(int(h[i:i + 2], 16) for i in range(0, len(h), 2))
    return rgba if len(rgba) == 4 else rgba + (255,)


def _grid_from_rows(rows, width, height=None):
    """Normalise une liste de chaînes en grille height x width."""
    height = width if height is None else height
    out = [list(str(r).ljust(width, '.')[:width]) for r in rows[:height]]
    while len(out) < height:
        out.append(['.'] * width)
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

    def __init__(self, data, source=None, fmt=None):
        self.data = data
        self.source = source
        self.id = data.get('id') or (
            os.path.basename(os.path.dirname(source)) if source else 'skin')
        self.name = data.get('name', self.id)

        self.size = int(data.get('grid', 24))
        self.scale = int(data.get('scale', 4))
        if self.size < 1 or self.scale < 1:
            raise SkinError('`grid` et `scale` doivent etre >= 1')

        # Ce n'est plus le skin qui impose la taille de frame, c'est le format.
        # On vérifie seulement que la grille du skin sait la pavér.
        self.format = fmt or load_format()
        self.check_format()

        # Canvas courant : le compilateur d'animation le règle par état, car la
        # frame n'est plus carrée (`typing` 168x96, `sing` 164x124...).
        self.reset_canvas()

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

    # ------------------------------------------------------------- géométrie
    def check_format(self):
        """Chaque frame du format doit être pavable par la grille du skin."""
        self.frame = self.size * self.scale
        for e in self.format['states']:
            for label, px in (('largeur', e['frame_w']), ('hauteur', e['frame_h'])):
                if px % self.scale:
                    raise SkinError(
                        f"etat '{e['key']}' : {label} de frame {px} px non "
                        f"divisible par scale={self.scale} "
                        f"(format {self.format['id']})")
            cols, rows = e['frame_w'] // self.scale, e['frame_h'] // self.scale
            if cols < self.size or rows < self.size:
                raise SkinError(
                    f"etat '{e['key']}' : frame {cols}x{rows} cellules plus "
                    f"petite que la grille du personnage {self.size}x{self.size} "
                    f"(baisse `grid`, ou augmente `scale`)")

    def set_canvas(self, cols, rows):
        """Règle la géométrie du canvas courant, en cellules."""
        self.cols, self.rows = int(cols), int(rows)
        # Le personnage garde sa grille logique size x size, ancrée en bas à
        # gauche. `put()` applique le décalage, donc toutes les primitives en
        # héritent sans être retouchées.
        self.head_room = self.rows - self.size     # marge ajoutée en haut
        self.prop_x0 = self.size                   # début de la zone accessoire
        return self

    def reset_canvas(self):
        return self.set_canvas(self.size, self.size)

    def canvas_for(self, entry):
        return self.set_canvas(entry['frame_w'] // self.scale,
                               entry['frame_h'] // self.scale)

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
        return [['.'] * self.cols for _ in range(self.rows)]

    def put(self, g, x, y, c):
        """Écrit en « espace personnage » : (0, 0) = coin haut-gauche du pet.

        Le pet est ancré en bas à gauche du canvas. Un `y` négatif vise donc la
        marge du haut (cas de `sing`), un `x >= prop_x0` la zone accessoire.
        """
        if not c:
            return
        ty = int(y) + self.head_room
        x = int(x)
        if 0 <= x < self.cols and 0 <= ty < self.rows:
            g[ty][x] = c

    def at(self, g, x, y):
        """Lit une cellule en espace personnage, '.' hors canvas."""
        ty = int(y) + self.head_room
        x = int(x)
        if 0 <= x < self.cols and 0 <= ty < self.rows:
            return g[ty][x]
        return '.'

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
        img = Image.new('RGBA', (self.cols, self.rows), (0, 0, 0, 0))
        px = img.load()
        for y in range(self.rows):
            for x in range(self.cols):
                col = self.palette.get(g[y][x])
                if col:
                    px[x, y] = col
        return img.resize((self.cols * self.scale, self.rows * self.scale),
                          Image.NEAREST)

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
                  squeeze=0, screen_off=False, ox=0, lean=0.0):
        """Pose la grille de base.

        oy         décalage vertical global
        ox         décalage horizontal global (tremblement, recul)
        feet       levée de chaque zone de `anchors.feet` (ignoré si vide)
        wave       ondulation horizontale du bas du corps, cf. wave_at
        squeeze    tassement vertical, bas ancré
        lean       inclinaison : le haut du corps part de `lean` cellules,
                   le bas ne bouge pas (piqué du nez de `falling`)
        flicker    la dalle passe en couleur `screenFlicker`
        screen_off la dalle passe en couleur `screenOff`
        """
        ymap = self._squeeze_map(squeeze)
        by0, by1 = int(self.body[1]), int(self.body[3])
        span = max(1, by1 - by0)
        for y in range(self.size):
            ty = ymap[y]
            if ty is None:
                continue
            for x in range(self.size):
                c = self.base[y][x]
                if c == '.':
                    continue
                dx = ox
                if lean:
                    dx += int(round(lean * max(0, by1 - y) / span))
                if wave and y >= int(wave.get('from', self.size)):
                    depth = y - int(wave.get('from', self.size))
                    period = max(1, int(wave.get('period', 6)))
                    dx += int(round(float(wave.get('amp', 1)) * math.sin(
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
            # Passe par at()/put() : sinon l'écriture rate la cible dès que le
            # canvas est plus haut que la grille du personnage.
            x0, y0, x1, y1 = self.screen_rect()
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if self.at(g, x + ox, y + oy) == self.c_screen:
                        self.put(g, x + ox, y + oy, self.c_flick)

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

    def eyes(self, g, oy, mode='open', dx=0, dy=0, squash=False, squeeze=0,
             ox=0):
        """mode : open | closed | dim | hearts | narrow | none

        `squeeze` doit reprendre la valeur passée à `draw_base` : les orbites
        suivent alors le tassement du corps au lieu de rester en l'air.
        `ox` doit reprendre le décalage horizontal (`ox` / `lean`) du corps.
        """
        oy += self.squeeze_shift(squeeze)
        for ex in (e + int(ox) for e in self.eye_x):
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

    En 1.133 la frame fait 168 px de large : `prop` (par défaut `screen`)
    remplit la moitié droite, sinon elle resterait vide.
    """
    gaze = _resample(p.get('gaze', [-1, 0, 1, 1, 0, -1, 0, 0]), n)
    blinks = max(1, int(p.get('cursorBlinks', 1)))
    x0, _, _, y1 = tuple(p.get('rect') or sk.screen_rect())
    cx = int(p.get('cursorX', x0 + 1))
    cy = int(p.get('cursorY', y1 - 1))
    width = max(1, int(p.get('cursorWidth', 2)))
    mode = _eye_mode(p, tracking)
    prop = p.get('prop', 'screen')
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode=mode, dx=gaze[i])
        if ((i * 2 * blinks) // n) % 2 == 0:
            sk.hline(g, cx, cx + width - 1, cy, sk.c_core)
        draw_prop(sk, g, prop, i, n, p)
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
    prop = p.get('prop')
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        draw_prop(sk, g, prop, i, n, p)
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


# ---------------------------------------------------------------- accessoires
# Depuis 1.133, trois états ont une frame plus large que le personnage : le pet
# est dessiné à gauche, et la largeur en trop accueille un accessoire.
# `Skin.prop_x0` marque le début de cette zone ; sur une frame carrée elle est
# vide, et les accessoires qui ont besoin de place s'abstiennent plutôt que de
# déborder sur le pet.

def prop_zone(sk, p, margin=1, need=6):
    """(x0, x1) utilisables par un accessoire, ou None si la frame est carrée."""
    x0 = int(p.get('propX0', sk.prop_x0 + margin))
    x1 = int(p.get('propX1', sk.cols - 1 - margin))
    if x0 < sk.prop_x0 or x1 - x0 + 1 < need:
        return None
    return x0, x1


def _prop_colors(sk):
    """(cadre, dalle, texte) — chaque terme peut être None."""
    return (sk.c_out or sk.c_socket,
            sk.c_screen or sk.c_shadow or sk.c_socket,
            sk.c_spark or sk.c_light or sk.c_core)


def _p_screen(sk, g, i, n, p):
    """Un écran sur pied, avec du texte qui s'écrit, et un clavier."""
    zone = prop_zone(sk, p, need=10)
    if not zone:
        return
    x0, x1 = zone
    edge, face, text = _prop_colors(sk)
    if not (edge or face):
        return
    y0 = int(p.get('propY0', 2))
    y1 = int(p.get('propY1', 14))
    cx = (x0 + x1) // 2
    sk.rect(g, x0, y0, x1, y1, edge or face)
    sk.rect(g, x0 + 1, y0 + 1, x1 - 1, y1 - 1, face or edge)

    # lignes de code : la dernière s'allonge d'une frame à l'autre
    lengths = [x1 - x0 - 4, x1 - x0 - 7, x1 - x0 - 3, x1 - x0 - 9]
    for k, length in enumerate(lengths):
        ly = y0 + 2 + 2 * k
        if ly > y1 - 2:
            break
        if k == len(lengths) - 1:
            length = max(1, length - 2 + 2 * (i % 2))
        sk.hline(g, x0 + 2, x0 + 2 + max(1, length), ly, text)
    # curseur, en phase avec le clignotement du pet
    cur_y = y0 + 2 + 2 * (len(lengths) - 1)
    if i % 2 == 0 and cur_y <= y1 - 2:
        sk.vline(g, x1 - 2, cur_y - 1, cur_y + 1, sk.c_core)

    # pied et socle
    sk.vline(g, cx, y1 + 1, y1 + 3, edge or face)
    sk.vline(g, cx + 1, y1 + 1, y1 + 3, edge or face)
    sk.hline(g, cx - 3, cx + 4, y1 + 4, edge or face)

    # clavier posé au sol
    ky = sk.size - 3
    sk.rect(g, x0, ky, x1, ky + 2, edge or face)
    sk.hline(g, x0, x1, ky, face or edge)
    for x in range(x0 + 1, x1, 2):
        sk.put(g, x, ky + 1, text)


def _button_geom(sk, p):
    zone = prop_zone(sk, p, need=9)
    if not zone:
        return None
    x0, x1 = zone
    return ((x0 + x1) // 2, int(p.get('propY0', 12)),
            int(p.get('propY1', sk.size - 2)))


def _p_button(sk, g, i, n, p, pressed=False):
    """Un gros bouton sur socle. `pressed` enfonce le champignon de 2 cases."""
    geom = _button_geom(sk, p)
    if not geom:
        return
    cx, _, base = geom
    edge, face, text = _prop_colors(sk)
    cap = sk.c_heart or sk.c_core
    rim = base - 5
    sk.rect(g, cx - 5, rim + 1, cx + 5, base, edge or face)
    sk.rect(g, cx - 4, rim + 2, cx + 4, base - 1, face or edge)
    sk.hline(g, cx - 6, cx + 6, rim, edge or face)
    top = rim - 2 if pressed else rim - 5
    sk.rect(g, cx - 4, top, cx + 4, rim - 1, cap)
    sk.hline(g, cx - 3, cx + 3, top, sk.c_light or cap)
    sk.vline(g, cx - 5, top + 1, rim - 1, edge or cap)
    sk.vline(g, cx + 5, top + 1, rim - 1, edge or cap)
    if pressed and text:
        # petit choc a l'impact
        sk.put(g, cx - 7, top - 2, text)
        sk.put(g, cx + 7, top - 2, text)
        sk.put(g, cx - 6, top - 3, text)
        sk.put(g, cx + 6, top - 3, text)
    return top


def _note(sk, g, x, y, c):
    """Croche : tête de 3x2, hampe de 5, drapeau. 6x6 cellules."""
    sk.rect(g, x, y + 4, x + 2, y + 5, c)
    sk.vline(g, x + 3, y, y + 4, c)
    sk.hline(g, x + 3, x + 4, y, c)
    sk.put(g, x + 4, y + 1, c)
    sk.put(g, x + 5, y + 2, c)


def _p_notes(sk, g, i, n, p):
    """Des notes qui montent dans la marge — `sing` a aussi de la place en haut."""
    zone = prop_zone(sk, p, need=8)
    if not zone:
        return
    x0, x1 = zone
    # `spark` est souvent quasi blanc : les notes prennent d'abord un accent
    # coloré, sinon elles disparaissent sur un thème clair.
    tones = [c for c in (sk.c_heart, sk.c_halo2, sk.c_spark, sk.c_core) if c]
    if not tones:
        return
    for k in range(3):
        y = int(p.get('propY0', 14)) - 6 * k - 3 * i
        if y + 5 < -sk.head_room:
            continue
        x = min(x1 - 5, x0 + 4 * k + (i + k) % 2)
        _note(sk, g, x, y, tones[k % len(tones)])


def _p_sign(sk, g, i, n, p):
    """Une pancarte tenue devant soi : croix de réanimation et manche."""
    fill = sk.c_page or sk.c_bubble or sk.c_screen or sk.c_shadow
    edge = sk.c_out or sk.c_socket
    ink = sk.c_ink or sk.c_out or sk.c_socket
    mark = sk.c_heart or sk.c_core
    if not (fill or edge):
        return
    zone = prop_zone(sk, p, need=10)
    if zone:
        x0, x1 = zone
        y1 = int(p.get('propY1', sk.eye_y + 2))
    else:
        bx0, _, bx1, _ = (int(v) for v in sk.body)
        cx = (bx0 + bx1) // 2
        half = int(p.get('signHalf', 6))
        x0, x1 = cx - half, cx + half
        y1 = int(p.get('propY1', max(7, sk.eye_y - 2)))
    y0 = y1 - int(p.get('signHeight', 8)) + 1
    cx = (x0 + x1) // 2

    sk.rect(g, x0, y0, x1, y1, edge or fill)
    sk.rect(g, x0 + 1, y0 + 1, x1 - 1, y1 - 1, fill or edge)
    # croix : lisible même réduite à 48 px. Le bras horizontal est centré sur
    # le bras vertical (y0+2 .. y1-2), pas sur la planche : sinon on lit un T.
    mid = (y0 + y1) // 2
    sk.rect(g, cx - 1, y0 + 1, cx, y1 - 1, mark or ink)
    sk.rect(g, cx - 3, mid, cx + 3, mid + 1, mark or ink)
    # manche + mains
    sk.vline(g, cx - 1, y1 + 1, y1 + 3, edge or ink)
    sk.vline(g, cx, y1 + 1, y1 + 3, edge or ink)
    if sk.c_light:
        sk.put(g, cx - 2, y1 + 2, sk.c_light)
        sk.put(g, cx + 1, y1 + 2, sk.c_light)


PROPS = {
    'screen': _p_screen,
    'button': _p_button,
    'notes': _p_notes,
    'sign': _p_sign,
}


def draw_prop(sk, g, kind, i, n, p):
    """Pose l'accessoire `kind` ; inconnu ou absent => rien, sans erreur."""
    fn = PROPS.get(kind) if kind else None
    if fn:
        fn(sk, g, i, n, p)


# ------------------------------------------------------ primitives 1.133
def _lean_at(sk, lean, y):
    """Décalage horizontal subi par la ligne `y` sous une inclinaison."""
    by0, by1 = int(sk.body[1]), int(sk.body[3])
    return int(round(lean * max(0, by1 - y) / max(1, by1 - by0)))


def _accent(sk):
    """Couleur des petits signes : gouttes, points, lignes de vitesse.

    `spark` vaut souvent un quasi-blanc (vapor, codex) qui disparaît sur un
    thème clair ; `haloStrong` est un accent teinté, lisible sur les deux.
    """
    return sk.c_halo2 or sk.c_spark or sk.c_light or sk.c_core


def _drop(sk, g, x, y):
    """Goutte de sueur / larme, cernée pour tenir sur n'importe quel fond."""
    c = _accent(sk)
    edge = sk.c_shine or sk.c_light or sk.c_core
    if not c:
        return
    sk.put(g, x, y, edge or c)
    sk.put(g, x, y + 1, c)
    sk.put(g, x + 1, y + 1, c)
    sk.put(g, x, y + 2, c)


def bi_falling(sk, n, p, tracking):
    """Chute : le pet pique du nez, des lignes de vitesse filent au-dessus."""
    lean = _resample(p.get('lean', [0, 1, 2, 3]), n)
    drop = _resample(p.get('drop', [0, 1, 1, 2]), n)
    mode = _eye_mode(p, tracking)
    # deux teintes en alternance : l'une porte sur fond clair, l'autre sur fond
    # sombre, et le pet peut se retrouver sur les deux
    streaks = [c for c in (_accent(sk), sk.c_spark) if c] or [sk.c_core]
    bx0, by0, bx1, _ = (int(v) for v in sk.body)
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, drop[i], lean=lean[i])
        sk.eyes(g, drop[i], mode=mode, ox=_lean_at(sk, lean[i], sk.eye_y), dy=1)
        # lignes de vitesse : uniquement dans les rangees libres au-dessus
        free = by0 + drop[i]
        for k in range(min(4, free)):
            y = free - 1 - k
            for x in range(bx0 + (i + k) % 4, bx1 + 1, 4):
                sk.put(g, x, y, streaks[k % len(streaks)])
        out.append(g)
    return out


def bi_jump(sk, n, p, tracking):
    """Accroupi, détente, sommet, maintien, descente, réception."""
    offsets = _resample(p.get('offsets', [1, -1, -2, -2, -1, 1]), n)
    squeeze = _resample(p.get('squeeze', [2, 0, 0, 0, 0, 1]), n)
    lift = _resample(p.get('feet', [0, -1, -2, -2, -1, 0]), n)
    mode = _eye_mode(p, tracking)
    bx0, _, bx1, _ = (int(v) for v in sk.body)
    cx, ground = (bx0 + bx1) // 2, sk.size - 1
    peak = min(offsets)
    out = []
    for i in range(n):
        g = sk.blank()
        feet = (lift[i], lift[i]) if sk.feet else (0, 0)
        sk.draw_base(g, offsets[i], squeeze=squeeze[i], feet=feet)
        sk.eyes(g, offsets[i], mode=mode, squeeze=squeeze[i],
                dy=-1 if offsets[i] < 0 else 0)
        if sk.c_shadow and p.get('shadow', bool(sk.feet)):
            # l'ombre au sol retrecit avec l'altitude : sans elle, la detente
            # ne se lit pas sur une planche de frames arretees
            t = 0.0 if peak >= 0 else max(0.0, min(1.0, offsets[i] / peak))
            half = max(2, int(round((bx1 - bx0 + 1) / 2 * (1 - 0.5 * t))))
            sk.hline(g, cx - half, cx + half, ground, sk.c_shadow)
        out.append(g)
    return out


def bi_press_button(sk, n, p, tracking):
    """Frame large : un bouton à droite, le pet tend le bras et l'enfonce."""
    mode = _eye_mode(p, tracking)
    reach = _resample(p.get('reach', [0.0, 0.35, 0.7, 1.0, 1.0, 1.0]), n)
    press_from = int(p.get('pressFrom', max(1, n - 2)))
    arm = sk.c_out or sk.c_socket
    hand = sk.c_light or sk.c_core
    bx1 = int(sk.body[2])
    out = []
    for i in range(n):
        g = sk.blank()
        pressed = i >= press_from
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode=mode, dx=1)
        top = _p_button(sk, g, i, n, p, pressed=pressed)
        if top is None:
            out.append(g)
            continue
        geom = _button_geom(sk, p)
        target = geom[0] - 5
        start = bx1 + 1
        arm_y = top + 1
        end = start + int(round(float(reach[i]) * (target - start)))
        sk.hline(g, start, end, arm_y, arm)
        sk.hline(g, start, end, arm_y + 1, arm)
        sk.rect(g, end - 1, arm_y, end, arm_y + 1, hand)
        out.append(g)
    return out


def bi_respawn(sk, n, p, tracking):
    """Matérialisation : le corps se recompose, le regard se rallume."""
    eye_seq = _resample(
        p.get('eyeSeq', ['none', 'none', 'dim', 'dim', 'open', 'open']), n)
    # densité sur 16 : 16 = corps plein. Le trouage est uniforme, pas couplé à
    # la profondeur comme celui de `wave.fade` — sinon seul le bas se dissout
    # et l'effet se lit comme une avarie, pas comme une apparition.
    dens = _resample(p.get('materialize', [3, 6, 9, 12, 15, 16]), n)
    bx0, by0, bx1, by1 = (int(v) for v in sk.body)
    cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode='none' if tracking else eye_seq[i])
        d = int(dens[i])
        if d < 16:
            for y in range(sk.rows):
                for x in range(sk.cols):
                    if g[y][x] != '.' and (x * 7 + y * 13 + i * 5) % 16 >= d:
                        g[y][x] = '.'
        if sk.c_spark and i < n - 1:
            r = 2 + (n - 1 - i)
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                sk.put(g, cx + dx * r, cy + dy * (r // 2 + 1), sk.c_spark)
        out.append(g)
    return out


def bi_revive_sign(sk, n, p, tracking):
    """Image fixe : le pet à terre, une pancarte tenue devant lui."""
    mode = 'none' if tracking else p.get('eyes', 'dim')
    oy = int(p.get('offset', 0))
    squeeze = int(p.get('squeeze', 0))
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, oy, squeeze=squeeze)
        sk.eyes(g, oy, mode=mode, squeeze=squeeze)
        draw_prop(sk, g, p.get('prop', 'sign'), i, n, p)
        out.append(g)
    return out


def bi_sing(sk, n, p, tracking):
    """Frame large et haute : bouche ouverte, notes qui montent dans la marge."""
    widths = _resample(p.get('widths', [3, 6, 4, 7]), n)
    bob = _resample(p.get('bob', [0, -1, 0, -1]), n)
    mode = 'none' if tracking else p.get('eyes', 'narrow')
    cx, my = sk.mouth_pos()
    out = []
    for i in range(n):
        g = sk.blank()
        oy = int(bob[i])
        sk.draw_base(g, oy)
        sk.eyes(g, oy, mode=mode)
        w = max(2, int(widths[i]))
        x0, x1 = cx - w // 2, cx + w // 2
        sk.rect(g, x0, my - 1 + oy, x1, my + 1 + oy, sk.c_core)
        if w >= 4 and sk.c_dark:
            sk.rect(g, x0 + 1, my + oy, x1 - 1, my + oy, sk.c_dark)
        draw_prop(sk, g, p.get('prop', 'notes'), i, n, p)
        out.append(g)
    return out


def bi_speechless(sk, n, p, tracking):
    """Regard vide, points de suspension, une goutte qui glisse."""
    mode = 'none' if tracking else p.get('eyes', 'dim')
    dots = _resample(p.get('dots', [0, 1, 2, 3, 3]), n)
    bx0, by0, bx1, _ = (int(v) for v in sk.body)
    cx = (bx0 + bx1) // 2
    tone = _accent(sk)
    out = []
    for i in range(n):
        g = sk.blank()
        sk.draw_base(g, 0)
        sk.eyes(g, 0, mode=mode)
        # au-dessus du corps par défaut ; une silhouette qui occupe déjà toute
        # la hauteur (vapor) déplace les points avec dotsX / dotsY
        dx0 = int(p.get('dotsX', cx - 3))
        dy = int(p.get('dotsY', max(0, by0 - 2)))
        for k in range(int(dots[i])):
            sk.put(g, dx0 + 3 * k, dy, tone)
        _drop(sk, g, bx1 + 1, sk.eye_y + i)
        out.append(g)
    return out


def bi_splat(sk, n, p, tracking):
    """Le pet s'écrase progressivement — `squeeze` de draw_base fait le travail."""
    body_h = max(2, int(sk.body[3]) - int(sk.body[1]))
    default = [max(1, round(body_h * f)) for f in (0.10, 0.25, 0.40, 0.50)]
    squeeze = _resample(p.get('squeeze', default), n)
    mode = _eye_mode(p, tracking)
    bx0, _, bx1, _ = (int(v) for v in sk.body)
    out = []
    for i in range(n):
        g = sk.blank()
        s = int(squeeze[i])
        sk.draw_base(g, 0, squeeze=s)
        sk.eyes(g, 0, mode=mode, squeeze=s, squash=(i >= n // 2))
        if sk.c_spark:
            spread = 1 + i
            sk.put(g, bx0 - spread, sk.size - 1, sk.c_spark)
            sk.put(g, bx1 + spread, sk.size - 1, sk.c_spark)
            if i:
                sk.put(g, bx0 - spread, sk.size - 2, sk.c_spark)
                sk.put(g, bx1 + spread, sk.size - 2, sk.c_spark)
        out.append(g)
    return out


def bi_worry(sk, n, p, tracking):
    """Tremblement nerveux, regard inquiet, goutte de sueur."""
    shake = _resample(p.get('shake', [-1, 1]), n)
    mode = 'none' if tracking else p.get('eyes', 'open')
    tone = _accent(sk)
    bx1 = int(sk.body[2])
    out = []
    for i in range(n):
        g = sk.blank()
        ox = int(shake[i])
        sk.draw_base(g, 0, ox=ox)
        sk.eyes(g, 0, mode=mode, ox=ox, dy=1)
        # traits de nervosite au-dessus des orbites exterieures
        for k, ex in enumerate(sk.eye_x):
            x = ex + ox + (-1 if k == 0 else sk.eye_w)
            sk.put(g, x, sk.eye_y - 1, tone)
            sk.put(g, x + (-1 if k == 0 else 1), sk.eye_y - 2, tone)
        _drop(sk, g, bx1 + 1 + ox, sk.eye_y + 1 + i)
        out.append(g)
    return out


BUILTINS = {
    'still': bi_still,
    'falling': bi_falling,
    'jump': bi_jump,
    'press-button': bi_press_button,
    'respawn': bi_respawn,
    'revive-sign': bi_revive_sign,
    'sing': bi_sing,
    'speechless': bi_speechless,
    'splat': bi_splat,
    'worry': bi_worry,
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
    """Compile une entrée d'animation en une liste de `expected` grilles.

    Le canvas courant du skin doit déjà être réglé (`Skin.set_canvas`).
    """
    spec = sk.animations.get(key, DEFAULT_ANIMATIONS.get(key, {'builtin': 'still'}))

    if isinstance(spec, str):
        spec = {'builtin': spec}
    if isinstance(spec, list):
        spec = {'frames': spec}
    if not isinstance(spec, dict):
        raise SkinError(f"{key} : definition d'animation invalide")

    if 'frames' in spec:
        rows = spec['frames']
        frames = [_grid_from_rows(f, sk.cols, sk.rows) for f in rows]
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


def sheet(entry):
    """Planche horizontale : largeur = frameWidth x frames, hauteur = frameHeight."""
    images = entry['images']
    w, h = entry['frame_w'], entry['frame_h']
    img = Image.new('RGBA', (w * len(images), h), (0, 0, 0, 0))
    for i, im in enumerate(images):
        img.paste(im, (i * w, 0))
    return img


def build_all(sk):
    """{clé: entrée} pour tous les états du format.

    Chaque entrée reprend le descripteur et ajoute `grids` et `images`. Les
    images sont rendues tout de suite, tant que le canvas de l'état est réglé.
    """
    out = {}
    for e in sk.format['states']:
        sk.canvas_for(e)
        grids = build_animation(sk, e['key'], e['frames'], e['tracking'])
        entry = dict(e)
        entry['cols'], entry['rows'] = sk.cols, sk.rows
        entry['grids'] = grids
        entry['images'] = [sk.render(g) for g in grids]
        out[e['key']] = entry
    sk.reset_canvas()
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
def load_skin(target, fmt=None):
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
    return Skin(data, source=os.path.abspath(path), fmt=fmt)


def write_skin(sk, outdir=None):
    """Écrit les PNG du format et le pet.css. Retourne les fichiers écrits."""
    root = outdir or os.path.dirname(sk.source)
    sprites = os.path.join(root, 'sprites')
    css_dir = os.path.join(root, 'css')
    os.makedirs(sprites, exist_ok=True)
    os.makedirs(css_dir, exist_ok=True)

    written = []
    for entry in build_all(sk).values():
        # la frame simple reste la frame 0 ; sans planche, c'est le seul fichier
        images = [(entry['images'][0], '.png')]
        if entry['spritesheet']:
            images.append((sheet(entry), '.spritesheet.png'))
        for variant in ('stable', 'insiders'):
            name = entry['template'].format(v=variant)
            for img, suffix in images:
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
    fmt_spec = None
    targets = []
    args = list(argv)
    while args:
        a = args.pop(0)
        if a in ('-o', '--out'):
            outdir = args.pop(0)
        elif a in ('-f', '--format'):
            fmt_spec = args.pop(0)
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            targets.append(a)

    try:
        fmt = load_format(fmt_spec)
    except SkinError as exc:
        print(f'ERREUR : {exc}')
        return 1
    expected = sum(4 if s['spritesheet'] else 2 for s in fmt['states'])

    if not targets:
        targets = all_skin_ids()
        if not targets:
            print('Aucun skin dans skins/.')
            return 1

    print(f"format {fmt['id']} : {len(fmt['states'])} etats, "
          f"{expected} fichiers attendus")
    status = 0
    for target in targets:
        try:
            sk = load_skin(target, fmt=fmt)
            files = write_skin(sk, outdir)
        except SkinError as exc:
            print(f'ERREUR [{target}] : {exc}')
            status = 1
            continue
        pngs = sum(1 for f in files if f.endswith('.png'))
        print(f"skin '{sk.name}' ({sk.id}) : {pngs} PNG + pet.css")
        if pngs != expected:
            print(f'  ERREUR : {pngs} PNG au lieu de {expected}')
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
