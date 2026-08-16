#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contrôles de conformité des skins. Utilisé par la CI et à la main.

    tools/check_skins.py            # tous les skins de skins/
    tools/check_skins.py nixie

Trois familles de contrôles :

1. `skin.json` valide contre `schema/skin.schema.json` (jsonschema requis) ;
2. les 48 sprites attendus sont présents, et seulement eux ;
3. chaque PNG fait 96 de haut, une largeur multiple de 96, et chaque
   spritesheet a exactement le nombre de frames imposé par VS Code.

Sortie 0 si tout passe, 1 sinon, avec la liste des anomalies.
"""

from __future__ import annotations

import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKINS_DIR = os.path.join(REPO, 'skins')
SCHEMA_PATH = os.path.join(REPO, 'schema', 'skin.schema.json')

# Nombre de frames imposé par les tables de durées codées en dur dans le
# JavaScript de VS Code. Cf. SPRITE-SPEC.md §3.
EXPECTED = {
    'idle-{v}-96': 50,
    'idle-{v}-tracking-96': 50,
    'rendering-{v}-tracking-96': 50,
    'clapping-{v}-tracking-96': 13,
    'cool-{v}-96': 9,
    'sleep-{v}-96': 8,
    'waking-{v}-96': 8,
    'typing-{v}-96': 8,
    'love-{v}-96': 6,
    'speech-{v}-96': 6,
    'yapping-{v}-96': 5,
    'search-{v}-96': 4,
}


def expected_files():
    """Les 48 noms attendus -> nombre de frames (1 pour les frames simples)."""
    out = {}
    for template, frames in EXPECTED.items():
        for variant in ('stable', 'insiders'):
            name = template.format(v=variant)
            out[f'buddy-{name}.spritesheet.png'] = frames
            out[f'buddy-{name}.png'] = 1
    return out


def check_schema(skin_id, data, problems):
    try:
        import jsonschema
    except ImportError:
        problems.append('jsonschema absent : `pip install jsonschema`')
        return
    with open(SCHEMA_PATH, encoding='utf-8') as fh:
        schema = json.load(fh)
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        where = '/'.join(str(p) for p in error.path) or '(racine)'
        problems.append(f'schema : {where} : {error.message}')
    if data.get('id') != skin_id:
        problems.append(
            f"schema : id '{data.get('id')}' != nom du dossier '{skin_id}'")


def check_sprites(sprite_dir, problems):
    want = expected_files()
    if not os.path.isdir(sprite_dir):
        problems.append(f'dossier absent : {sprite_dir}')
        return
    found = sorted(f for f in os.listdir(sprite_dir) if f.endswith('.png'))

    missing = sorted(set(want) - set(found))
    extra = sorted(set(found) - set(want))
    for name in missing:
        problems.append(f'sprite manquant : {name}')
    for name in extra:
        problems.append(f'fichier en trop : {name}')
    if len(found) != 48 and not missing and not extra:
        problems.append(f'{len(found)} fichiers au lieu de 48')

    for name in sorted(set(found) & set(want)):
        with Image.open(os.path.join(sprite_dir, name)) as img:
            w, h = img.size
        if h != 96:
            problems.append(f'{name} : hauteur {h}, attendu 96')
        if w % 96:
            problems.append(f'{name} : largeur {w}, non multiple de 96')
            continue
        frames = w // 96
        if frames != want[name]:
            problems.append(
                f'{name} : {frames} frames, attendu {want[name]} '
                f'(impose par VS Code)')


def check_css(skin_dir, problems):
    path = os.path.join(skin_dir, 'css', 'pet.css')
    if not os.path.isfile(path):
        problems.append('css/pet.css absent (genere par generator/petgen.py)')
        return
    with open(path, encoding='utf-8') as fh:
        head = fh.read(400)
    if 'FICHIER GENERE' not in head:
        problems.append('css/pet.css : en-tete de fichier genere absent — '
                        'il a ete edite a la main ?')


def check_skin(skin_id):
    skin_dir = os.path.join(SKINS_DIR, skin_id)
    problems = []
    path = os.path.join(skin_dir, 'skin.json')
    if not os.path.isfile(path):
        return [f'{skin_id} : skin.json absent']
    with open(path, encoding='utf-8') as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            return [f'{skin_id} : skin.json illisible : {exc}']

    check_schema(skin_id, data, problems)
    check_sprites(os.path.join(skin_dir, 'sprites'), problems)
    check_css(skin_dir, problems)
    return [f'{skin_id} : {p}' for p in problems]


def all_skin_ids():
    if not os.path.isdir(SKINS_DIR):
        return []
    return sorted(d for d in os.listdir(SKINS_DIR)
                  if os.path.isfile(os.path.join(SKINS_DIR, d, 'skin.json')))


def main(argv):
    targets = argv or all_skin_ids()
    if not targets:
        print('Aucun skin dans skins/.')
        return 1
    failed = 0
    for skin_id in targets:
        problems = check_skin(skin_id)
        if problems:
            failed += 1
            for p in problems:
                print('ECHEC ' + p)
        else:
            print(f'OK    {skin_id} : schema, 48 sprites, dimensions, '
                  f'nombre de frames, pet.css')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
