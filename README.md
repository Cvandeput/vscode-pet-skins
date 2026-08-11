# vscode-pet-skins

Remplace le pet expÃ©rimental de VS Code par une mascotte personnalisÃ©e, et
documente le format pour que tu puisses dessiner la tienne.

Le skin fourni s'appelle **Nixie** â€” un Ã©cran d'ordinateur sur pieds, chÃ¢ssis
gris foncÃ©, yeux rouge-orangÃ© qui suivent le curseur. NommÃ© d'aprÃ¨s les tubes
Nixie, ces afficheurs en verre sombre Ã  lueur orange.

<p align="center">
  <img src="skins/nixie/preview/idle.gif" width="180" alt="idle">
  <img src="skins/nixie/preview/search.gif" width="180" alt="search">
  <img src="skins/nixie/preview/love.gif" width="180" alt="love">
</p>

<p align="center"><img src="skins/nixie/preview/states.png" width="900" alt="tous les Ã©tats"></p>

Installation, dÃ©sinstallation et rÃ©application aprÃ¨s mise Ã  jour sont
entiÃ¨rement scriptÃ©es, en une commande. Le dÃ©pÃ´t contient aussi la
**[spÃ©cification complÃ¨te du format](SPRITE-SPEC.md)**, reconstituÃ©e par
lecture du bundle de VS Code â€” elle n'existe nulle part ailleurs.

---

## Sommaire

- [C'est quoi ce pet ?](#cest-quoi-ce-pet-)
- [CompatibilitÃ©](#compatibilitÃ©)
- [Installation](#installation)
- [DÃ©sinstallation](#dÃ©sinstallation)
- [AprÃ¨s une mise Ã  jour de VS Code](#aprÃ¨s-une-mise-Ã -jour-de-vs-code)
- [Comment Ã§a marche](#comment-Ã§a-marche)
- [CrÃ©er son propre skin](#crÃ©er-son-propre-skin)
- [DÃ©pannage](#dÃ©pannage)
- [Risques](#risques)

---

## C'est quoi ce pet ?

VS Code **1.131** (29 juillet 2026) a introduit une fonctionnalitÃ© marquÃ©e
*highly experimental* : une petite crÃ©ature animÃ©e dans le panneau de chat,
invoquÃ©e par `/vscode-pet`. Elle rÃ©agit Ã  ce que fait l'agent â€” frappe, rendu,
sommeil, applaudissements â€” et son regard suit la souris.

Microsoft n'expose **aucun rÃ©glage** pour la personnaliser. Un clic droit donne
accÃ¨s Ã  deux variantes de sprites et Ã  un mode Â« on the run Â», c'est tout. Ce
dÃ©pÃ´t remplace les assets et surcharge le CSS.

## CompatibilitÃ©

| | |
|---|---|
| VS Code | â‰¥ 1.131 â€” vÃ©rifiÃ© sur **1.132.0** |
| OS | Windows (scripts PowerShell) |
| Droits | administrateur si VS Code est dans `Program Files` |

Le format des sprites est identique partout ; seuls les scripts sont
spÃ©cifiques Ã  Windows. Sur macOS et Linux les chemins sont respectivement
`Visual Studio Code.app/Contents/Resources/app/out` et
`/usr/share/code/resources/app/out`, les Ã©tapes sont les mÃªmes.

## Installation

```powershell
git clone https://github.com/Cvandeput/vscode-pet-skins.git
cd vscode-pet-skins
powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1
```

Le script s'Ã©lÃ¨ve tout seul (invite UAC), refuse de tourner si VS Code est
ouvert â€” `-Force` pour le fermer automatiquement â€” et sauvegarde tout avant
d'Ã©crire.

Puis, dans VS Code, tape `/vscode-pet` dans le chat.

### Options

| Option | Effet |
|---|---|
| `-Skin <nom>` | choisit un sous-dossier de `skins\`. DÃ©faut : `nixie` |
| `-Force` | ferme VS Code au lieu de s'arrÃªter |
| `-KeepBanner` | ne touche pas Ã  `product.json` ; la banniÃ¨re d'intÃ©gritÃ© apparaÃ®tra |
| `-RegisterLogonTask` | rejoue l'installation Ã  chaque ouverture de session |
| `-VSCodeRoot <chemin>` | force la racine d'installation |
| `-SpriteDir` / `-CssFile` | surcharge ponctuelle des chemins |

## DÃ©sinstallation

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Uninstall-PetSkin.ps1
```

Restaure les 48 sprites, `workbench.html` et `product.json` depuis la
sauvegarde la plus rÃ©cente, vÃ©rifie chaque fichier par SHA-256, et supprime la
tÃ¢che planifiÃ©e si elle existe.

```powershell
.\scripts\Uninstall-PetSkin.ps1 -ListBackups
.\scripts\Uninstall-PetSkin.ps1 -Timestamp 2026-08-11_15-26-37
```

Sauvegardes dans `%USERPROFILE%\.vscode-pet-skin\backups\`.

## AprÃ¨s une mise Ã  jour de VS Code

Une mise Ã  jour rÃ©installe les fichiers d'origine : le skin disparaÃ®t. Relance
l'installateur, il re-rÃ©sout le hash du nouveau build.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1 -Force
```

Pour ne plus y penser :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1 -RegisterLogonTask
```

Le script est idempotent : relancÃ© alors que rien n'a changÃ©, il ne casse ni ne
duplique quoi que ce soit.

## Comment Ã§a marche

Trois couches, chacune indÃ©pendante et rÃ©versible.

**1. Les sprites.** 48 PNG remplacÃ©s dans
`resources\app\out\vs\workbench\contrib\chat\browser\widget\media\chatPet\`.
Ces fichiers ne figurent pas dans la liste `checksums` de `product.json` : les
remplacer seuls ne dÃ©clenche **aucun avertissement**.

**2. Le CSS.** Sur trois Ã©tats (`idle`, `rendering`, `clapping`), VS Code
dessine les pupilles en DOM par-dessus le sprite â€” c'est ce qui leur permet de
suivre le curseur. Elles sont codÃ©es en dur en `#191a1b` et positionnÃ©es pour
l'ancien personnage. Un bloc `<style>` est injectÃ© dans `workbench.html` pour
les repositionner sur les orbites du nouveau skin et les recolorer.

Ce dÃ©pÃ´t patche `workbench.html` directement plutÃ´t que de dÃ©pendre de
l'extension *Custom CSS and JS Loader* : mÃªme effet, entiÃ¨rement scriptable,
sans Ã©tape manuelle.

**3. Le checksum.** `workbench.html`, lui, **est** checksummÃ©. Le modifier
dÃ©clenche Â« Your Code installation appears corrupt Â» Ã  chaque dÃ©marrage. Le
script recalcule le checksum et met `product.json` Ã  jour, ce qui supprime la
banniÃ¨re.

> Ce contrÃ´le d'intÃ©gritÃ© sert Ã  dÃ©tecter une altÃ©ration non dÃ©sirÃ©e de
> l'installation. Ici l'altÃ©ration est volontaire, connue et rÃ©versible, donc
> le recalcul est cohÃ©rent â€” mais `-KeepBanner` saute cette Ã©tape si tu
> prÃ©fÃ¨res garder l'avertissement.

## CrÃ©er son propre skin

```
skins/
â””â”€â”€ nixie/
    â”œâ”€â”€ skin.json          mÃ©tadonnÃ©es : palette, coordonnÃ©es des orbites
    â”œâ”€â”€ sprites/           les 48 PNG
    â”œâ”€â”€ css/pet.css        surcharges des pupilles
    â”œâ”€â”€ generator/         le script qui produit les sprites
    â””â”€â”€ preview/           gifs et planche des Ã©tats
```

Duplique `skins/nixie/` sous un autre nom, modifie, puis :

```powershell
.\scripts\Install-PetSkin.ps1 -Skin <ton-skin>
```

### Le gÃ©nÃ©rateur

Tout le dessin de Nixie est produit par
[`skins/nixie/generator/petgen.py`](skins/nixie/generator/petgen.py) â€” ~400
lignes de Python, sans dÃ©pendance hors Pillow. Aucun asset n'est dessinÃ© Ã  la
main.

```bash
pip install pillow
python skins/nixie/generator/petgen.py     # Ã©crit out/ : 48 PNG + preview/
```

Structure : la palette dans un dict en tÃªte de fichier, `draw_base()` pour le
chÃ¢ssis, une fonction par animation, l'assemblage des spritesheets Ã  la fin.
Changer une couleur tient en une ligne ; redessiner le personnage tient dans
`draw_base()`.

### Avant de te lancer

Lis [**SPRITE-SPEC.md**](SPRITE-SPEC.md). Trois piÃ¨ges y sont dÃ©taillÃ©s, et
aucun n'est visible sur une image fixe :

1. **Le nombre de frames est imposÃ©** par des tables de durÃ©es codÃ©es en dur
   dans le JS. Une frame de trop et l'animation se dÃ©synchronise.
2. **Les Ã©tats *tracking* ne doivent pas contenir de pupilles** â€” VS Code les
   dessine par-dessus. Un sprite avec des yeux peints y donnera quatre yeux.
3. **`idle` doit se synchroniser au frame prÃ¨s** avec les keyframes CSS :
   descente Ã  la frame 20, clignement aux frames 23-27.

### Repositionner les yeux

Une cellule de la grille logique 24Ã—24 vaut 2 px CSS :

```
orbite (x, y)  ->  left: x*2 px,  top: y*2 px
```

Reporte les valeurs dans `skins/<ton-skin>/css/pet.css` et dans `skin.json`.

## DÃ©pannage

**Le pet est toujours l'ancien personnage.** Les PNG n'ont pas Ã©tÃ© copiÃ©s, ou
VS Code tournait pendant la copie. Relance avec `-Force`.

**L'Ã©cran est bien lÃ  mais les pupilles sont noires ou dÃ©calÃ©es.** Le bloc CSS
n'est pas pris. VÃ©rifie que `workbench.html` contient `<!-- pet-skin:start -->`.
Si oui, c'est de la spÃ©cificitÃ© : ajoute `!important` sur les cinq dÃ©clarations
de `css/pet.css` et relance.

**Le pet a quatre yeux.** Des pupilles ont Ã©tÃ© dessinÃ©es dans les sprites
*tracking*. Voir la [section 5 de la spec](SPRITE-SPEC.md).

**Le visage se dÃ©colle du corps en animation.** Le palier de `idle` n'est pas Ã 
la bonne frame. Voir la [section 7](SPRITE-SPEC.md).

**Â« Your Code installation appears corrupt Â».** Checksum non mis Ã  jour : soit
`-KeepBanner`, soit la clÃ© est absente de `product.json`.

**Le pet n'apparaÃ®t pas.** Tape `/vscode-pet` dans le chat. Demande VS Code
â‰¥ 1.131.

## Risques

Ce dÃ©pÃ´t modifie les fichiers d'installation de VS Code. Rien n'est
irrÃ©versible, mais autant savoir ce qu'on fait.

- Tout est sauvegardÃ© avec un manifeste SHA-256 avant la premiÃ¨re Ã©criture.
- Les sprites seuls ne dÃ©clenchent aucun avertissement d'intÃ©gritÃ©.
- Le patch `workbench.html` + `product.json` en dÃ©clenche un, contournÃ© par
  recalcul du checksum.
- Une mise Ã  jour de VS Code Ã©crase les modifications, sans casse.
- Rien ne touche aux rÃ©glages, extensions, ni donnÃ©es utilisateur.

`/vscode-pet` est marquÃ© *highly experimental* par Microsoft. Noms de fichiers,
classes CSS et compteurs de frames peuvent changer d'une version Ã  l'autre,
voire disparaÃ®tre.

## Contribuer

Les skins sont bienvenus. Un skin = un dossier sous `skins/`, avec les 48 PNG,
un `skin.json`, un `pet.css` et de quoi le rÃ©gÃ©nÃ©rer. Ouvre une PR avec une
capture.

## Licence

MIT. Les sprites de ce dÃ©pÃ´t sont des crÃ©ations originales ; ceux d'origine
appartiennent Ã  Microsoft et ne sont pas redistribuÃ©s ici.

