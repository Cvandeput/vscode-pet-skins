<#
.SYNOPSIS
    Restaure les sprites, workbench.html et product.json d'origine.

.PARAMETER ListBackups
    Affiche les sauvegardes disponibles et sort.

.PARAMETER Timestamp
    Restaure une sauvegarde précise. Par défaut, la plus récente.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Uninstall-PetSkin.ps1
#>

[CmdletBinding()]
param(
    [switch] $ListBackups,
    [string] $Timestamp,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
$StateDir  = Join-Path $env:USERPROFILE '.vscode-pet-skin'
$BackupDir = Join-Path $StateDir 'backups'

function Fail([string]$m) { Write-Host "  ECHEC : $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $BackupDir)) { Fail "Aucune sauvegarde dans $BackupDir" }

$all = Get-ChildItem $BackupDir -Directory | Sort-Object Name -Descending
if ($ListBackups) {
    Write-Host 'Sauvegardes disponibles :' -ForegroundColor Cyan
    $all | ForEach-Object { Write-Host "   $($_.Name)" }
    exit
}
if (-not $all) { Fail 'Aucune sauvegarde.' }

$bk = if ($Timestamp) {
    $m = $all | Where-Object Name -eq $Timestamp
    if (-not $m) { Fail "Sauvegarde $Timestamp introuvable." }
    $m.FullName
} else { $all[0].FullName }

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $a = @('-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    if ($Timestamp) { $a += @('-Timestamp', $Timestamp) }
    if ($Force)     { $a += '-Force' }
    Start-Process powershell -Verb RunAs -ArgumentList $a
    exit
}

$running = Get-Process -Name Code -ErrorAction SilentlyContinue
if ($running) {
    if ($Force) { $running | Stop-Process -Force; Start-Sleep 2 }
    else { Fail 'VS Code est ouvert. Ferme-le, ou relance avec -Force.' }
}

$paths = Get-Content (Join-Path $bk 'paths.json') -Raw | ConvertFrom-Json
$base  = $paths.Base
$Out   = Join-Path $base 'resources\app\out'
$PetDir    = Join-Path $Out  'vs\workbench\contrib\chat\browser\widget\media\chatPet'
$Workbench = Join-Path $Out  'vs\code\electron-browser\workbench\workbench.html'
$Product   = Join-Path $base 'resources\app\product.json'

Write-Host "== Restauration depuis $bk" -ForegroundColor Cyan

Copy-Item (Join-Path $bk 'chatPet\buddy-*.png') $PetDir -Force
Copy-Item (Join-Path $bk 'workbench.html') $Workbench -Force
Copy-Item (Join-Path $bk 'product.json')   $Product   -Force

$bad = 0
Get-ChildItem (Join-Path $bk 'chatPet\buddy-*.png') | ForEach-Object {
    $a = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    $b = (Get-FileHash (Join-Path $PetDir $_.Name) -Algorithm SHA256).Hash
    if ($a -ne $b) { $bad++ }
}
if ($bad) { Fail "$bad fichiers restaures ne correspondent pas." }

Unregister-ScheduledTask -TaskName 'vscode-pet-skin' -Confirm:$false -ErrorAction SilentlyContinue

Write-Host '   48 sprites, workbench.html et product.json restaures' -ForegroundColor Green
Write-Host '   tache planifiee supprimee si elle existait' -ForegroundColor Green
Write-Host '   Relance VS Code.' -ForegroundColor Green
