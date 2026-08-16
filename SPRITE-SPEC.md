# Spécification des sprites du pet VS Code

Tout ce qu'il faut savoir pour dessiner ses propres sprites. Ces informations
proviennent de la lecture directe du bundle de VS Code — elles ne sont
documentées nulle part officiellement.

**Elles décrivent la 1.133.** Microsoft remanie le pet d'une version à l'autre,
et les chiffres ci-dessous ne valent que pour celle-là : la 1.132 avait 12
états, 48 fichiers et des frames toujours carrées. Le format exact est relevé
dans [`schema/formats/1.133.json`](schema/formats/1.133.json), et
[`tools/probe_format.py`](tools/probe_format.py) le régénère depuis une
installation.

---

## 1. Où vivent les fichiers

```
<VSCode>\<hash-de-build>\resources\app\out\
  vs\workbench\contrib\chat\browser\widget\media\chatPet\
```

Le segment `<hash-de-build>` change à chaque mise à jour. Ne jamais le coder
en dur : le résoudre en cherchant le sous-dossier qui contient
`resources\app\out`.

82 fichiers en 1.133 : 21 états x 2 variantes, chacun avec une frame simple et
une spritesheet — sauf `revive-sign`, qui n'a pas de spritesheet.

---

## 2. Format

| Propriété | Valeur |
|---|---|
| Frame | PNG RGBA, fond transparent, **taille propre à chaque état** |
| Spritesheet | bande **horizontale**, largeur = largeur_frame × nb_frames |
| Rendu | `<canvas>` à la taille de la frame, affiché en **48×48** |
| Filtrage | `imageSmoothingEnabled = false`, `image-rendering: pixelated` |

> **La frame n'est pas carrée, et elle n'est pas 96×96 partout.** C'était vrai
> en 1.132, ça ne l'est plus en 1.133 : les états qui portent un accessoire
> sont plus larges (`typing` 168×96, `press-button` 160×96) et `sing` est aussi
> plus haute (164×124). Le pet y est dessiné à gauche, l'accessoire occupe la
> largeur en trop.
>
> **La taille d'une frame se lit sur le PNG simple**, jamais en supposant un
> carré. `buddy-typing-stable-96.spritesheet.png` fait 336×96 : divisée par 96
> elle donnerait 3,5 frames, ce qui n'a aucun sens. La frame fait 168×96 et la
> planche en contient 2.
>
> Le suffixe du nom de fichier (`-96`, `-124`) est la **hauteur** de la frame,
> pas sa largeur.

Les sprites d'origine sont dessinés en **12×12** logiques puis agrandis ×8.
Rien n'oblige à respecter cette résolution : ce dépôt travaille en **24×24**
agrandi ×4, ce qui donne deux fois plus de détail. Le seul impératif est
d'aboutir exactement à la taille de frame que l'état réclame — d'où le fait que
le facteur d'agrandissement doive diviser la largeur *et* la hauteur.

---

## 3. Nombre de frames — imposé

Les durées de chaque frame sont dans des tables `frameDurations` **codées en
dur dans le JavaScript**. Elles ne sont pas dérivées de la largeur de l'image.
Ajouter ou retirer une frame désynchronise l'animation sans rien casser de
visible à l'arrêt.

| État | Fichier | Frames | Frame | Spritesheet | Tracking |
|---|---|---|---|---|---|
| `idle` | `buddy-idle-<v>-96` | 50 | 96×96 | oui | non |
| `idle-tracking` | `buddy-idle-<v>-tracking-96` | 50 | 96×96 | oui | **oui** |
| `rendering-tracking` | `buddy-rendering-<v>-tracking-96` | 50 | 96×96 | oui | **oui** |
| `clapping-tracking` | `buddy-clapping-<v>-tracking-96` | 13 | 96×96 | oui | **oui** |
| `cool` | `buddy-cool-<v>-96` | 9 | 96×96 | oui | non |
| `sleep` | `buddy-sleep-<v>-96` | 8 | 96×96 | oui | non |
| `waking` | `buddy-waking-<v>-96` | 8 | 96×96 | oui | non |
| `jump` | `buddy-jump-<v>-96` | 6 | 96×96 | oui | non |
| `love` | `buddy-love-<v>-96` | 6 | 96×96 | oui | non |
| `press-button` | `buddy-press-button-<v>-96` | 6 | 160×96 | oui | non |
| `respawn` | `buddy-respawn-<v>-96` | 6 | 96×96 | oui | non |
| `speech` | `buddy-speech-<v>-96` | 6 | 96×96 | oui | non |
| `speechless` | `buddy-speechless-<v>-96` | 5 | 96×96 | oui | non |
| `yapping` | `buddy-yapping-<v>-96` | 5 | 96×96 | oui | non |
| `falling` | `buddy-falling-<v>-96` | 4 | 96×96 | oui | non |
| `search` | `buddy-search-<v>-96` | 4 | 96×96 | oui | non |
| `sing` | `buddy-sing-<v>-124` | 4 | 164×124 | oui | non |
| `splat` | `buddy-splat-<v>-96` | 4 | 96×96 | oui | non |
| `typing` | `buddy-typing-<v>-96` | 2 | 168×96 | oui | non |
| `worry` | `buddy-worry-<v>-96` | 2 | 96×96 | oui | non |
| `revive-sign` | `buddy-revive-sign-<v>-96` | 1 | 96×96 | **non** | non |

`<v>` vaut `stable` ou `insiders` : deux jeux complets, géométriquement
identiques, sélectionnables par **clic droit sur le pet**. Produire les deux
évite de perdre son skin en basculant.

Durées connues, en millisecondes :

```
idle / rendering : 50 x 40                       = 2000 ms
clapping         : 80,40,40,40,80,40,40,40,40,80,40,40,80
cool             : 9 valeurs
waking           : 160,100,80,90,90,90,100,170
love             : 200,200,380,100,80,1980   <- derniere frame tres longue
speech           : 220,220,220,100,160,180
yapping          : 300,240,1500,240,360      <- frame 2 tres longue
search           : 500,500,500,500
```

Les frames longues doivent être des **poses stables et lisibles**, pas des
images de transition.

---

## 4. Frames simples — deux usages

Les fichiers sans `.spritesheet` — un par état et par variante — servent dans
deux cas :

1. **Reduced motion.** Si `accessibilityService.isMotionReduced()`, tous les
   états basculent sur leur frame simple.
2. **Rendu normal**, pour les états dont la table de durées est vide :
   `onTheRun`, `searchingDown` et `yapping`.

En pratique, hors reduced motion, seuls deux fichiers simples sont chargés :

| Fichier | Utilisé pour |
|---|---|
| `buddy-idle-<v>-tracking-96.png` | état `yapping` (l'animation est une rotation CSS, pas le sprite) |
| `buddy-search-<v>-96.png` | états `onTheRun` et `searchingDown` |

Convention retenue ici : la frame simple = **frame 0** de l'animation
correspondante, sauf `search` dont la frame 0 est déjà la pose « caché ».

---

## 5. Les états « tracking » — la règle la plus importante

Trois états utilisent des sprites dits *tracking* : **idle**, **rendering**,
**clapping**.

Sur ceux-là, VS Code **superpose les pupilles en DOM**, et elles suivent le
curseur de la souris. Le sprite ne doit donc contenir **aucune pupille** :
seulement l'orbite creusée, prête à recevoir le regard.

Sur tous les autres états, les yeux sont peints dans le PNG.

Comparaison des deux versions d'origine : 128 pixels diffèrent, tous par la
même substitution `#24BFA5 ↔ #191A1B`. Les orbites ne sont donc repérables
que par différence entre les deux fichiers.

---

## 6. Géométrie du regard

### Structure DOM

```
.chat-pet-host
└ .chat-pet-overlay
  └ button.chat-pet-button          48×48, [data-state=idle|typing|love|...]
    ├ .chat-pet-sprite  (×2, double buffer)
    │   ├ canvas.chat-pet-canvas    le pixel visible
    │   └ img.chat-pet-spritesheet  (display:none)
    ├ .chat-pet-eyes[.tracking][.animated]
    │   └ .chat-pet-eye.left|.right
    │       └ .chat-pet-pupil       background:#191a1b EN DUR
    └ .chat-pet-speech-bubble
        └ canvas.chat-pet-speech-canvas
```

### CSS natif

```css
.chat-pet-eye    { position:absolute; top:30px; width:8px; height:8px; overflow:hidden }
.chat-pet-eye.left  { left:18px }
.chat-pet-eye.right { left:30px }
.chat-pet-pupil  { position:absolute; top:2px; left:2px; width:4px; height:4px;
                   background:#191a1b }
```

### Logique du regard

```js
let dx = curX - cx, dy = curY - cy, r = Math.hypot(dx, dy);
let [t, i] = [Math.round(dx/r), Math.round(dy/r)];   // composantes ∈ {-1,0,1}
pupil.style.transform = `translate(${t*2}px, ${i*2}px)`;
```

Neuf positions discrètes, diagonales comprises. Déplacement de **±2 px CSS**,
soit ±4 px image.

### Conversion des unités

```
1 cellule de grille 24×24  =  4 px image  =  2 px CSS
```

Donc, pour une orbite de 4×4 cellules dont le coin haut-gauche est en `(x, y)` :

```css
.chat-pet-eye       { top: <y*2>px; width: 8px; height: 8px; }
.chat-pet-eye.left  { left: <x_gauche*2>px; }
.chat-pet-eye.right { left: <x_droit*2>px; }
```

**La position des yeux est donc entièrement libre** dès lors qu'on injecte du
CSS — ce que fait ce dépôt. Inutile de construire son personnage autour des
coordonnées héritées du blob d'origine.

Dimensionnement : une orbite de **4×4 cellules** contient exactement le
débattement de la pupille (2×2 cellules ± 1). En dessous, la pupille déborde
sur le corps quand le regard part sur le côté — c'est d'ailleurs le
comportement des sprites d'origine, dont l'orbite ne fait qu'1 pixel natif.

### Mode drag

Pendant le déplacement du pet, les pupilles sont masquées et remplacées par
des croix en `::before` / `::after`, elles aussi codées en `#191a1b`. Sans
surcharge, le pet a des yeux colorés sauf quand on le déplace.

---

## 7. Synchronisation de `idle` — le piège invisible

Deux keyframes CSS de 2000 ms animent les pupilles, et les 50 frames × 40 ms
du sprite font exactement 2000 ms. Le sprite doit donc suivre au frame près :

| Frames | Temps | Comportement |
|---|---|---|
| 0 – 19 | 0 – 800 ms | position haute |
| 20 – 22 | 800 – 920 ms | corps descendu de 1 cellule (`translateY(2px)`) |
| 23 – 27 | 920 – 1120 ms | **clignement** : orbite écrasée à 1 cellule, alignée en bas |
| 28 – 49 | 1120 – 2000 ms | corps toujours descendu de 1 |

Ce n'est pas un cycle sinusoïdal : c'est un palier. Descente nette à la frame
20, maintien jusqu'à la fin, clignement au milieu.

Un décalage ici est **invisible sur une frame isolée** et ne se voit qu'en
animation, sous forme de visage qui se décolle du corps.

---

## 8. `onTheRun` — il n'y a pas de cycle de marche

Contre-intuitif, mais vérifié dans le code : le pet ne se déplace pas
latéralement.

```css
.chat-pet-button.on-the-run { transform: translateY(var(--vscode-spacing-size400)) }
```

`translateY`, pas `translateX`. Le pet **descend et se cache** sous la zone de
saisie. Toutes les 10 000 ms, un scheduler le fait remonter jeter un œil
(`chat-pet-search-up`, 4 frames de `search`), puis il replonge
(`chat-pet-search-down`, frame simple de `search`).

Ce qu'il faut dessiner pour cet état, c'est un **coup d'œil vertical**, pas
une marche.

---

## 9. Réglages exposés par VS Code

Aucun réglage dans `settings.json`. **Clic droit sur le pet** ouvre un menu
contextuel qui expose :

- `chat.pet.variant.stable` / `chat.pet.variant.insiders`
- `chat.pet.onTheRun`

L'état est persisté dans `state.vscdb` (storageService) sous
`chat.vscodePet.enabled`, `.variant`, `.onTheRun` — d'où le fait qu'une
recherche `@tag:experimental` dans les Settings ne renvoie rien.

---

## 10. `speech` boucle à l'infini — la bulle ne doit jamais grossir

L'état `speech` ne dessine pas le personnage : il dessine **la bulle de
dialogue**, dans un canvas séparé (`.chat-pet-speech-bubble`).

VS Code **répète l'animation en boucle** tant que l'état dure. Toute frame qui
représente une phase d'apparition — bulle plus petite, en train de grossir —
sera donc rejouée en boucle, et la bulle se dégonflera et se regonflera
indéfiniment. C'est le piège : sur une planche de frames, la séquence
« grossit puis se stabilise » paraît juste ; en animation, elle pulse.

Deux règles :

1. **La bulle atteint sa taille définitive dès la frame 0** et n'est plus
   jamais redessinée plus petite. Seul le contenu s'anime.
2. **Le contenu doit boucler proprement** sur les 6 frames. Trois points dont
   un seul est allumé à la fois (`i % 3 == k`) boucle deux fois par cycle sans
   discontinuité. Une séquence cumulative qui finit sur « tous allumés »
   marque une rupture visible au raccord.

Un skin peut aussi ne **pas** vouloir de bulle. `skin.json` expose pour ça :

```json
"speechBubble": false
```

Les 6 frames deviennent entièrement transparentes, et VS Code n'affiche rien.
Le code de la bulle reste dans le générateur, disponible pour les autres
skins ; l'option est réversible sans rien redessiner. Dans ce dépôt, `nixie`
et `vapor` sont à `false`, `codex` à `true`.

---

## 11. Checksums

`product.json` contient une liste `checksums`. Y figurent :

```
vs/workbench/workbench.desktop.main.js
vs/workbench/workbench.desktop.main.css
vs/code/electron-browser/workbench/workbench.html
```

Les PNG **n'y sont pas**. Conséquence : remplacer les sprites ne déclenche
aucun avertissement. Toucher au CSS ou au HTML, si.

Le checksum est le SHA-256 du fichier, encodé en base64, sans les `=` de
remplissage :

```powershell
$b = [IO.File]::ReadAllBytes($f)
[Convert]::ToBase64String([Security.Cryptography.SHA256]::Create().ComputeHash($b)).TrimEnd('=')
```
