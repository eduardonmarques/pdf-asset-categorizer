# scheduler.ps1 -- Gerencia execucao automatica do categorizador por janela de horario
# Janelas:
#   23:00-06:00 -- executa sempre (modo noturno)
#   09:00-18:00 -- executa apenas quando computador ocioso
#   Fora dessas janelas -- para o processo se estiver rodando

$PROJECT     = "G:\Meu Drive\Git\Projetos\Resume_PDFs_Relatorios"
$PYTHON      = "$PROJECT\.venv\Scripts\python.exe"
$MAIN_SCRIPT = "main.py"
$RUN_ARGS    = ""
$LOG         = "$PROJECT\scheduler.log"
$CHECK_SEC   = 120

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $LOG -Value $line -Encoding UTF8
}

function Get-CatProcess {
    Get-WmiObject Win32_Process -Filter "name='python.exe'" |
        Where-Object { $_.CommandLine -like "*Resume_PDFs_Relatorios*" -and $_.CommandLine -like "*main.py*" } |
        Select-Object -First 1
}

function Test-ComputerIdle {
    $otherCPU = Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $wmi = Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue
            if ($wmi -and $wmi.CommandLine -notlike "*Resume_PDFs_Relatorios*") { $_.CPU }
        } catch {}
    }
    $total = ($otherCPU | Measure-Object -Sum).Sum
    if ($null -eq $total) { $total = 0 }
    return ($total -lt 50)
}

function Start-Categorizer {
    Write-Log "Iniciando categorizador (producao)..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $PYTHON
    $psi.Arguments = if ($RUN_ARGS) { "$MAIN_SCRIPT $RUN_ARGS" } else { $MAIN_SCRIPT }
    $psi.WorkingDirectory = $PROJECT
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Minimized
    $psi.UseShellExecute = $true
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    Write-Log "Categorizador iniciado."
}

function Stop-Categorizer {
    $proc = Get-CatProcess
    if ($proc) {
        Write-Log "Parando categorizador (PID $($proc.ProcessId))..."
        Get-WmiObject Win32_Process -Filter "name='python.exe'" |
            Where-Object { $_.CommandLine -like "*Resume_PDFs_Relatorios*" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Write-Log "Categorizador parado."
    }
}

Write-Log "=== Scheduler iniciado ==="
Write-Log "Janelas: noturno 00:00-06:00 (sempre) | diurno 09:00-18:00 (se ocioso)"

while ($true) {
    $hour    = (Get-Date).Hour
    $isNight = ($hour -lt 6)
    $isDay   = ($hour -ge 9 -and $hour -lt 18)
    $running = $null -ne (Get-CatProcess)

    if ($isNight) {
        if (-not $running) {
            Write-Log "Janela noturna - iniciando."
            Start-Categorizer
        } else {
            Write-Log "Janela noturna - em execucao. OK."
        }
    } elseif ($isDay) {
        $idle = Test-ComputerIdle
        if ($idle -and -not $running) {
            Write-Log "Janela diurna + ocioso - iniciando."
            Start-Categorizer
        } elseif (-not $idle -and $running) {
            Write-Log "Janela diurna + ocupado - parando."
            Stop-Categorizer
        } elseif ($idle -and $running) {
            Write-Log "Janela diurna + ocioso - em execucao. OK."
        } else {
            Write-Log "Janela diurna + ocupado - aguardando ociosidade."
        }
    } else {
        if ($running) {
            Write-Log "Fora da janela ($($hour)h) - parando."
            Stop-Categorizer
        } else {
            Write-Log "Fora da janela ($($hour)h) - aguardando."
        }
    }

    Start-Sleep -Seconds $CHECK_SEC
}
