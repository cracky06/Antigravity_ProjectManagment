<#
.SYNOPSIS
    Script de release et de versioning Git automatique pour Antigravity Manager.
.DESCRIPTION
    Calcule la prochaine version (MAJOR.MINOR), crée un tag Git annoté (ex: V1.67) et affiche les commandes de publication.
.PARAMETER Type
    Type d'incrément de version : 'minor' (ex: 1.66 -> 1.67) ou 'major' (ex: 1.67 -> 2.0).
.PARAMETER Message
    Message optionnel pour annoter le tag de release.
.PARAMETER Push
    Si spécifié, pousse automatiquement le commit et les tags vers le dépôt distant.
.EXAMPLE
    .\scripts\release.ps1 minor
.EXAMPLE
    .\scripts\release.ps1 major -Message "Refonte complète"
#>
[CmdletBinding()]
param (
    [Parameter(Position = 0, Mandatory = $false)]
    [ValidateSet("minor", "major")]
    [string]$Type = "minor",

    [Parameter(Mandatory = $false)]
    [string]$Message = "",

    [Parameter(Mandatory = $false)]
    [switch]$Push
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Split-Path -Parent $ScriptDir
Set-Location -Path $RootDir

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Antigravity Manager - Release & Tagging    " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Vérification du statut Git
$GitStatus = & git status --porcelain
if ($GitStatus) {
    Write-Host "`n[AVERTISSEMENT] Des modifications non commitees sont detectees." -ForegroundColor Yellow
}

# 2. Récupération du dernier tag existant
$LatestTag = & git describe --tags --abbrev=0 2>$null
$CurrentMajor = 1
$CurrentMinor = 0

if ($LatestTag -match '^[vV]?(\d+)\.(\d+)$') {
    $CurrentMajor = [int]$Matches[1]
    $CurrentMinor = [int]$Matches[2]
    Write-Host "Derniere version detectee : V$CurrentMajor.$CurrentMinor (Tag: $LatestTag)" -ForegroundColor Gray
}
else {
    Write-Host "Aucun tag de version existant detecte. Demarrage a partir de V1.0." -ForegroundColor Gray
}

# 3. Calcul de la nouvelle version
if ($Type.ToLower() -eq "major") {
    $NewMajor = $CurrentMajor + 1
    $NewMinor = 0
}
else {
    $NewMajor = $CurrentMajor
    $NewMinor = $CurrentMinor + 1
}

$NewVersion = "$NewMajor.$NewMinor"
$TagName = "V$NewVersion"

Write-Host "`nNouvelle version a creer : $TagName (Type: $Type)" -ForegroundColor Green

# 4. Création du tag Git
$TagMessage = if ($Message) { "Release $TagName - $Message" } else { "Release $TagName" }
Write-Host "Creation du tag Git $TagName..." -ForegroundColor Yellow

& git tag -a "$TagName" -m "$TagMessage"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nTag $TagName cree avec succes !" -ForegroundColor Green
}
else {
    Write-Host "`nErreur lors de la creation du tag." -ForegroundColor Red
    exit $LASTEXITCODE
}

# 5. Push vers remote si demandé
if ($Push) {
    Write-Host "Envoi des tags vers le depot distant (git push origin $TagName)..." -ForegroundColor Yellow
    & git push origin "$TagName"
}
else {
    Write-Host "`nPour publier ce tag sur GitHub, executez :" -ForegroundColor Cyan
    Write-Host "  git push origin $TagName" -ForegroundColor White
}
