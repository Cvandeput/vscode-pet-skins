<#
.SYNOPSIS
    Bootstrap en une commande pour vscode-pet-skins.

.DESCRIPTION
    Conçu pour être exécuté directement depuis le web :

        irm https://raw.githubusercontent.com/Cvandeput/vscode-pet-skins/main/install.ps1 | iex

    Le script clone (ou met à jour) le dépôt dans un dossier local, puis
    enchaîne sur scripts\Install-PetSkin.ps1.

    Comme `iex` reçoit du texte et non un fichier, un bloc param() n'y est pas
    utilisable : tout se règle par variables d'environnement.

      PETSKIN_SKIN       nom du skin                  (défaut : nixie)
      PETSKIN_DIR        dossier de clone             (défaut : %LOCALAPPDATA%\vscode-pet-skins)
      PETSKIN_REF        branche ou tag à récupérer   (défaut : main)
      PETSKIN_ARGS       arguments supplémentaires passés tels quels à
                         Install-PetSkin.ps1, ex. "-Force -KeepBanner"
      PETSKIN_YES=1      saute le délai d'annulation de 5 secondes
      PETSKIN_NOINSTALL=1  s'arrête juste après le clone, sans rien installer
                           (garde-fou pour la CI et les tests)

.EXAMPLE
    $env:PETSKIN_ARGS = '-Force'
    irm https://raw.githubusercontent.com/Cvandeput/vscode-pet-skins/main/install.ps1 | iex
#>

$ErrorActionPreference = 'Stop'

# ---- réglages (variables d'environnement uniquement, cf. note sur iex)
$RepoUrl = 'https://github.com/Cvandeput/vscode-pet-skins.git'

$Skin = $env:PETSKIN_SKIN
if (-not $Skin) { $Skin = 'nixie' }

$Ref = $env:PETSKIN_REF
if (-not $Ref) { $Ref = 'main' }

$Dir = $env:PETSKIN_DIR
if (-not $Dir) { $Dir = Join-Path $env:LOCALAPPDATA 'vscode-pet-skins' }

$ExtraArgs = @()
if ($env:PETSKIN_ARGS) {
    $ExtraArgs = $env:PETSKIN_ARGS -split '\s+' | Where-Object { $_ }
}

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Fail([string]$m) { Write-Host "  ECHEC : $m" -ForegroundColor Red; exit 1 }

# ---- en-tête et avertissement
Say ''
Say '=============================================================' 'Cyan'
Say ' vscode-pet-skins - installation en une commande' 'Cyan'
Say '=============================================================' 'Cyan'
Say ''
Say ' Ce script modifie ton installation de VS Code :' 'Yellow'
Say '   - remplace 48 PNG du pet dans resources\app\out\...\chatPet' 'Yellow'
Say '   - injecte un bloc <style> dans workbench.html' 'Yellow'
Say '   - recalcule le checksum correspondant dans product.json' 'Yellow'
Say '   - demande une elevation UAC (invite Windows)' 'Yellow'
Say ''
Say ' Tout est sauvegarde avant ecriture dans' 'Gray'
Say '   %USERPROFILE%\.vscode-pet-skin\backups\<horodatage>' 'Gray'
Say ' et entierement reversible via scripts\Uninstall-PetSkin.ps1.' 'Gray'
Say ''
Say " skin   : $Skin"
Say " dossier: $Dir"
Say " ref    : $Ref"
if ($ExtraArgs.Count) { Say " args   : $($ExtraArgs -join ' ')" }
Say ''

if ([Environment]::UserInteractive -and $env:PETSKIN_YES -ne '1') {
    Say ' Demarrage dans 5 secondes -- Ctrl+C pour annuler.' 'Yellow'
    Start-Sleep -Seconds 5
    Say ''
}

# ---- prerequis : git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Say '  ECHEC : git est introuvable dans le PATH.' 'Red'
    Say ''
    Say '  Deux solutions :' 'Yellow'
    Say '    1. installer git, puis relancer cette commande :' 'Yellow'
    Say '         winget install --id Git.Git -e' 'Gray'
    Say '       (ou https://git-scm.com/download/win)' 'Gray'
    Say '    2. telecharger le zip du depot a la main :' 'Yellow'
    Say '         https://github.com/Cvandeput/vscode-pet-skins/archive/refs/heads/main.zip' 'Gray'
    Say '       le decompresser, puis lancer depuis le dossier extrait :' 'Yellow'
    Say '         powershell -ExecutionPolicy Bypass -File .\scripts\Install-PetSkin.ps1' 'Gray'
    exit 1
}

# ---- clone ou mise a jour
Say '== Depot' 'Cyan'

if (Test-Path $Dir) {
    if (-not (Test-Path (Join-Path $Dir '.git'))) {
        Say "  ECHEC : $Dir existe deja mais n'est pas un depot git." 'Red'
        Say '  Rien n a ete supprime. Choisis un autre dossier :' 'Yellow'
        Say '    $env:PETSKIN_DIR = ''C:\chemin\vers\un\autre\dossier''' 'Gray'
        Say '  ou supprime celui-ci toi-meme s il ne sert a rien.' 'Yellow'
        exit 1
    }

    Say "   mise a jour de $Dir"
    & git -C $Dir fetch --depth 1 origin $Ref
    if ($LASTEXITCODE -ne 0) { Fail "git fetch a echoue (code $LASTEXITCODE). Verifie ta connexion et que la ref '$Ref' existe." }

    # ecrase les modifications locales du clone gere par ce script
    & git -C $Dir reset --hard FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { Fail "git reset --hard a echoue (code $LASTEXITCODE)." }

    Say "   a jour sur $Ref"
} else {
    Say "   clone de $RepoUrl"
    & git clone --depth 1 --branch $Ref $RepoUrl $Dir
    if ($LASTEXITCODE -ne 0) { Fail "git clone a echoue (code $LASTEXITCODE). Verifie ta connexion et que la ref '$Ref' existe." }
    Say "   clone dans $Dir"
}

$Installer = Join-Path $Dir 'scripts\Install-PetSkin.ps1'
if (-not (Test-Path $Installer)) { Fail "Installateur introuvable : $Installer" }

# ---- garde-fou CI / tests
if ($env:PETSKIN_NOINSTALL -eq '1') {
    Say ''
    Say '== PETSKIN_NOINSTALL=1 : arret avant l installation' 'Yellow'
    Say "   depot pret dans $Dir"
    Say "   pour installer : powershell -NoProfile -ExecutionPolicy Bypass -File `"$Installer`" -Skin $Skin"
    exit 0
}

# ---- installation
Say ''
Say '== Installation' 'Cyan'
$argList = @('-NoProfile','-ExecutionPolicy','Bypass','-File', $Installer, '-Skin', $Skin) + $ExtraArgs
& powershell @argList
$code = $LASTEXITCODE

# ---- recapitulatif
Say ''
Say '=============================================================' 'Green'
Say " Depot         : $Dir" 'Green'
Say " Desinstaller  : powershell -ExecutionPolicy Bypass -File `"$Dir\scripts\Uninstall-PetSkin.ps1`"" 'Green'
Say " Relancer      : irm https://raw.githubusercontent.com/Cvandeput/vscode-pet-skins/main/install.ps1 | iex" 'Green'
Say ' Dans VS Code  : tape /vscode-pet dans le chat.' 'Green'
Say '=============================================================' 'Green'

exit $code
