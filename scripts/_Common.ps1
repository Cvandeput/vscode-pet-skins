<#
.SYNOPSIS
    Fonctions partagées par Install-PetSkin.ps1 et Uninstall-PetSkin.ps1.

.DESCRIPTION
    Ce fichier n'est pas exécutable seul : il est dot-sourcé par les deux
    scripts (". `$PSScriptRoot\_Common.ps1"). Il regroupe :
      - la localisation de la racine d'installation de VS Code ;
      - la résolution du build courant (dossier nommé d'après le hash du
        commit), par le commit déclaré et non par une date de modification ;
      - le calcul des chemins cibles (sprites, workbench.html, product.json) ;
      - le chargement du descripteur de format (schema\formats\<id>.json) et
        le contrôle d'intégrité d'un jeu de sprites contre ce descripteur ;
      - le test « le skin est-il déjà en place ? » utilisé pour l'idempotence.

    Rien n'est codé en dur sur le format des sprites : le nombre d'états, le
    nombre de fichiers et les dimensions de chaque frame sont lus dans le
    descripteur. VS Code change ce format d'une version à l'autre (48 fichiers
    et frame carrée en 1.132, 82 fichiers et frames rectangulaires en 1.133) :
    la seule façon de ne pas se tromper est de relire le relevé.

    Aucune fonction n'écrit dans l'installation de VS Code, et aucune
    n'affiche quoi que ce soit : les avertissements sont retournés dans le
    champ Warnings, à charge de l'appelant de les afficher.
#>

# ---- racine d'installation

function Get-VSCodeRootPath {
    <#  Retourne la racine de VS Code, ou $null. Un chemin explicite gagne. #>
    param([string] $Explicit)

    if ($Explicit) {
        if (Test-Path $Explicit) { return (Resolve-Path $Explicit).Path }
        return $null
    }
    $candidates = @(
        'C:\Program Files\Microsoft VS Code',
        'C:\Program Files (x86)\Microsoft VS Code',
        (Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code')
    )
    return ($candidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
}

# ---- commit du build courant

function Get-VSCodeCommitFromProduct {
    <#  Clé "commit" de <racine>\resources\app\product.json, ou $null. #>
    param([Parameter(Mandatory)][string] $VSCodeRoot)

    $pj = Join-Path $VSCodeRoot 'resources\app\product.json'
    if (-not (Test-Path $pj)) { return $null }
    try {
        $json = Get-Content $pj -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
        if ($json -and $json.commit) { return [string]$json.commit }
    } catch { return $null }
    return $null
}

function Get-VSCodeCommitFromExe {
    <#
        Commit rapporté par "Code.exe --version" (sortie : version, commit,
        architecture). L'appel peut être lent ou échouer : il est borné par un
        timeout et n'émet jamais d'erreur.
    #>
    param(
        [Parameter(Mandatory)][string] $VSCodeRoot,
        [int] $TimeoutSec = 10
    )

    $exe = Join-Path $VSCodeRoot 'Code.exe'
    if (-not (Test-Path $exe)) { return $null }

    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("petskin-ver-{0}.txt" -f ([guid]::NewGuid().ToString('N')))
    try {
        $proc = Start-Process -FilePath $exe -ArgumentList '--version' -NoNewWindow -PassThru `
            -RedirectStandardOutput $tmp -ErrorAction SilentlyContinue
        if (-not $proc) { return $null }
        if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
            try { $proc.Kill() } catch { $null = $_ }
            return $null
        }
        $lines = @(Get-Content $tmp -ErrorAction SilentlyContinue)
        # On ne se fie pas au rang de la ligne : on prend le premier jeton qui
        # a la forme d'un hash de commit (40 caractères hexadécimaux).
        foreach ($l in $lines) {
            $t = "$l".Trim()
            if ($t -match '^[0-9a-f]{40}$') { return $t }
        }
        return $null
    } catch {
        return $null
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

# ---- résolution du build

function Resolve-VSCodeBuild {
    <#
        Détermine le dossier de base contenant resources\app\out.

        Ordre : commit de product.json (recoupé avec Code.exe --version) ->
        sous-dossier portant ce nom -> layout sans dossier de hash -> en
        dernier recours le sous-dossier hash le plus récemment modifié
        (avertissement).

        Retourne une hashtable @{ Root; Base; Commit; Method; Warnings } ou
        $null si aucun resources\app\out n'est trouvé.
    #>
    param(
        [Parameter(Mandatory)][string] $VSCodeRoot,
        [int] $ExeTimeoutSec = 10
    )

    $warnings = @()
    $productCommit = Get-VSCodeCommitFromProduct $VSCodeRoot
    $exeCommit     = Get-VSCodeCommitFromExe -VSCodeRoot $VSCodeRoot -TimeoutSec $ExeTimeoutSec

    if ($productCommit -and $exeCommit -and $productCommit -ne $exeCommit) {
        $warnings += "product.json annonce le commit $productCommit, Code.exe --version annonce $exeCommit"
    }

    # Candidats dans l'ordre de confiance, sans doublon.
    $commits = @()
    foreach ($c in @($productCommit, $exeCommit)) {
        if ($c -and ($commits -notcontains $c)) { $commits += $c }
    }

    # Sous-dossiers "hash" plausibles.
    $hashDirs = @(Get-ChildItem $VSCodeRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName 'resources\app\out') })

    if (-not $hashDirs) {
        # Layout sans dossier de hash : les fichiers sont directement sous la racine.
        if (Test-Path (Join-Path $VSCodeRoot 'resources\app\out')) {
            $commit = if ($commits) { $commits[0] } else { $null }
            return @{ Root = $VSCodeRoot; Base = $VSCodeRoot; Commit = $commit; Method = 'racine'; Warnings = $warnings }
        }
        return $null
    }

    # La source fiable est le product.json de CHAQUE build : celui de la racine
    # n'existe pas toujours, et Code.exe --version peut rapporter la version
    # d'Electron. Le dossier, lui, porte un commit TRONQUE (10 caracteres sur
    # les builds observes) : on compare donc par prefixe, pas par egalite.
    $cands = @()
    foreach ($d in $hashDirs) {
        $own = Get-VSCodeCommitFromProduct $d.FullName
        $cands += @{ Dir = $d; Commit = $own }
    }

    foreach ($c in $cands) {
        if (-not $c.Commit) { continue }
        $match = $false
        foreach ($ref in $commits) {
            if ($ref -eq $c.Commit -or $ref.StartsWith($c.Dir.Name) -or $c.Commit.StartsWith($c.Dir.Name)) {
                $match = $true; break
            }
        }
        # Sans commit de reference exterieur, un build qui se declare lui-meme
        # et dont le dossier porte son prefixe est deja une identification sure.
        if (-not $commits -and $c.Commit.StartsWith($c.Dir.Name)) { $match = $true }
        if ($match) {
            return @{ Root = $VSCodeRoot; Base = $c.Dir.FullName; Commit = $c.Commit
                      Method = 'commit'; Warnings = $warnings }
        }
    }

    # Un seul build installe : aucune ambiguite a lever, pas d'avertissement.
    if ($hashDirs.Count -eq 1) {
        $only = $cands[0]
        $label = $only.Commit
        if (-not $label) { $label = $only.Dir.Name }
        return @{ Root = $VSCodeRoot; Base = $only.Dir.FullName; Commit = $label
                  Method = 'unique'; Warnings = $warnings }
    }

    # Dernier recours : le plus récemment modifié.
    $pick = $hashDirs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($commits) {
        $warnings += "aucun dossier ne correspond au commit declare ($($commits -join ', ')) ; repli sur le dossier le plus recent : $($pick.Name)"
    } else {
        $warnings += "commit du build indetermine ; repli sur le dossier le plus recent : $($pick.Name)"
    }
    return @{ Root = $VSCodeRoot; Base = $pick.FullName; Commit = $pick.Name; Method = 'lastwrite'; Warnings = $warnings }
}

# ---- lecture d'en-tête PNG

function Get-PngSize {
    <#
        Dimensions d'un PNG, lues dans le chunk IHDR (offsets 16 à 23,
        gros-boutiste).

        Les casts [int] ne sont PAS décoratifs. Sous Windows PowerShell 5.1,
        `-shl` conserve le type de l'opérande gauche : décaler un [byte] de 8
        bits ou plus renvoie 0, puisque tout sort de la largeur du type.

            [byte]0x04 -shl 8   ->  0        (et le résultat est un [byte])
            [int]0x04  -shl 8   ->  1024

        Sans les casts, toute image de plus de 255 px de large est mesurée sur
        son seul octet de poids faible : une planche de 1248 px (0x04E0) est
        lue 224 px (0xE0), et le contrôle « largeur multiple de 96 » refuse
        alors des fichiers parfaitement valides.
    #>
    param([Parameter(Mandatory)][string] $Path)

    $buf = New-Object byte[] 24
    $fs = [IO.File]::OpenRead($Path)
    try {
        # Stream.Read peut rendre moins d'octets que demandé : on boucle.
        $read = 0
        while ($read -lt 24) {
            $n = $fs.Read($buf, $read, 24 - $read)
            if ($n -le 0) { break }
            $read += $n
        }
    } finally { $fs.Dispose() }
    if ($read -lt 24) { return @{ W = 0; H = 0; Valid = $false } }

    # signature PNG : 89 50 4E 47 0D 0A 1A 0A
    $sig = @(0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A)
    for ($i = 0; $i -lt 8; $i++) {
        if ($buf[$i] -ne $sig[$i]) { return @{ W = 0; H = 0; Valid = $false } }
    }

    $w = ([int]$buf[16] -shl 24) -bor ([int]$buf[17] -shl 16) -bor
         ([int]$buf[18] -shl 8)  -bor  [int]$buf[19]
    $h = ([int]$buf[20] -shl 24) -bor ([int]$buf[21] -shl 16) -bor
         ([int]$buf[22] -shl 8)  -bor  [int]$buf[23]
    return @{ W = $w; H = $h; Valid = $true }
}

# ---- chemins cibles

function Get-PetPaths {
    <#  Chemins des trois cibles, à partir du dossier de base. #>
    param([Parameter(Mandatory)][string] $Base)

    $out = Join-Path $Base 'resources\app\out'
    return @{
        Out       = $out
        PetDir    = Join-Path $out 'vs\workbench\contrib\chat\browser\widget\media\chatPet'
        Workbench = Join-Path $out 'vs\code\electron-browser\workbench\workbench.html'
        Product   = Join-Path $Base 'resources\app\product.json'
    }
}

# ---- descripteur de format

function Get-PetFormatVersionKey {
    <#
        Clé de tri d'un identifiant de format ("1.133", "1.133.0"). Retourne
        un [version] quand c'est possible, sinon [version]0.0 : un id exotique
        se retrouve en queue de tri plutôt que de faire échouer la comparaison.
    #>
    param([string] $Id)

    $m = [regex]::Match("$Id", '\d+(\.\d+){0,3}')
    if ($m.Success) {
        try { return [version] $m.Value } catch { $null = $_ }
    }
    return [version] '0.0'
}

function Get-PetFormatFileNames {
    <#
        Noms de fichiers attendus pour un état du descripteur, avec les
        dimensions attendues de chacun.

        Convention de nommage de VS Code (cf. tools\probe_format.py) :
            buddy-<état>-<stable|insiders>[-tracking]-<suffixe>.png
            buddy-<état>-<stable|insiders>[-tracking]-<suffixe>.spritesheet.png

        Le suffixe numérique du nom est la HAUTEUR de la frame, pas sa largeur.
        Les deux variantes (stable / insiders) sont identiques, d'où 4 fichiers
        par état — 2 seulement quand l'état n'a pas de spritesheet.

        Retourne une table @{ nom = @{ W; H; Sheet } }.
    #>
    param([Parameter(Mandatory)] $State)

    $fw = [int] $State.frameWidth
    $fh = [int] $State.frameHeight
    $n  = [int] $State.frames
    if ($n -lt 1) { $n = 1 }
    $track = ''
    if ($State.tracking) { $track = '-tracking' }

    $out = @{}
    foreach ($variant in @('stable', 'insiders')) {
        $stem = "buddy-{0}-{1}{2}-{3}" -f $State.state, $variant, $track, $State.suffix
        $out["$stem.png"] = @{ W = $fw; H = $fh; Sheet = $false }
        if ($State.spritesheet) {
            $out["$stem.spritesheet.png"] = @{ W = $fw * $n; H = $fh; Sheet = $true }
        }
    }
    return $out
}

function Get-PetFormat {
    <#
        Charge le descripteur de format qui décrit les sprites attendus.

        Sélection, par ordre de priorité :
          1. -Id : descripteur imposé (id déclaré ou nom de fichier) ;
          2. -VSCodeVersion : le descripteur dont le tableau "vscode" contient
             cette version ;
          3. à défaut, le descripteur d'id le plus récent, avec un
             avertissement — le format a pu changer sans qu'on l'ait relevé.

        Retourne @{ Id; Path; States; Files; FileCount; StateCount; Matched;
        Warnings } ou $null si aucun descripteur n'est lisible. Comme le reste
        du fichier, rien n'est affiché : les avertissements sont retournés.
    #>
    param(
        # _Common.ps1 vit dans scripts\, les descripteurs dans schema\formats\ :
        # la valeur par defaut evite que chaque appelant ait a la recalculer.
        [string] $FormatDir = (Join-Path (Split-Path -Parent $PSScriptRoot) 'schema\formats'),
        [string] $Id,
        [string] $VSCodeVersion
    )

    $warnings = @()
    $all = @()
    foreach ($f in @(Get-ChildItem (Join-Path $FormatDir '*.json') -ErrorAction SilentlyContinue)) {
        $doc = $null
        try { $doc = Get-Content $f.FullName -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json }
        catch { $doc = $null }
        if (-not $doc -or -not $doc.states) { continue }
        $fid = if ($doc.id) { [string] $doc.id } else { $f.BaseName }
        $all += @{ Id = $fid; Path = $f.FullName; Doc = $doc
                   Vscode = @($doc.vscode); File = $f.BaseName }
    }
    if (-not $all) { return $null }

    $all = @($all | Sort-Object { Get-PetFormatVersionKey $_.Id } -Descending)

    $pick = $null
    $matched = $false
    if ($Id) {
        $pick = $all | Where-Object { $_.Id -eq $Id -or $_.File -eq $Id } | Select-Object -First 1
        if (-not $pick) {
            $known = ($all | ForEach-Object { $_.Id }) -join ', '
            $warnings += "format '$Id' inconnu ; disponibles : $known"
            return @{ Id = $Id; Path = $null; States = @(); Files = @{}
                      FileCount = 0; StateCount = 0; Matched = $false; Warnings = $warnings }
        }
        $matched = $true
    } elseif ($VSCodeVersion) {
        $pick = $all | Where-Object { $_.Vscode -contains $VSCodeVersion } | Select-Object -First 1
        if ($pick) {
            $matched = $true
        } else {
            $pick = $all[0]
            $warnings += "format non releve pour la version $VSCodeVersion, on tente avec $($pick.Id)"
            $warnings += "si le rendu est faux, relance : python tools\probe_format.py --out schema\formats\$VSCodeVersion.json"
        }
    } else {
        $pick = $all[0]
        $warnings += "version de VS Code indeterminee, on tente avec le format $($pick.Id)"
    }

    $states = @($pick.Doc.states)
    $files = @{}
    foreach ($s in $states) {
        foreach ($kv in (Get-PetFormatFileNames -State $s).GetEnumerator()) {
            $files[$kv.Key] = $kv.Value
        }
    }

    return @{
        Id         = $pick.Id
        Path       = $pick.Path
        States     = $states
        Files      = $files
        FileCount  = $files.Count
        StateCount = $states.Count
        Matched    = $matched
        Warnings   = $warnings
    }
}

# ---- contrôle d'intégrité d'un jeu de sprites

function Test-SpriteSet {
    <#
        Confronte un dossier de sprites au descripteur de format. Retourne la
        liste (éventuellement vide) des anomalies, chacune nommant le fichier
        fautif.

        Contrôles :
          - chaque fichier annoncé par le descripteur est présent ;
          - le PNG simple mesure frameWidth x frameHeight ;
          - la spritesheet mesure (frameWidth * frames) x frameHeight ;
          - aucun buddy-*.png en trop dans le dossier source ;
          - avec -PetDir, chaque source a un homologue de mêmes dimensions
            dans la cible. C'est ce dernier point qui révèle un décalage de
            version : VS Code attend le format de SON build, pas celui du
            descripteur.
    #>
    param(
        [Parameter(Mandatory)][string] $SpriteDir,
        [Parameter(Mandatory)] $Format,
        [string] $PetDir
    )

    $problems = @()
    if (-not $Format -or -not $Format.Files -or $Format.Files.Count -eq 0) {
        $problems += "descripteur de format vide ou illisible"
        return $problems
    }
    if (-not (Test-Path $SpriteDir)) {
        $problems += "dossier des sprites introuvable : $SpriteDir"
        return $problems
    }

    $present = @{}
    foreach ($f in @(Get-ChildItem (Join-Path $SpriteDir 'buddy-*.png') -ErrorAction SilentlyContinue)) {
        $present[$f.Name] = $f.FullName
    }

    foreach ($name in ($Format.Files.Keys | Sort-Object)) {
        $want = $Format.Files[$name]
        if (-not $present.ContainsKey($name)) {
            $problems += "$name : manquant dans $SpriteDir"
            continue
        }
        $path = $present[$name]
        $s = Get-PngSize $path
        if (-not $s.Valid) {
            $problems += "$name : PNG illisible ou tronque"
            continue
        }
        if ($s.W -ne $want.W -or $s.H -ne $want.H) {
            $kind = if ($want.Sheet) { 'planche' } else { 'frame' }
            $problems += "$name : $kind $($s.W)x$($s.H), attendu $($want.W)x$($want.H)"
            continue
        }
        if ($PetDir) {
            $target = Join-Path $PetDir $name
            if (-not (Test-Path $target)) {
                $problems += "$name : pas d'homologue dans la cible"
                continue
            }
            $t = Get-PngSize $target
            if (-not $t.Valid) {
                $problems += "$name : homologue cible illisible"
            } elseif ($s.W -ne $t.W -or $s.H -ne $t.H) {
                $problems += "$name : $($s.W)x$($s.H) vs original $($t.W)x$($t.H) - format de VS Code different"
            }
        }
    }

    foreach ($name in ($present.Keys | Sort-Object)) {
        if (-not $Format.Files.ContainsKey($name)) {
            $problems += "$name : fichier en trop, absent du format $($Format.Id)"
        }
    }

    return $problems
}

# ---- idempotence

function Test-SkinApplied {
    <#
        Vrai si tous les sprites annoncés par le descripteur ont le même
        SHA256 côté source et côté cible, ET que le marqueur CSS est présent
        dans workbench.html.

        C'est cette fonction qui porte l'idempotence : un compte de fichiers
        faux la ferait répondre « non » à chaque exécution, et la tâche
        planifiée créerait une sauvegarde à chaque ouverture de session. Le
        nombre attendu vient donc du descripteur, jamais d'une constante.
    #>
    param(
        [Parameter(Mandatory)][string] $SpriteDir,
        [Parameter(Mandatory)][string] $PetDir,
        [Parameter(Mandatory)][string] $Workbench,
        [string] $Marker = 'pet-skin',
        $Format
    )

    if (-not (Test-Path $Workbench)) { return $false }
    $html = Get-Content $Workbench -Raw -ErrorAction SilentlyContinue
    if (-not $html -or $html -notmatch [regex]::Escape("<!-- $Marker`:start -->")) { return $false }

    $src = @(Get-ChildItem (Join-Path $SpriteDir 'buddy-*.png') -ErrorAction SilentlyContinue)
    if ($Format -and $Format.FileCount -gt 0) {
        if ($src.Count -ne $Format.FileCount) { return $false }
    } elseif ($src.Count -eq 0) {
        return $false
    }

    foreach ($f in $src) {
        $target = Join-Path $PetDir $f.Name
        if (-not (Test-Path $target)) { return $false }
        $a = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
        $b = (Get-FileHash $target     -Algorithm SHA256).Hash
        if ($a -ne $b) { return $false }
    }
    return $true
}

# ---- etat (skin actif)

function Get-PetSkinState {
    <#  Contenu de %USERPROFILE%\.vscode-pet-skin\state.json, ou $null. #>
    param([string] $StateDir = (Join-Path $env:USERPROFILE '.vscode-pet-skin'))

    $f = Join-Path $StateDir 'state.json'
    if (-not (Test-Path $f)) { return $null }
    try { return (Get-Content $f -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json) }
    catch { return $null }
}
