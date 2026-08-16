#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contrôles de conformité des skins. Utilisé par la CI et à la main.

    tools/check_skins.py            # tous les skins de skins/
    tools/check_skins.py nixie

Trois familles de contrôles :

1. `skin.json` valide contre `schema/skin.schema.json` (jsonschema requis) ;
2. les sprites attendus sont présents, et seulement eux ;
3. chaque PNG a exactement la taille annoncée par le descripteur de format
   — la frame n'est pas carrée partout, et chaque spritesheet vaut
   largeur_frame x nombre_de_frames.

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

# Le format n'est pas une constante : il change d'une version de VS Code a
# l'autre (48 fichiers et frames carrees en 1.132, 82 fichiers et frames
# rectangulaires en 1.133). Il est releve dans schema/formats/<id>.json par
# tools/probe_format.py, et c'est cette description qui fait foi ici.
FORMATS_DIR = os.path.join(REPO, 'schema', 'formats')
DEFAULT_FORMAT = '1.133'


def load_format(fmt=DEFAULT_FORMAT):
    path = fmt if os.path.isfile(fmt) else os.path.join(FORMATS_DIR, f'{fmt}.json')
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def expected_files(fmt):
    """{nom de fichier: (largeur, hauteur)} pour tout le jeu attendu."""
    out = {}
    for st in fmt['states']:
        tracking = '-tracking' if st['tracking'] else ''
        for variant in ('stable', 'insiders'):
            stem = f"buddy-{st['state']}-{variant}{tracking}-{st['suffix']}"
            out[stem + '.png'] = (st['frameWidth'], st['frameHeight'])
            if st['spritesheet']:
                out[stem + '.spritesheet.png'] = (
                    st['frameWidth'] * st['frames'], st['frameHeight'])
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


def check_sprites(sprite_dir, fmt, problems):
    want = expected_files(fmt)
    if not os.path.isdir(sprite_dir):
        problems.append(f'dossier absent : {sprite_dir}')
        return
    found = sorted(f for f in os.listdir(sprite_dir) if f.endswith('.png'))

    for name in sorted(set(want) - set(found)):
        problems.append(f'sprite manquant : {name}')
    for name in sorted(set(found) - set(want)):
        problems.append(f"fichier en trop : {name} (absent du format {fmt['id']})")

    for name in sorted(set(found) & set(want)):
        with Image.open(os.path.join(sprite_dir, name)) as img:
            size, mode = img.size, img.mode
        if size != want[name]:
            problems.append(
                f'{name} : {size[0]}x{size[1]}, attendu '
                f'{want[name][0]}x{want[name][1]} (impose par VS Code)')
        if mode != 'RGBA':
            problems.append(f'{name} : mode {mode}, attendu RGBA')


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


def check_skin(skin_id, fmt):
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
    check_sprites(os.path.join(skin_dir, 'sprites'), fmt, problems)
    check_css(skin_dir, problems)
    return [f'{skin_id} : {p}' for p in problems]


def all_skin_ids():
    if not os.path.isdir(SKINS_DIR):
        return []
    return sorted(d for d in os.listdir(SKINS_DIR)
                  if os.path.isfile(os.path.join(SKINS_DIR, d, 'skin.json')))


def main(argv):
    fmt = load_format()
    targets = argv or all_skin_ids()
    if not targets:
        print('Aucun skin dans skins/.')
        return 1
    failed = 0
    for skin_id in targets:
        problems = check_skin(skin_id, fmt)
        if problems:
            failed += 1
            for p in problems:
                print('ECHEC ' + p)
        else:
            print(f'OK    {skin_id} : schema, {len(expected_files(fmt))} sprites '
                  f'(format {fmt["id"]}), dimensions, pet.css')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
