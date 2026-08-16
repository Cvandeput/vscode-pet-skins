<#
.SYNOPSIS
    Installe un skin personnalisé pour le "pet" natif de VS Code (>= 1.131).

.DESCRIPTION
    Trois opérations, toutes réversibles :
      1. remplace les 48 PNG du pet dans resources\app\out\...\media\chatPet
      2. injecte un bloc <style> dans workbench.html (repositionne et
         recolore les pupilles DOM)
      3. met à jour le checksum de workbench.html dans product.json, ce qui
         évite la bannière "Your Code installation appears corrupt"

    Tout est sauvegardé avant écriture dans %USERPROFILE%\.vscode-pet-skin\backups\<timestamp>.
    Le script est idempotent : si les 48 sprites cibles sont déjà identiques
    aux sources et que le marqueur CSS est présent, il sort sans rien écrire
    ni sauvegarder.

.PARAMETER Skin
    Nom du skin à installer, càd un sous-dossier de skins\. S'il n'est pas
    fourni explicitement, le skin est lu dans
    %USERPROFILE%\.vscode-pet-skin\state.json (défaut : nixie).

.PARAMETER List
    Affiche les skins disponibles (nom, auteur, versions vérifiées) et sort.
    Ne demande aucune élévation.

.PARAMETER KeepBackups
    Nombre de sauvegardes à conserver. Les plus anciennes sont supprimées
    après création de la nouvelle. Défaut : 5. 0 = illimité.

.PARAMETER KeepBanner
    N'écrit pas product.json. La bannière d'intégrité apparaîtra à chaque
    démarrage. À utiliser si tu préfères ne pas toucher au fichier.

.PARAMETER Force
    Ferme VS Code automatiquement au lieu de s'arrêter.

.PARAMETER RegisterLogonTask
    Crée une tâche planifiée qui rejoue l'installation à chaque ouverture de
    session, pour réappliquer le skin après une mise à jour de VS Code. La
    tâche ne fige pas le skin : elle relit state.json à chaque exécution.

.PARAMETER VSCodeRoot
    Force la racine d'installation de VS Code.

.PARAMETER SpriteDir
    Surcharge le dossier des PNG sources.

.PARAMETER CssFile
    Surcharge le fichier CSS injecté.

.PARAMETER Silent
    Supprime les messages (utilisé par la tâche planifiée).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1 -List

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1 -Skin nixie -KeepBackups 10
#>

[CmdletBinding()]
param(
    [string] $Skin = 'nixie',
    [string] $SpriteDir,
    [string] $CssFile,
    [string] $VSCodeRoot,
    [int]    $KeepBackups = 5,
    [switch] $List,
    [switch] $KeepBanner,
    [switch] $Force,
    [switch] $RegisterLogonTask,
    [switch] $Silent
)

$ErrorActionPreference = 'Stop'
$RepoRoot  = Split-Path -Parent $PSScriptRoot
$StateDir  = Join-Path $env:USERPROFILE '.vscode-pet-skin'
$BackupDir = Join-Path $StateDir 'backups'
$Marker    = 'pet-skin'

. (Join-Path $PSScriptRoot '_Common.ps1')

function Say([string]$m, [string]$c = 'Gray') {
    if (-not $Silent) { Write-Host $m -ForegroundColor $c }
}
function Fail([string]$m) { Write-Host "  ECHEC : $m" -ForegroundColor Red; exit 1 }

# --------------------------------------------------------------- -List
# Placé avant l'élévation : lister les skins ne touche à rien.
if ($List) {
    $skinsRoot = Join-Path $RepoRoot 'skins'
    $dirs = @(Get-ChildItem $skinsRoot -Directory -ErrorAction SilentlyContinue | Sort-Object Name)
    if (-not $dirs) { Fail "aucun skin dans $skinsRoot" }
    Write-Host 'Skins disponibles :' -ForegroundColor Cyan
    foreach ($d in $dirs) {
        $meta = $null
        $mf = Join-Path $d.FullName 'skin.json'
        if (Test-Path $mf) {
            try { $meta = Get-Content $mf -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json }
            catch { $meta = $null }
        }
        $name     = if ($meta -and $meta.name)   { $meta.name }   else { $d.Name }
        $author   = if ($meta -and $meta.author) { $meta.author } else { 'inconnu' }
        $verified = if ($meta -and $meta.verifiedOn) { ($meta.verifiedOn -join ', ') } else { 'non renseigne' }
        Write-Host ("   {0,-14} {1}" -f $d.Name, $name) -ForegroundColor Green
        Write-Host ("                  auteur   : {0}" -f $author)
        Write-Host ("                  verifie  : {0}" -f $verified)
        if (-not (Test-Path $mf)) { Write-Host '                  (pas de skin.json)' -ForegroundColor Yellow }
    }
    exit 0
}

# --------------------------------------------------------------- skin actif
# -Skin non fourni : on relit le dernier skin installe (state.json), ce qui
# permet a la tache planifiee de ne pas figer un nom de skin.
if (-not $PSBoundParameters.ContainsKey('Skin')) {
    $state = Get-PetSkinState -StateDir $StateDir
    if ($state -and $state.skin) { $Skin = [string]$state.skin }
}

$SkinDir = Join-Path $RepoRoot "skins\$Skin"
if (-not $SpriteDir) { $SpriteDir = Join-Path $SkinDir 'sprites' }
if (-not $CssFile)   { $CssFile   = Join-Path $SkinDir 'css\pet.css' }
if (-not (Test-Path $SkinDir)) {
    $avail = (Get-ChildItem (Join-Path $RepoRoot 'skins') -Directory -EA SilentlyContinue).Name -join ', '
    Write-Host "  ECHEC : skin '$Skin' introuvable. Disponibles : $avail" -ForegroundColor Red
    exit 1
}

# --------------------------------------------------------------- élévation
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Say '== Elevation requise, relance en administrateur' 'Yellow'
    $argList = @('-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    foreach ($k in $PSBoundParameters.Keys) {
        $v = $PSBoundParameters[$k]
        if ($v -is [switch]) { if ($v) { $argList += "-$k" } }
        else { $argList += @("-$k", "`"$v`"") }
    }
    # Le skin resolu est transmis explicitement pour que la session elevee
    # cible exactement le meme skin.
    if (-not $PSBoundParameters.ContainsKey('Skin')) { $argList += @('-Skin', "`"$Skin`"") }
    Start-Process powershell -Verb RunAs -ArgumentList $argList
    exit
}

Say '== Verifications prealables' 'Cyan'
Say '   session elevee : OK'

# --------------------------------------------------------------- VS Code fermé
$running = Get-Process -Name Code -ErrorAction SilentlyContinue
if ($running) {
    if ($Force -or $Silent) {
        $running | Stop-Process -Force
        Start-Sleep -Seconds 2
        Say '   VS Code ferme de force : OK'
    } else {
        Fail 'VS Code est ouvert. Ferme-le, ou relance avec -Force.'
    }
} else {
    Say '   VS Code ferme  : OK'
}

# --------------------------------------------------------------- localisation
$VSCodeRoot = Get-VSCodeRootPath -Explicit $VSCodeRoot
if (-not $VSCodeRoot) { Fail "Installation de VS Code introuvable. Passe -VSCodeRoot." }

# Les builds recents inserent un dossier nomme d'apres le hash du commit :
# on le resout par le commit declare, pas par une date de modification.
$build = Resolve-VSCodeBuild -VSCodeRoot $VSCodeRoot
if (-not $build) { Fail "Aucun resources\app\out sous $VSCodeRoot." }
$base = $build.Base

$paths     = Get-PetPaths -Base $base
$PetDir    = $paths.PetDir
$Workbench = $paths.Workbench
$Product   = $paths.Product

foreach ($p in @($PetDir, $Workbench, $Product)) {
    if (-not (Test-Path $p)) { Fail "Introuvable : $p" }
}

Say '== Cible' 'Cyan'
Say "   skin   : $Skin"
Say "   racine : $VSCodeRoot"
if ($base -ne $VSCodeRoot) { Say "   build  : $(Split-Path -Leaf $base)" }
if ($build.Commit)         { Say "   commit : $($build.Commit) (resolution : $($build.Method))" }
foreach ($w in $build.Warnings) { Say "   AVERTISSEMENT : $w" 'Yellow' }
if ($build.Method -eq 'lastwrite') {
    Say '   AVERTISSEMENT : build choisi par date de modification, verifie la cible.' 'Yellow'
}

# --------------------------------------------------------------- contrôles
function Get-PngSize([string]$path) {
    $fs = [IO.File]::OpenRead($path)
    try {
        $buf = New-Object byte[] 24
        [void]$fs.Read($buf, 0, 24)
    } finally { $fs.Dispose() }
    $w = ($buf[16] -shl 24) -bor ($buf[17] -shl 16) -bor ($buf[18] -shl 8) -bor $buf[19]
    $h = ($buf[20] -shl 24) -bor ($buf[21] -shl 16) -bor ($buf[22] -shl 8) -bor $buf[23]
    return @{ W = $w; H = $h }
}

Say '== Controle d''integrite des sources' 'Cyan'
$src = Get-ChildItem (Join-Path $SpriteDir 'buddy-*.png') -ErrorAction SilentlyContinue
if ($src.Count -ne 48) { Fail "48 fichiers buddy-* attendus, $($src.Count) trouves dans $SpriteDir" }

$problems = @()
foreach ($f in $src) {
    $target = Join-Path $PetDir $f.Name
    if (-not (Test-Path $target)) { $problems += "$($f.Name) : pas d'homologue dans la cible"; continue }
    $s = Get-PngSize $f.FullName
    $t = Get-PngSize $target
    if ($s.H -ne 96)          { $problems += "$($f.Name) : hauteur $($s.H), attendu 96" }
    if ($s.W % 96 -ne 0)      { $problems += "$($f.Name) : largeur $($s.W), non multiple de 96" }
    if ($s.W -ne $t.W -or $s.H -ne $t.H) {
        $problems += "$($f.Name) : $($s.W)x$($s.H) vs original $($t.W)x$($t.H) — nb de frames different"
    }
}
if ($problems) {
    Write-Host '   Anomalies :' -ForegroundColor Red
    $problems | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Fail 'aucune ecriture effectuee.'
}
Say "   48/48 OK (dimensions, homologues, nombre de frames)"

# --------------------------------------------------------------- garde-fou de version
# skin.json declare les versions de VS Code sur lesquelles le skin a ete
# verifie : on avertit sans bloquer si la version installee n'y figure pas.
$skinMeta = $null
$skinJson = Join-Path $SkinDir 'skin.json'
if (Test-Path $skinJson) {
    try { $skinMeta = Get-Content $skinJson -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json }
    catch { $skinMeta = $null }
}
$vscodeVersion = $null
$pkg = Join-Path $base 'resources\app\package.json'
if (Test-Path $pkg) {
    try { $vscodeVersion = (Get-Content $pkg -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json).version }
    catch { $vscodeVersion = $null }
}
if ($skinMeta -and $skinMeta.verifiedOn) {
    $verified = @($skinMeta.verifiedOn)
    if (-not $vscodeVersion) {
        Say "   AVERTISSEMENT : version de VS Code indeterminee (package.json illisible)." 'Yellow'
    } elseif ($verified -notcontains $vscodeVersion) {
        Say "   AVERTISSEMENT : skin verifie sur $($verified -join ', ') ; VS Code installe en $vscodeVersion." 'Yellow'
        Say '                   le format des sprites peut avoir change, verifie le rendu.' 'Yellow'
    } else {
        Say "   version de VS Code : $vscodeVersion (verifiee)"
    }
}

# Une CSP restrictive (style-src) peut neutraliser le <style> injecte : le
# seul symptome visible est alors des pupilles mal placees.
$htmlProbe = Get-Content $Workbench -Raw -ErrorAction SilentlyContinue
if ($htmlProbe -and $htmlProbe -match '<meta\s+http-equiv="Content-Security-Policy"') {
    Say '   AVERTISSEMENT : workbench.html declare une Content-Security-Policy.' 'Yellow'
    Say '                   si style-src est restrictif, le bloc <style> sera ignore' 'Yellow'
    Say '                   et les pupilles resteront mal placees.' 'Yellow'
}

# --------------------------------------------------------------- idempotence
# Rien a faire si les 48 cibles sont deja identiques aux sources et que le
# marqueur CSS est present : on sort avant toute ecriture et toute sauvegarde
# (la tache planifiee rejoue l'install a chaque ouverture de session).
if (Test-SkinApplied -SpriteDir $SpriteDir -PetDir $PetDir -Workbench $Workbench -Marker $Marker) {
    Say '== Etat' 'Cyan'
    Say '   skin deja en place, rien a faire' 'Green'
    exit 0
}

# --------------------------------------------------------------- sauvegarde
$stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$bk    = Join-Path $BackupDir $stamp
New-Item -ItemType Directory -Force -Path (Join-Path $bk 'chatPet') | Out-Null
Copy-Item (Join-Path $PetDir 'buddy-*.png') (Join-Path $bk 'chatPet') -Force
Copy-Item $Workbench (Join-Path $bk 'workbench.html') -Force
Copy-Item $Product   (Join-Path $bk 'product.json')   -Force
@{ Root = $VSCodeRoot; Base = $base; Commit = $build.Commit; Version = $vscodeVersion } |
    ConvertTo-Json | Set-Content (Join-Path $bk 'paths.json') -Encoding UTF8
Set-Content (Join-Path $StateDir 'LAST_BACKUP.txt') $bk -Encoding UTF8
Say '== Sauvegarde' 'Cyan'
Say "   $bk"

# ---- rétention : on ne garde que les N plus recentes (nom = timestamp triable)
if ($KeepBackups -gt 0) {
    $olds = @(Get-ChildItem $BackupDir -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -Skip $KeepBackups)
    foreach ($o in $olds) {
        Remove-Item $o.FullName -Recurse -Force -ErrorAction SilentlyContinue
        Say "   purge : $($o.Name)"
    }
    if ($olds.Count) { Say "   $($olds.Count) ancienne(s) sauvegarde(s) supprimee(s), $KeepBackups conservee(s)" }
}

# --------------------------------------------------------------- 1. sprites
Copy-Item (Join-Path $SpriteDir 'buddy-*.png') $PetDir -Force
$mismatch = 0
foreach ($f in $src) {
    $a = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    $b = (Get-FileHash (Join-Path $PetDir $f.Name) -Algorithm SHA256).Hash
    if ($a -ne $b) { $mismatch++ }
}
if ($mismatch) { Fail "$mismatch fichiers copies ne correspondent pas a la source." }
Say '== Sprites' 'Cyan'
Say '   48 fichiers copies, verifies par SHA256'

# --------------------------------------------------------------- 2. CSS
$css  = Get-Content $CssFile -Raw
$html = Get-Content $Workbench -Raw
$html = [regex]::Replace($html, "(?s)<!-- $Marker\:start -->.*?<!-- $Marker\:end -->\s*", '')

$block = "<!-- $Marker`:start --><style>`n$css`n</style><!-- $Marker`:end -->`n"
if ($html -match '</head>') {
    $html = $html -replace '</head>', "$block</head>"
} elseif ($html -match '</html>') {
    $html = $html -replace '</html>', "$block</html>"
} else {
    $html = $html + $block
}
[IO.File]::WriteAllText($Workbench, $html, (New-Object Text.UTF8Encoding($false)))
Say '== CSS' 'Cyan'
Say '   bloc <style> injecte dans workbench.html'

# --------------------------------------------------------------- 3. checksum
if ($KeepBanner) {
    Say '== Checksum' 'Cyan'
    Say '   ignore (-KeepBanner). La banniere d''integrite apparaitra.' 'Yellow'
} else {
    $bytes = [IO.File]::ReadAllBytes($Workbench)
    $sha   = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    $sum   = [Convert]::ToBase64String($sha).TrimEnd('=')
    $pj    = Get-Content $Product -Raw
    $key   = 'vs/code/electron-browser/workbench/workbench.html'
    if ($pj -match [regex]::Escape($key)) {
        $pj = [regex]::Replace($pj,
            '("' + [regex]::Escape($key) + '"\s*:\s*")[^"]*(")',
            "`${1}$sum`${2}")
        [IO.File]::WriteAllText($Product, $pj, (New-Object Text.UTF8Encoding($false)))
        Say '== Checksum' 'Cyan'
        Say '   product.json mis a jour, pas de banniere'
    } else {
        Say '   cle de checksum absente de product.json, rien a faire' 'Yellow'
    }
}

# --------------------------------------------------------------- état
# Skin actif, relu par la tache planifiee et par une relance sans -Skin.
@{
    skin        = $Skin
    installedAt = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')
    repoRoot    = $RepoRoot
} | ConvertTo-Json | Set-Content (Join-Path $StateDir 'state.json') -Encoding UTF8

# --------------------------------------------------------------- tâche
if ($RegisterLogonTask) {
    # Pas de -Skin : la tache relira state.json, donc changer de skin ne
    # demande pas de re-enregistrer la tache.
    $action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Silent -Force"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $set     = New-ScheduledTaskSettingsSet -StartWhenAvailable
    $prin    = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest
    Register-ScheduledTask -TaskName 'vscode-pet-skin' -Action $action -Trigger $trigger `
        -Settings $set -Principal $prin -Force | Out-Null
    Say '== Tache planifiee' 'Cyan'
    Say '   vscode-pet-skin : reapplication a chaque ouverture de session'
}

Say ''
Say '=============================================================' 'Green'
Say ' Skin applique. Relance VS Code normalement.' 'Green'
Say " Sauvegarde : $bk" 'Green'
Say ' Desinstallation : scripts\Uninstall-PetSkin.ps1' 'Green'
Say '=============================================================' 'Green'
