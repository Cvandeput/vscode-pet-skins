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
    Le script est idempotent : le relancer ne duplique rien.

.PARAMETER Skin
    Nom du skin à installer, càd un sous-dossier de skins\. Défaut : nixie.

.PARAMETER KeepBanner
    N'écrit pas product.json. La bannière d'intégrité apparaîtra à chaque
    démarrage. À utiliser si tu préfères ne pas toucher au fichier.

.PARAMETER Force
    Ferme VS Code automatiquement au lieu de s'arrêter.

.PARAMETER RegisterLogonTask
    Crée une tâche planifiée qui rejoue l'installation à chaque ouverture de
    session, pour réappliquer le skin après une mise à jour de VS Code.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1
#>

[CmdletBinding()]
param(
    [string] $Skin = 'nixie',
    [string] $SpriteDir,
    [string] $CssFile,
    [string] $VSCodeRoot,
    [switch] $KeepBanner,
    [switch] $Force,
    [switch] $RegisterLogonTask,
    [switch] $Silent
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SkinDir  = Join-Path $RepoRoot "skins\$Skin"
if (-not $SpriteDir) { $SpriteDir = Join-Path $SkinDir 'sprites' }
if (-not $CssFile)   { $CssFile   = Join-Path $SkinDir 'css\pet.css' }
if (-not (Test-Path $SkinDir)) {
    $avail = (Get-ChildItem (Join-Path $RepoRoot 'skins') -Directory -EA SilentlyContinue).Name -join ', '
    Write-Host "  ECHEC : skin '$Skin' introuvable. Disponibles : $avail" -ForegroundColor Red
    exit 1
}

$StateDir  = Join-Path $env:USERPROFILE '.vscode-pet-skin'
$BackupDir = Join-Path $StateDir 'backups'
$Marker    = 'pet-skin'

function Say([string]$m, [string]$c = 'Gray') {
    if (-not $Silent) { Write-Host $m -ForegroundColor $c }
}
function Fail([string]$m) { Write-Host "  ECHEC : $m" -ForegroundColor Red; exit 1 }

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
if (-not $VSCodeRoot) {
    $candidates = @(
        'C:\Program Files\Microsoft VS Code',
        'C:\Program Files (x86)\Microsoft VS Code',
        (Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code')
    )
    $VSCodeRoot = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $VSCodeRoot) { Fail "Installation de VS Code introuvable. Passe -VSCodeRoot." }

# Les builds récents insèrent un dossier nommé d'après le hash du commit.
$base = $VSCodeRoot
$hashDir = Get-ChildItem $VSCodeRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName 'resources\app\out') } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($hashDir) { $base = $hashDir.FullName }

$Out       = Join-Path $base 'resources\app\out'
$PetDir    = Join-Path $Out  'vs\workbench\contrib\chat\browser\widget\media\chatPet'
$Workbench = Join-Path $Out  'vs\code\electron-browser\workbench\workbench.html'
$Product   = Join-Path $base 'resources\app\product.json'

foreach ($p in @($PetDir, $Workbench, $Product)) {
    if (-not (Test-Path $p)) { Fail "Introuvable : $p" }
}

Say '== Cible' 'Cyan'
Say "   skin   : $Skin"
Say "   racine : $VSCodeRoot"
if ($hashDir) { Say "   build  : $($hashDir.Name)" }

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

# --------------------------------------------------------------- sauvegarde
$stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$bk    = Join-Path $BackupDir $stamp
New-Item -ItemType Directory -Force -Path (Join-Path $bk 'chatPet') | Out-Null
Copy-Item (Join-Path $PetDir 'buddy-*.png') (Join-Path $bk 'chatPet') -Force
Copy-Item $Workbench (Join-Path $bk 'workbench.html') -Force
Copy-Item $Product   (Join-Path $bk 'product.json')   -Force
@{ Root = $VSCodeRoot; Base = $base } | ConvertTo-Json |
    Set-Content (Join-Path $bk 'paths.json') -Encoding UTF8
Set-Content (Join-Path $StateDir 'LAST_BACKUP.txt') $bk -Encoding UTF8
Say '== Sauvegarde' 'Cyan'
Say "   $bk"

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

# --------------------------------------------------------------- tâche
if ($RegisterLogonTask) {
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
