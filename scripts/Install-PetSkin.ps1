<#
.SYNOPSIS
    Installe un skin personnalisé pour le "pet" natif de VS Code (>= 1.131).

.DESCRIPTION
    Trois opérations, toutes réversibles :
      1. remplace les PNG du pet dans resources\app\out\...\media\chatPet
      2. injecte un bloc <style> dans workbench.html (repositionne et
         recolore les pupilles DOM)
      3. met à jour le checksum de workbench.html dans product.json, ce qui
         évite la bannière "Your Code installation appears corrupt"

    Le nombre de sprites, leurs noms et leurs dimensions ne sont pas codés en
    dur : ils sont lus dans le descripteur de format schema\formats\<id>.json,
    choisi d'après la version de VS Code installée. VS Code remanie ce format
    d'une version à l'autre (48 fichiers et frame toujours carrée en 1.132 ;
    82 fichiers, 21 états et des frames rectangulaires en 1.133).

    Tout est sauvegardé avant écriture dans %USERPROFILE%\.vscode-pet-skin\backups\<timestamp>.
    Le script est idempotent : si les sprites cibles sont déjà identiques aux
    sources et que le marqueur CSS est présent, il sort sans rien écrire ni
    sauvegarder.

.PARAMETER Skin
    Nom du skin à installer, càd un sous-dossier de skins\. S'il n'est pas
    fourni explicitement, le skin est lu dans
    %USERPROFILE%\.vscode-pet-skin\state.json (défaut : nixie).

.PARAMETER List
    Affiche les skins disponibles (nom, auteur, versions vérifiées) et sort.
    Ne demande aucune élévation.

.PARAMETER Format
    Force le descripteur de format à utiliser, par son id ou par le nom du
    fichier schema\formats\<id>.json (par exemple « 1.133 »). Sans ce
    paramètre, le descripteur est choisi d'après la version lue dans
    resources\app\package.json ; si aucun ne la déclare, le script avertit et
    prend le plus récent. Pour relever le format d'une nouvelle version :

        python tools\probe_format.py --out schema\formats\<version>.json

.PARAMETER KeepBackups
    Nombre de sauvegardes à conserver. Les plus anciennes sont supprimées
    après création de la nouvelle. Défaut : 5. 0 = illimité.

    Exception : les sauvegardes marquées « d'origine » — celles prises alors
    qu'aucun skin n'était encore posé, donc les seules à contenir le pet de
    Microsoft — ne sont jamais purgées, quel que soit le quota.

.PARAMETER LogFile
    Journal de la session élevée. Renseigné automatiquement lors de la
    relance en administrateur : la fenêtre élevée se referme aussitôt, sans
    ce transcript son résultat serait invisible.

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
    [string] $Format,
    [int]    $KeepBackups = 5,
    [string] $LogFile,
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
        if ($k -eq 'LogFile') { continue }
        $v = $PSBoundParameters[$k]
        if ($v -is [switch]) { if ($v) { $argList += "-$k" } }
        else { $argList += @("-$k", "`"$v`"") }
    }
    # Le skin resolu est transmis explicitement pour que la session elevee
    # cible exactement le meme skin.
    if (-not $PSBoundParameters.ContainsKey('Skin')) { $argList += @('-Skin', "`"$Skin`"") }

    # La fenetre elevee se referme des qu'elle a fini : sans journal, ni son
    # resultat ni ses messages ne sont visibles, et l'appelant (notamment
    # install.ps1 lance par `irm | iex`) annoncerait un succes sans rien savoir.
    # -Verb RunAs interdit -RedirectStandardOutput, d'ou le transcript.
    if (-not $LogFile) { $LogFile = Join-Path $StateDir 'last-run.log' }
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    $argList += @('-LogFile', "`"$LogFile`"")

    $proc = Start-Process powershell -Verb RunAs -ArgumentList $argList -Wait -PassThru
    $code = if ($null -ne $proc) { $proc.ExitCode } else { 1 }
    if ($code -ne 0) {
        Write-Host "  ECHEC : la session elevee est sortie en $code" -ForegroundColor Red
        if (Test-Path $LogFile) {
            Write-Host "  Dernieres lignes de $LogFile :" -ForegroundColor Red
            Get-Content $LogFile -Tail 20 | ForEach-Object { Write-Host "    $_" }
        }
    } else {
        Say "   session elevee terminee, journal : $LogFile" 'Green'
    }
    exit $code
}

# Session elevee : on journalise, la fenetre disparaitra sans laisser de trace.
if ($LogFile) {
    try { Start-Transcript -Path $LogFile -Force | Out-Null } catch { $null = $_ }
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

# --------------------------------------------------------------- format
# Le format des sprites depend de la version de VS Code installee : on lit la
# version puis on choisit le descripteur qui la declare. Sans correspondance,
# on avertit et on tente le plus recent plutot que de bloquer.
$vscodeVersion = $null
$pkg = Join-Path $base 'resources\app\package.json'
if (Test-Path $pkg) {
    try { $vscodeVersion = (Get-Content $pkg -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json).version }
    catch { $vscodeVersion = $null }
}

$formatDir = Join-Path $RepoRoot 'schema\formats'
$fmtArgs = @{ FormatDir = $formatDir }
if ($Format)        { $fmtArgs['Id'] = $Format }
if ($vscodeVersion) { $fmtArgs['VSCodeVersion'] = $vscodeVersion }
$fmt = Get-PetFormat @fmtArgs
if (-not $fmt) { Fail "aucun descripteur de format lisible dans $formatDir" }
if (-not $fmt.Path) {
    foreach ($w in $fmt.Warnings) { Write-Host "  ECHEC : $w" -ForegroundColor Red }
    exit 1
}
foreach ($w in $fmt.Warnings) { Say "   AVERTISSEMENT : $w" 'Yellow' }

Say '== Format' 'Cyan'
if ($vscodeVersion) { Say "   version de VS Code : $vscodeVersion" }
else { Say '   version de VS Code indeterminee (package.json illisible)' 'Yellow' }
$forced = if ($Format) { ' (impose par -Format)' } else { '' }
Say "   descripteur : $($fmt.Id)$forced"
Say "   $($fmt.StateCount) etats, $($fmt.FileCount) fichiers attendus"

# --------------------------------------------------------------- contrôles
# Get-PngSize vit dans _Common.ps1 : sa version naive se trompait sur toute
# image de plus de 255 px de large (cf. le commentaire de la fonction).
# Aucun nombre n'est code en dur ici : Test-SpriteSet confronte le dossier au
# descripteur (noms attendus, dimensions de frame et de planche, fichiers en
# trop) puis compare chaque source a son homologue dans la cible.

Say '== Controle d''integrite des sources' 'Cyan'
$problems = @(Test-SpriteSet -SpriteDir $SpriteDir -Format $fmt -PetDir $PetDir)
if ($problems) {
    Write-Host "   Anomalies ($($problems.Count)) :" -ForegroundColor Red
    $problems | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
    Fail 'aucune ecriture effectuee.'
}
$src = @(Get-ChildItem (Join-Path $SpriteDir 'buddy-*.png') -ErrorAction SilentlyContinue)
Say "   $($fmt.FileCount)/$($fmt.FileCount) OK (noms, dimensions, homologues)"

# --------------------------------------------------------------- garde-fou de version
# skin.json declare les versions de VS Code sur lesquelles le skin a ete
# verifie : on avertit sans bloquer si la version installee n'y figure pas.
$skinMeta = $null
$skinJson = Join-Path $SkinDir 'skin.json'
if (Test-Path $skinJson) {
    try { $skinMeta = Get-Content $skinJson -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json }
    catch { $skinMeta = $null }
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
# Rien a faire si les cibles sont deja identiques aux sources et que le
# marqueur CSS est present : on sort avant toute ecriture et toute sauvegarde
# (la tache planifiee rejoue l'install a chaque ouverture de session). Le
# nombre attendu vient du descripteur : un compte fige ferait recreer une
# sauvegarde a chaque ouverture de session.
if (Test-SkinApplied -SpriteDir $SpriteDir -PetDir $PetDir -Workbench $Workbench -Marker $Marker -Format $fmt) {
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
# Une sauvegarde est « d'origine » si le marqueur CSS etait absent avant
# ecriture : ce qu'elle contient est alors le pet de Microsoft, pas un skin
# precedent. C'est la seule qui permette un retour a l'etat initial.
$pristine = -not ($htmlProbe -match [regex]::Escape("<!-- $Marker`:start -->"))
@{ Root = $VSCodeRoot; Base = $base; Commit = $build.Commit; Version = $vscodeVersion
   Pristine = $pristine; Skin = $Skin; Format = $fmt.Id } |
    ConvertTo-Json | Set-Content (Join-Path $bk 'paths.json') -Encoding UTF8
if ($pristine) { Say '   sauvegarde d''origine (pet de Microsoft), protegee de la purge' 'Green' }
Set-Content (Join-Path $StateDir 'LAST_BACKUP.txt') $bk -Encoding UTF8
Say '== Sauvegarde' 'Cyan'
Say "   $bk"

# ---- rétention : on ne garde que les N plus recentes (nom = timestamp triable)
# Les sauvegardes d'origine ne sont JAMAIS purgees : ce sont les seules qui
# contiennent le pet de Microsoft. Les supprimer rendrait la desinstallation
# incapable de revenir a l'etat initial, alors que c'est ce qu'elle promet.
if ($KeepBackups -gt 0) {
    $olds = @(Get-ChildItem $BackupDir -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -Skip $KeepBackups)
    $purged, $kept = 0, 0
    foreach ($o in $olds) {
        $meta = $null
        $mf = Join-Path $o.FullName 'paths.json'
        if (Test-Path $mf) {
            try { $meta = Get-Content $mf -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json }
            catch { $meta = $null }
        }
        if ($meta -and $meta.Pristine) {
            $kept++
            Say "   conservee (sauvegarde d'origine) : $($o.Name)"
            continue
        }
        Remove-Item $o.FullName -Recurse -Force -ErrorAction SilentlyContinue
        $purged++
        Say "   purge : $($o.Name)"
    }
    if ($purged) { Say "   $purged ancienne(s) sauvegarde(s) supprimee(s), $KeepBackups conservee(s)" }
    if ($kept)   { Say "   $kept sauvegarde(s) d'origine conservee(s) hors quota" }
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
Say "   $($src.Count) fichiers copies, verifies par SHA256"

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
