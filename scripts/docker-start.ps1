<#
.SYNOPSIS
    Sobe o Docker Desktop no host Windows e espera o daemon ficar pronto.

.DESCRIPTION
    Rode no terminal do HOST (Windows PowerShell), NAO dentro do devcontainer:
    sem daemon nao existe container de onde chamar isto (ovo e galinha).

    Idempotente — se o daemon ja responde, sai imediatamente sem fazer nada.

    Motivacao: nesta maquina o Docker Desktop esta com "Start Docker Desktop
    when you sign in" DESLIGADO (AutoStart=False), entao ele nao volta sozinho
    depois de um shutdown/reboot. Sem daemon, o "Dev Containers: Reopen/Rebuild
    in Container" do VS Code falha silenciosamente ("nao carrega").

    Compativel com Windows PowerShell 5.1 (nao requer pwsh 7).

.PARAMETER TimeoutSeconds
    Quanto esperar o daemon responder antes de desistir. Default: 180.

.PARAMETER Up
    Depois que o daemon subir, tambem roda `docker compose up -d`.

.EXAMPLE
    .\scripts\docker-start.ps1

.EXAMPLE
    .\scripts\docker-start.ps1 -Up

.EXAMPLE
    .\scripts\docker-start.ps1 -TimeoutSeconds 240
#>
[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 180,
    [switch]$Up
)

function Test-DockerDaemon {
    # Native exe: exit code e a fonte de verdade. Silencia stderr para nao
    # poluir o console enquanto o daemon ainda esta subindo.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    return $ok
}

if (Test-DockerDaemon) {
    Write-Host "Docker daemon ja esta rodando." -ForegroundColor Green
}
else {
    $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $exe)) {
        Write-Error "Docker Desktop nao encontrado em: $exe"
        exit 1
    }

    Write-Host "Docker daemon fora do ar. Iniciando Docker Desktop..."
    Start-Process -FilePath $exe | Out-Null

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-DockerDaemon)) {
        if ($sw.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
            Write-Host ""
            Write-Error "Timeout: o daemon nao respondeu em $TimeoutSeconds s. Abra o Docker Desktop e verifique."
            exit 1
        }
        Start-Sleep -Seconds 3
        Write-Host "." -NoNewline
    }
    Write-Host ""
    Write-Host ("Docker daemon pronto em {0}s." -f [int]$sw.Elapsed.TotalSeconds) -ForegroundColor Green
}

if ($Up) {
    Write-Host "Subindo a stack (docker compose up -d)..."
    docker compose up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Error "docker compose up -d falhou."
        exit 1
    }
    Write-Host "Stack no ar. Agora: Ctrl+Shift+P -> Dev Containers: Reopen in Container." -ForegroundColor Green
}
