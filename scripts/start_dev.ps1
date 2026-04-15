[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $projectRoot "frontend"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envFile = Join-Path $projectRoot ".env"

function Assert-PathExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $LiteralPath)) {
        throw "Missing ${Description}: $LiteralPath"
    }
}

function Assert-CommandExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Command not found: $CommandName"
    }
}

function ConvertTo-SingleQuotedLiteral {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return $Value.Replace("'", "''")
}

function Test-PortOccupied {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return ($listeners | Measure-Object).Count -gt 0
    }
    catch {
        return $false
    }
}

Assert-PathExists -LiteralPath $venvPython -Description "virtualenv Python"
Assert-PathExists -LiteralPath $frontendRoot -Description "frontend directory"
Assert-PathExists -LiteralPath $envFile -Description "root .env file"
Assert-CommandExists -CommandName "npm"
Assert-CommandExists -CommandName "powershell.exe"

if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    throw "Missing frontend\\node_modules. Run 'cd frontend; npm install' first."
}

Write-Host "Project root: $projectRoot"
Write-Host "Backend URL : http://127.0.0.1:8000"
Write-Host "Frontend URL: http://127.0.0.1:5173"

if ($DryRun) {
    Write-Host ""
    Write-Host "[DryRun] Backend command:"
    Write-Host "powershell.exe -NoExit -Command <backend command>"
    Write-Host ""
    Write-Host "[DryRun] Frontend command:"
    Write-Host "powershell.exe -NoExit -Command <frontend command>"
    exit 0
}

$launchBackend = -not (Test-PortOccupied -Port 8000)
$launchFrontend = -not (Test-PortOccupied -Port 5173)

$quotedProjectRoot = ConvertTo-SingleQuotedLiteral -Value $projectRoot
$quotedFrontendRoot = ConvertTo-SingleQuotedLiteral -Value $frontendRoot
$quotedVenvPython = ConvertTo-SingleQuotedLiteral -Value $venvPython

$backendCommand = @"
`$Host.UI.RawUI.WindowTitle = 'Atlas Backend'
Set-Location '$quotedProjectRoot'
& '$quotedVenvPython' -m uvicorn app.main:app --reload --app-dir '.\backend'
"@

$frontendCommand = @"
`$Host.UI.RawUI.WindowTitle = 'Atlas Frontend'
Set-Location '$quotedFrontendRoot'
npm run dev
"@

if (-not $launchBackend) {
    Write-Warning "Port 8000 is already in use. Skipping backend startup."
}

if (-not $launchFrontend) {
    Write-Warning "Port 5173 is already in use. Skipping frontend startup."
}

if (-not $launchBackend -and -not $launchFrontend) {
    Write-Host ""
    Write-Host "Both frontend and backend already appear to be running."
    exit 0
}

if ($launchBackend) {
    Start-Process powershell.exe -WorkingDirectory $projectRoot -ArgumentList @(
        "-NoExit",
        "-Command",
        $backendCommand
    )
}

if ($launchBackend -and $launchFrontend) {
    Start-Sleep -Seconds 2
}

if ($launchFrontend) {
    Start-Process powershell.exe -WorkingDirectory $frontendRoot -ArgumentList @(
        "-NoExit",
        "-Command",
        $frontendCommand
    )
}

Write-Host ""
Write-Host "Startup windows created."
Write-Host "Backend window : Atlas Backend"
Write-Host "Frontend window: Atlas Frontend"
