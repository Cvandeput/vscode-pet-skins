# vscode-pet-skins

Remplace le pet expérimental de VS Code par une mascotte personnalisée, et
documente le format pour que tu puisses dessiner la tienne.

Le skin fourni s'appelle **Nixie** — un écran d'ordinateur sur pieds, châssis
gris foncé, yeux rouge-orangé qui suivent le curseur. Nommé d'après les tubes
Nixie, ces afficheurs en verre sombre à lueur orange.

<p align="center"><img src="skins/nixie/preview/banner.gif" width="900" alt="Nixie"></p>

<p align="center"><img src="skins/nixie/preview/states.png" width="900" alt="tous les états"></p>

Installation, désinstallation et réapplication après mise à jour sont
entièrement scriptées, en une commande. Le dépôt contient aussi la
**[spécification complète du format](SPRITE-SPEC.md)**, reconstituée par
lecture du bundle de VS Code — elle n'existe nulle part ailleurs.

---

## Sommaire

- [C'est quoi ce pet ?](#cest-quoi-ce-pet-)
- [Compatibilité](#compatibilité)
- [Installation](#installation)
- [Désinstallation](#désinstallation)
- [Après une mise à jour de VS Code](#après-une-mise-à-jour-de-vs-code)
- [Comment ça marche](#comment-ça-marche)
- [Créer son propre skin](#créer-son-propre-skin)
- [Dépannage](#dépannage)
- [Risques](#risques)

---

## C'est quoi ce pet ?

VS Code **1.131** (29 juillet 2026) a introduit une fonctionnalité marquée
*highly experimental* : une petite créature animée dans le panneau de chat,
invoquée par `/vscode-pet`. Elle réagit à ce que fait l'agent — frappe, rendu,
sommeil, applaudissements — et son regard suit la souris.

Microsoft n'expose **aucun réglage** pour la personnaliser. Un clic droit donne
accès à deux variantes de sprites et à un mode « on the run », c'est tout. Ce
dépôt remplace les assets et surcharge le CSS.

## Compatibilité

| | |
|---|---|
| VS Code | ≥ 1.131 — vérifié sur **1.132.0** |
| OS | Windows (scripts PowerShell) |
| Droits | administrateur si VS Code est dans `Program Files` |

Le format des sprites est identique partout ; seuls les scripts sont
spécifiques à Windows. Sur macOS et Linux les chemins sont respectivement
`Visual Studio Code.app/Contents/Resources/app/out` et
`/usr/share/code/resources/app/out`, les étapes sont les mêmes.

## Installation

```powershell
git clone https://github.com/Cvandeput/vscode-pet-skins.git
cd vscode-pet-skins
powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1
```

Le script s'élève tout seul (invite UAC), refuse de tourner si VS Code est
ouvert — `-Force` pour le fermer automatiquement — et sauvegarde tout avant
d'écrire.

Puis, dans VS Code, tape `/vscode-pet` dans le chat.

### Options

| Option | Effet |
|---|---|
| `-Skin <nom>` | choisit un sous-dossier de `skins\`. Défaut : `nixie` |
| `-Force` | ferme VS Code au lieu de s'arrêter |
| `-KeepBanner` | ne touche pas à `product.json` ; la bannière d'intégrité apparaîtra |
| `-RegisterLogonTask` | rejoue l'installation à chaque ouverture de session |
| `-VSCodeRoot <chemin>` | force la racine d'installation |
| `-SpriteDir` / `-CssFile` | surcharge ponctuelle des chemins |

## Désinstallation

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Uninstall-PetSkin.ps1
```

Restaure les 48 sprites, `workbench.html` et `product.json` depuis la
sauvegarde la plus récente, vérifie chaque fichier par SHA-256, et supprime la
tâche planifiée si elle existe.

```powershell
.\scripts\Uninstall-PetSkin.ps1 -ListBackups
.\scripts\Uninstall-PetSkin.ps1 -Timestamp 2026-08-11_15-26-37
```

Sauvegardes dans `%USERPROFILE%\.vscode-pet-skin\backups\`.

## Après une mise à jour de VS Code

Une mise à jour réinstalle les fichiers d'origine : le skin disparaît. Relance
l'installateur, il re-résout le hash du nouveau build.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1 -Force
```

Pour ne plus y penser :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1 -RegisterLogonTask
```

Le script est idempotent : relancé alors que rien n'a changé, il ne casse ni ne
duplique quoi que ce soit.

## Comment ça marche

Trois couches, chacune indépendante et réversible.

**1. Les sprites.** 48 PNG remplacés dans
`resources\app\out\vs\workbench\contrib\chat\browser\widget\media\chatPet\`.
Ces fichiers ne figurent pas dans la liste `checksums` de `product.json` : les
remplacer seuls ne déclenche **aucun avertissement**.

**2. Le CSS.** Sur trois états (`idle`, `rendering`, `clapping`), VS Code
dessine les pupilles en DOM par-dessus le sprite — c'est ce qui leur permet de
suivre le curseur. Elles sont codées en dur en `#191a1b` et positionnées pour
l'ancien personnage. Un bloc `<style>` est injecté dans `workbench.html` pour
les repositionner sur les orbites du nouveau skin et les recolorer.

Ce dépôt patche `workbench.html` directement plutôt que de dépendre de
l'extension *Custom CSS and JS Loader* : même effet, entièrement scriptable,
sans étape manuelle.

**3. Le checksum.** `workbench.html`, lui, **est** checksummé. Le modifier
déclenche « Your Code installation appears corrupt » à chaque démarrage. Le
script recalcule le checksum et met `product.json` à jour, ce qui supprime la
bannière.

> Ce contrôle d'intégrité sert à détecter une altération non désirée de
> l'installation. Ici l'altération est volontaire, connue et réversible, donc
> le recalcul est cohérent — mais `-KeepBanner` saute cette étape si tu
> préfères garder l'avertissement.

## Créer son propre skin

```
tools/editor.html          éditeur pixel-art, à ouvrir dans le navigateur
skins/
└── nixie/
    ├── skin.json          LE fichier source : dessin, palette, repères
    ├── sprites/           les 48 PNG produits
    ├── css/pet.css        surcharges des pupilles
    ├── generator/
    │   ├── petgen.py      lit skin.json, écrit les 48 PNG
    │   └── banner.py      bannière animée du README
    └── preview/           gifs et planche des états
```

### Le tout en trois étapes

**1. Dessine.** Ouvre [`tools/editor.html`](tools/editor.html) dans ton
navigateur — aucune installation, c'est un fichier unique. Tu y dessines le
personnage sur une grille 24×24, tu choisis tes couleurs, tu places les
repères, et tu exportes un `skin.json`.

L'éditeur montre en direct l'animation `idle` telle qu'elle sera rendue, à la
taille réelle de 48 px, avec un mode *tracking* où la pupille suit ta souris
comme dans VS Code. Il génère aussi le CSS correspondant à tes orbites et
signale les incohérences de géométrie.

Outils : crayon, gomme, pot de peinture, pipette, symétrie horizontale,
annulation. Raccourcis `b` `e` `g` `i` et `Ctrl+Z`.

**2. Génère.**

```bash
mkdir -p skins/<ton-skin> && mv ~/Downloads/skin.json skins/<ton-skin>/
cp skins/nixie/generator/petgen.py skins/<ton-skin>/generator/
cd skins/<ton-skin>/generator && python petgen.py
mv out/buddy-*.png ../sprites/
```

**3. Installe.**

```powershell
.\scripts\Install-PetSkin.ps1 -Skin <ton-skin>
```

### Le générateur

`petgen.py` ne contient aucun dessin : il lit `skin.json` et en dérive les 12
animations. Tu dessines **une** image, il en produit 220 frames.

```bash
pip install pillow
python skins/nixie/generator/petgen.py                  # utilise ../skin.json
python skins/nixie/generator/petgen.py autre/skin.json  # un autre skin
```

Ce qui est dérivé automatiquement du dessin de base : la respiration et le
clignement d'`idle`, le balayage du regard de `typing`, la barre de
progression de `rendering`, les sauts de `clapping`, les cœurs de `love`, les
lunettes de `cool`, l'extinction de `sleep`, l'amorçage CRT de `waking`, la
bouche de `yapping`, l'émergence de `search`, et la bulle de `speech`.

Les repères de `skin.json` disent au générateur **où** agir : `screen` délimite
la zone où dessiner scanlines et barres, `eyes` place les orbites, `feet`
identifie les pieds pour qu'ils puissent se lever, `body` sert aux effets qui
débordent du châssis.

### Avant de te lancer

Lis [**SPRITE-SPEC.md**](SPRITE-SPEC.md). Trois pièges y sont détaillés, et
aucun n'est visible sur une image fixe :

1. **Le nombre de frames est imposé** par des tables de durées codées en dur
   dans le JS. Une frame de trop et l'animation se désynchronise.
2. **Les états *tracking* ne doivent pas contenir de pupilles** — VS Code les
   dessine par-dessus. Un sprite avec des yeux peints y donnera quatre yeux.
3. **`idle` doit se synchroniser au frame près** avec les keyframes CSS :
   descente à la frame 20, clignement aux frames 23-27.

### Repositionner les yeux

Une cellule de la grille logique 24×24 vaut 2 px CSS :

```
orbite (x, y)  ->  left: x*2 px,  top: y*2 px
```

L'éditeur fait le calcul et affiche le CSS prêt à coller dans
`skins/<ton-skin>/css/pet.css`.

## Dépannage

**Le pet est toujours l'ancien personnage.** Les PNG n'ont pas été copiés, ou
VS Code tournait pendant la copie. Relance avec `-Force`.

**L'écran est bien là mais les pupilles sont noires ou décalées.** Le bloc CSS
n'est pas pris. Vérifie que `workbench.html` contient `<!-- pet-skin:start -->`.
Si oui, c'est de la spécificité : ajoute `!important` sur les cinq déclarations
de `css/pet.css` et relance.

**Le pet a quatre yeux.** Des pupilles ont été dessinées dans les sprites
*tracking*. Voir la [section 5 de la spec](SPRITE-SPEC.md).

**Le visage se décolle du corps en animation.** Le palier de `idle` n'est pas à
la bonne frame. Voir la [section 7](SPRITE-SPEC.md).

**« Your Code installation appears corrupt ».** Checksum non mis à jour : soit
`-KeepBanner`, soit la clé est absente de `product.json`.

**Le pet n'apparaît pas.** Tape `/vscode-pet` dans le chat. Demande VS Code
≥ 1.131.

## Risques

Ce dépôt modifie les fichiers d'installation de VS Code. Rien n'est
irréversible, mais autant savoir ce qu'on fait.

- Tout est sauvegardé avec un manifeste SHA-256 avant la première écriture.
- Les sprites seuls ne déclenchent aucun avertissement d'intégrité.
- Le patch `workbench.html` + `product.json` en déclenche un, contourné par
  recalcul du checksum.
- Une mise à jour de VS Code écrase les modifications, sans casse.
- Rien ne touche aux réglages, extensions, ni données utilisateur.

`/vscode-pet` est marqué *highly experimental* par Microsoft. Noms de fichiers,
classes CSS et compteurs de frames peuvent changer d'une version à l'autre,
voire disparaître.

## Contribuer

Les skins sont bienvenus. Un skin = un dossier sous `skins/`, avec les 48 PNG,
un `skin.json`, un `pet.css` et de quoi le régénérer. Ouvre une PR avec une
capture.

## Licence

MIT. Les sprites de ce dépôt sont des créations originales ; ceux d'origine
appartiennent à Microsoft et ne sont pas redistribués ici.

