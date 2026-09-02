<#
.SYNOPSIS
    Script de compilation et de distribution d'Antigravity Manager.
.DESCRIPTION
    Nettoie les anciens artefacts, vérifie les dépendances et génère un exécutable autonome (.exe) avec PyInstaller.
.PARAMETER CleanOnly
    Si spécifié, nettoie uniquement les dossiers build et dist sans compiler.
.PARAMETER OneDir
    Si spécifié, génère un dossier avec dépendances au lieu d'un unique fichier .exe.
#>
[CmdletBinding()]
param (
    [switch]$CleanOnly,
    [switch]$OneDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location -Path $ScriptDir

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Antigravity Manager - Script de Build      " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Nettoyage
Write-Host "`n[1/3] Nettoyage des anciens builds..." -ForegroundColor Yellow

Get-Process -Name "AntigravityManager" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  Fermeture de l'instance active d'AntigravityManager (PID: $($_.Id))..." -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
}

$DirectoriesToClean = @("build", "dist")
foreach ($Dir in $DirectoriesToClean) {
    $Target = Join-Path -Path $ScriptDir -ChildPath $Dir
    if (Test-Path -Path $Target) {
        Write-Host "  Suppression de $Dir..." -ForegroundColor Gray
        Remove-Item -Path $Target -Recurse -Force
    }
}

Get-ChildItem -Path $ScriptDir -Filter "*.spec" | ForEach-Object {
    Write-Host "  Suppression de $($_.Name)..." -ForegroundColor Gray
    Remove-Item -Path $_.FullName -Force
}

if ($CleanOnly) {
    Write-Host "`nNettoyage termine avec succes." -ForegroundColor Green
    return
}

# 2. Verification de l'environnement Python
Write-Host "`n[2/3] Verification de l'environnement Python..." -ForegroundColor Yellow

$VenvPython = Join-Path -Path $ScriptDir -ChildPath ".venv\Scripts\python.exe"
$VenvPyInstaller = Join-Path -Path $ScriptDir -ChildPath ".venv\Scripts\pyinstaller.exe"

$PythonCmd = if (Test-Path -Path $VenvPython) { $VenvPython } else { "python" }
$PyInstallerCmd = if (Test-Path -Path $VenvPyInstaller) { $VenvPyInstaller } else { "pyinstaller" }

Write-Host "  Interpreteur : $PythonCmd" -ForegroundColor Gray

try {
    & $PythonCmd -c "import PyQt6, PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Installation des dependances requises..." -ForegroundColor Gray
        & $PythonCmd -m pip install -r requirements.txt
    }
    else {
        Write-Host "  Dependances detectees (PyQt6, PyInstaller)." -ForegroundColor Green
    }
}
catch {
    Write-Host "Erreur lors de la verification des dependances: $_" -ForegroundColor Red
    exit 1
}

# 3. Compilation PyInstaller
Write-Host "`n[3/3] Compilation avec PyInstaller..." -ForegroundColor Yellow

$PyInstallerArgs = @(
    "--noconfirm",
    "--windowed",
    "--name", "AntigravityManager",
    "antigravity_manager.py"
)

if (-not $OneDir) {
    $PyInstallerArgs += "--onefile"
}

Write-Host "  Execution de $PyInstallerCmd..." -ForegroundColor Gray
& $PyInstallerCmd @PyInstallerArgs

if ($LASTEXITCODE -eq 0) {
    $ExePath = Join-Path -Path $ScriptDir -ChildPath "dist\AntigravityManager.exe"
    Write-Host "`n=============================================" -ForegroundColor Green
    Write-Host "  BUILD REUSSI !" -ForegroundColor Green
    if (Test-Path -Path $ExePath) {
        $SizeMB = [math]::Round((Get-Item -Path $ExePath).Length / 1MB, 2)
        Write-Host "  Executable : $ExePath ($SizeMB Mo)" -ForegroundColor Green
    }
    Write-Host "=============================================" -ForegroundColor Green
}
else {
    Write-Host "`nEchec du build PyInstaller." -ForegroundColor Red
    exit $LASTEXITCODE
}
