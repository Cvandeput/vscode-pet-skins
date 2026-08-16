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
      - le test « le skin est-il déjà en place ? » utilisé pour l'idempotence.

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

    foreach ($c in $commits) {
        $dir = Join-Path $VSCodeRoot $c
        if ((Test-Path $dir) -and (Test-Path (Join-Path $dir 'resources\app\out'))) {
            return @{ Root = $VSCodeRoot; Base = $dir; Commit = $c; Method = 'commit'; Warnings = $warnings }
        }
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

    # Dernier recours : le plus récemment modifié.
    $pick = $hashDirs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($commits) {
        $warnings += "aucun dossier ne porte le commit declare ($($commits -join ', ')) ; repli sur le dossier le plus recent : $($pick.Name)"
    } else {
        $warnings += "commit du build indetermine ; repli sur le dossier le plus recent : $($pick.Name)"
    }
    return @{ Root = $VSCodeRoot; Base = $pick.FullName; Commit = $pick.Name; Method = 'lastwrite'; Warnings = $warnings }
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

# ---- idempotence

function Test-SkinApplied {
    <#
        Vrai si les 48 sprites cibles ont le même SHA256 que les sources ET
        que le marqueur CSS est présent dans workbench.html.
    #>
    param(
        [Parameter(Mandatory)][string] $SpriteDir,
        [Parameter(Mandatory)][string] $PetDir,
        [Parameter(Mandatory)][string] $Workbench,
        [string] $Marker = 'pet-skin'
    )

    if (-not (Test-Path $Workbench)) { return $false }
    $html = Get-Content $Workbench -Raw -ErrorAction SilentlyContinue
    if (-not $html -or $html -notmatch [regex]::Escape("<!-- $Marker`:start -->")) { return $false }

    $src = @(Get-ChildItem (Join-Path $SpriteDir 'buddy-*.png') -ErrorAction SilentlyContinue)
    if ($src.Count -ne 48) { return $false }

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
