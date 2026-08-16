<#
.SYNOPSIS
    Restaure les sprites, workbench.html et product.json d'origine.

.DESCRIPTION
    La désinstallation re-localise elle-même le build courant de VS Code
    (même logique que l'installation) ; le fichier paths.json de la
    sauvegarde ne sert plus qu'en secours. Si le build d'où provient la
    sauvegarde a disparu — cas classique après une mise à jour de VS Code,
    qui a déjà réinstallé les fichiers d'origine — le script le dit et sort
    normalement, après avoir supprimé la tâche planifiée.

    La restauration ne suppose aucun nombre de sprites : elle remet tout ce
    que la sauvegarde contient (celle-ci a été prise au joker buddy-*.png).
    Le format relevé au moment de la sauvegarde est noté dans son paths.json,
    à titre indicatif.

.PARAMETER ListBackups
    Affiche les sauvegardes disponibles et sort.

.PARAMETER Timestamp
    Restaure une sauvegarde précise.

    Par défaut, le script restaure la plus récente sauvegarde « d'origine »,
    c'est-à-dire prise avant qu'un skin ne soit posé : c'est la seule qui
    ramène le pet de Microsoft. La plus récente tout court peut ne contenir
    qu'un skin précédent, si tu en as changé. -ListBackups les affiche toutes.

.PARAMETER VSCodeRoot
    Force la racine d'installation de VS Code au lieu de la détecter.

.PARAMETER Force
    Ferme VS Code automatiquement au lieu de s'arrêter.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Uninstall-PetSkin.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Uninstall-PetSkin.ps1 -ListBackups
#>

[CmdletBinding()]
param(
    [switch] $ListBackups,
    [string] $Timestamp,
    [string] $VSCodeRoot,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
$StateDir  = Join-Path $env:USERPROFILE '.vscode-pet-skin'
$BackupDir = Join-Path $StateDir 'backups'
$TaskName  = 'vscode-pet-skin'

. (Join-Path $PSScriptRoot '_Common.ps1')

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Fail([string]$m) { Write-Host "  ECHEC : $m" -ForegroundColor Red; exit 1 }

# --------------------------------------------------------------- sauvegardes
if (-not (Test-Path $BackupDir)) { Fail "Aucune sauvegarde dans $BackupDir" }

$all = @(Get-ChildItem $BackupDir -Directory | Sort-Object Name -Descending)
if ($ListBackups) {
    Say 'Sauvegardes disponibles :' 'Cyan'
    $all | ForEach-Object { Write-Host "   $($_.Name)" }
    exit 0
}
if (-not $all) { Fail 'Aucune sauvegarde.' }

function Get-BackupMeta([string]$dir) {
    $f = Join-Path $dir 'paths.json'
    if (-not (Test-Path $f)) { return $null }
    try { return (Get-Content $f -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json) }
    catch { return $null }
}

# Desinstaller veut dire « revenir au pet d'origine ». La sauvegarde la plus
# recente peut tres bien contenir un skin precedent (cas d'un changement de
# skin) : on prefere donc la plus recente marquee Pristine, qui contient les
# fichiers de Microsoft. -Timestamp permet toujours de viser autre chose.
$bk = if ($Timestamp) {
    $m = $all | Where-Object Name -eq $Timestamp
    if (-not $m) { Fail "Sauvegarde $Timestamp introuvable." }
    $m.FullName
} else {
    $orig = $all | Where-Object { (Get-BackupMeta $_.FullName).Pristine } | Select-Object -First 1
    if ($orig) { $orig.FullName } else { $all[0].FullName }
}

# --------------------------------------------------------------- élévation
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $a = @('-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    # La sauvegarde choisie est transmise telle quelle : sans cela la session
    # elevee refait le choix, et pourrait ne pas retomber sur la meme.
    $a += @('-Timestamp', (Split-Path -Leaf $bk))
    if ($VSCodeRoot) { $a += @('-VSCodeRoot', "`"$VSCodeRoot`"") }
    if ($Force)      { $a += '-Force' }
    # -Wait : sans lui, la fenetre elevee est detachee et ce script sortirait
    # en 0 sans savoir si la restauration a reussi.
    $proc = Start-Process powershell -Verb RunAs -ArgumentList $a -Wait -PassThru
    $code = if ($null -ne $proc) { $proc.ExitCode } else { 1 }
    if ($code -ne 0) { Write-Host "  ECHEC : la session elevee est sortie en $code" -ForegroundColor Red }
    exit $code
}

# --------------------------------------------------------------- localisation
# paths.json fige le build de l'epoque : il ne sert que de secours, on
# re-localise le build courant comme le fait l'installateur.
$saved = $null
$pathsFile = Join-Path $bk 'paths.json'
if (Test-Path $pathsFile) {
    try { $saved = Get-Content $pathsFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json }
    catch { $saved = $null }
}

$root = Get-VSCodeRootPath -Explicit $VSCodeRoot
if (-not $root -and $saved -and $saved.Root -and (Test-Path $saved.Root)) { $root = $saved.Root }
if (-not $root) { Fail "Installation de VS Code introuvable. Passe -VSCodeRoot." }

$build = Resolve-VSCodeBuild -VSCodeRoot $root
$base  = if ($build) { $build.Base } else { $null }

Say "== Restauration depuis $bk" 'Cyan'
if ($saved -and $saved.Pristine) {
    Say '   sauvegarde d''origine : retour au pet de Microsoft' 'Green'
} elseif (-not $Timestamp) {
    Say '   AVERTISSEMENT : aucune sauvegarde d''origine trouvee, restauration de' 'Yellow'
    Say '                   l''etat precedent. -ListBackups pour en choisir une autre.' 'Yellow'
}
if ($build) {
    foreach ($w in $build.Warnings) { Say "   AVERTISSEMENT : $w" 'Yellow' }
}

# ---- la sauvegarde correspond-elle encore au build installe ?
$savedLabel = if ($saved -and $saved.Commit) { $saved.Commit }
              elseif ($saved -and $saved.Base) { Split-Path -Leaf $saved.Base }
              else { '(inconnu)' }

$stale = $false
if (-not $base) {
    $stale = $true
} elseif ($saved -and $saved.Commit -and $build.Commit -and $saved.Commit -ne $build.Commit) {
    $stale = $true
} elseif ($saved -and $saved.Base -and -not (Test-Path $saved.Base) -and $saved.Base -ne $base) {
    $stale = $true
}

if (-not $stale) {
    $p = Get-PetPaths -Base $base
    if (-not (Test-Path $p.PetDir) -or -not (Test-Path $p.Workbench)) { $stale = $true }
}

if ($stale) {
    Say "   cette sauvegarde vient du build $savedLabel, absent ; la mise a jour de VS Code" 'Yellow'
    Say "   a deja restaure les fichiers d'origine, rien a faire" 'Yellow'
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Say '   tache planifiee supprimee si elle existait' 'Green'
    exit 0
}

$paths     = Get-PetPaths -Base $base
$PetDir    = $paths.PetDir
$Workbench = $paths.Workbench
$Product   = $paths.Product
if ($build.Commit) { Say "   build cible : $($build.Commit)" }
if ($saved -and $saved.Format) { Say "   format releve a la sauvegarde : $($saved.Format)" }

# --------------------------------------------------------------- VS Code fermé
$running = Get-Process -Name Code -ErrorAction SilentlyContinue
if ($running) {
    if ($Force) { $running | Stop-Process -Force; Start-Sleep 2 }
    else { Fail 'VS Code est ouvert. Ferme-le, ou relance avec -Force.' }
}

# --------------------------------------------------------------- restauration
# La sauvegarde a ete prise au joker buddy-*.png : on restaure exactement ce
# qu'elle contient, quel qu'en soit le nombre. Aucun compte n'est suppose ici
# — le format de VS Code change d'une version a l'autre (48 fichiers en 1.132,
# 82 en 1.133) et la sauvegarde fait foi.
$saved_sprites = @(Get-ChildItem (Join-Path $bk 'chatPet\buddy-*.png') -ErrorAction SilentlyContinue)
if (-not $saved_sprites) { Fail "aucun sprite dans $bk\chatPet, sauvegarde inexploitable." }

Copy-Item (Join-Path $bk 'chatPet\buddy-*.png') $PetDir -Force
Copy-Item (Join-Path $bk 'workbench.html') $Workbench -Force
if (Test-Path $Product) { Copy-Item (Join-Path $bk 'product.json') $Product -Force }

$bad = 0
foreach ($f in $saved_sprites) {
    $dest = Join-Path $PetDir $f.Name
    if (-not (Test-Path $dest)) { $bad++; Say "   non restaure : $($f.Name)" 'Red'; continue }
    $a = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    $b = (Get-FileHash $dest       -Algorithm SHA256).Hash
    if ($a -ne $b) { $bad++; Say "   different de la sauvegarde : $($f.Name)" 'Red' }
}
if ($bad) { Fail "$bad fichiers restaures ne correspondent pas." }

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# L'etat n'a plus de skin actif.
$stateFile = Join-Path $StateDir 'state.json'
if (Test-Path $stateFile) { Remove-Item $stateFile -Force -ErrorAction SilentlyContinue }

Say "   $($saved_sprites.Count) sprites, workbench.html et product.json restaures" 'Green'
Say '   tache planifiee supprimee si elle existait' 'Green'
Say '   Relance VS Code.' 'Green'
