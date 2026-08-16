#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relève le format des sprites du pet sur une installation de VS Code.

    tools/probe_format.py                          # trouve VS Code tout seul
    tools/probe_format.py "C:\\Program Files\\Microsoft VS Code"
    tools/probe_format.py --out schema/formats/1.134.json

Microsoft remanie le pet d'une version à l'autre : entre la 1.132 et la 1.133,
neuf états sont apparus, `typing` est passé de 8 frames à 2, et la frame a
cessé d'être carrée. Plutôt que de deviner, ce script lit l'installation et
écrit le descripteur que consomme `generator/petgen.py`.

C'est l'outil à relancer après chaque mise à jour de VS Code :

    python tools/probe_format.py --out schema/formats/<version>.json
    python generator/petgen.py
    python tools/check_skins.py

DEUX RÈGLES, apprises à la dure :

1. La taille d'une frame se lit sur le PNG **simple**, jamais en supposant
   qu'elle est carrée. `buddy-typing-stable-96.spritesheet.png` fait 336x96 ;
   en divisant par 96 on trouve 3,5 frames, ce qui n'a aucun sens. La frame
   fait 168x96 et la planche en contient 2.

2. Le suffixe du nom de fichier (`-96`, `-124`) n'est pas la largeur de la
   frame : c'est sa hauteur.

Dépendance : Pillow.
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys

from PIL import Image

PET_SUBPATH = os.path.join(
    'resources', 'app', 'out', 'vs', 'workbench', 'contrib', 'chat',
    'browser', 'widget', 'media', 'chatPet')

NAME_RE = re.compile(
    r'^buddy-(?P<state>.+?)-(?P<variant>stable|insiders)'
    r'(?P<tracking>-tracking)?-(?P<suffix>\d+)(?P<sheet>\.spritesheet)?\.png$')

CANDIDATES = [
    r'C:\Program Files\Microsoft VS Code',
    r'C:\Program Files (x86)\Microsoft VS Code',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Microsoft VS Code'),
    '/usr/share/code',
    '/Applications/Visual Studio Code.app/Contents/Resources/app/out',
]


def find_pet_dir(root=None):
    """Dossier chatPet, en traversant le dossier de build s'il y en a un."""
    roots = [root] if root else [c for c in CANDIDATES if c and os.path.isdir(c)]
    for r in roots:
        direct = os.path.join(r, PET_SUBPATH)
        if os.path.isdir(direct):
            return direct, r, None
        # Les builds récents insèrent un dossier nommé d'après le commit,
        # tronqué à 10 caractères sur les versions observées.
        try:
            subs = sorted(os.listdir(r))
        except OSError:
            continue
        for sub in subs:
            cand = os.path.join(r, sub, PET_SUBPATH)
            if os.path.isdir(cand):
                return cand, r, sub
    return None, None, None


def read_version(root, build):
    base = os.path.join(root, build) if build else root
    out = {}
    for name, key in (('package.json', 'version'), ('product.json', 'commit')):
        path = os.path.join(base, 'resources', 'app', name)
        if os.path.isfile(path):
            try:
                with open(path, encoding='utf-8') as fh:
                    out[key] = json.load(fh).get(key)
            except (OSError, ValueError):
                pass
    return out.get('version'), out.get('commit')


def probe(pet_dir):
    raw = collections.OrderedDict()
    unknown = []
    for name in sorted(os.listdir(pet_dir)):
        if not name.endswith('.png'):
            continue
        m = NAME_RE.match(name)
        if not m:
            unknown.append(name)
            continue
        if m['variant'] != 'stable':      # les deux variantes sont identiques
            continue
        key = m['state'] + ('-tracking' if m['tracking'] else '')
        with Image.open(os.path.join(pet_dir, name)) as img:
            size = img.size
        entry = raw.setdefault(key, {
            'state': m['state'], 'tracking': bool(m['tracking']),
            'suffix': int(m['suffix'])})
        entry['sheet' if m['sheet'] else 'single'] = size

    states, problems = [], []
    for key, e in sorted(raw.items()):
        if 'single' not in e:
            problems.append(f'{key} : pas de PNG simple, taille de frame indeterminable')
            continue
        fw, fh = e['single']
        sheet = e.get('sheet')
        frames = 1
        if sheet:
            if sheet[1] != fh:
                problems.append(f'{key} : hauteur de planche {sheet[1]} != frame {fh}')
            if sheet[0] % fw:
                problems.append(
                    f'{key} : largeur de planche {sheet[0]} non multiple de {fw}')
            frames = sheet[0] // fw
        if e['suffix'] != fh:
            problems.append(f'{key} : suffixe -{e["suffix"]} != hauteur {fh}')
        states.append(collections.OrderedDict([
            ('key', key), ('state', e['state']), ('tracking', e['tracking']),
            ('suffix', e['suffix']), ('frameWidth', fw), ('frameHeight', fh),
            ('frames', frames), ('spritesheet', bool(sheet)),
        ]))
    return states, problems, unknown


def main(argv):
    root, out_path = None, None
    args = list(argv)
    while args:
        a = args.pop(0)
        if a in ('-o', '--out'):
            out_path = args.pop(0)
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            root = a

    pet_dir, root, build = find_pet_dir(root)
    if not pet_dir:
        print("Installation de VS Code introuvable. Passe le chemin en argument.")
        return 1
    version, commit = read_version(root, build)

    states, problems, unknown = probe(pet_dir)
    files = sum(4 if s['spritesheet'] else 2 for s in states)

    print(f'racine  : {root}')
    print(f'build   : {build or "(pas de dossier de build)"}')
    print(f'version : {version or "?"}   commit : {commit or "?"}')
    print(f'releve  : {len(states)} etats, {files} fichiers')
    for s in states:
        odd = []
        if (s['frameWidth'], s['frameHeight']) != (96, 96):
            odd.append(f"frame {s['frameWidth']}x{s['frameHeight']}")
        if not s['spritesheet']:
            odd.append('pas de spritesheet')
        if odd:
            print(f"   {s['key']:20s} {s['frames']:3d} frames   " + ', '.join(odd))
    for u in unknown:
        print(f'   NOM NON RECONNU : {u}')
    for p in problems:
        print(f'   ANOMALIE : {p}')

    doc = collections.OrderedDict([
        ('$schema', '../format.schema.json'),
        ('id', version or 'inconnu'),
        ('vscode', [version] if version else []),
        ('commit', commit),
        ('description', f'Relevé par tools/probe_format.py sur {root}.'),
        ('states', states),
    ])
    text = json.dumps(doc, ensure_ascii=False, indent=2) + '\n'
    if out_path:
        with open(out_path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        print(f'\necrit dans {out_path}')
    else:
        print('\n(--out <fichier> pour ecrire le descripteur)')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
