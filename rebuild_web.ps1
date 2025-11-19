# Script for safe Next.js rebuild
# Stops service, clears cache, builds project and restarts service

Write-Host "=== Rebuilding Next.js application ===" -ForegroundColor Cyan
Write-Host ""

$serviceName = "CryptoSpikesWeb"
$webPath = "C:\onlyWS\WEB"

# Step 1: Stop service
Write-Host "1. Stopping service $serviceName..." -ForegroundColor Yellow
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -eq "Running") {
        Stop-Service -Name $serviceName -Force
        Write-Host "   Service stopped" -ForegroundColor Green
        
        # Wait for full stop
        $timeout = 30
        $elapsed = 0
        while ($service.Status -ne "Stopped" -and $elapsed -lt $timeout) {
            Start-Sleep -Seconds 1
            $elapsed++
            $service.Refresh()
        }
        
        if ($service.Status -eq "Stopped") {
            Write-Host "   Service fully stopped" -ForegroundColor Green
        } else {
            Write-Host "   WARNING: Service did not stop within $timeout seconds" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   Service already stopped" -ForegroundColor Gray
    }
} else {
    Write-Host "   Service not found (continuing)" -ForegroundColor Yellow
}

Write-Host ""

# Step 2: Stop all Node.js processes related to Next.js
Write-Host "2. Checking Node.js processes..." -ForegroundColor Yellow
$nodeProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue
if ($nodeProcesses) {
    Write-Host "   Found Node.js processes: $($nodeProcesses.Count)" -ForegroundColor Yellow
    
    # Stop processes that might be using .next
    foreach ($proc in $nodeProcesses) {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        if ($cmdLine -and ($cmdLine -like "*next*" -or $cmdLine -like "*WEB*" -or $cmdLine -like "*standalone*")) {
            $shortCmd = if ($cmdLine.Length -gt 60) { $cmdLine.Substring(0, 60) + "..." } else { $cmdLine }
            Write-Host "   Stopping process PID $($proc.Id): $shortCmd..." -ForegroundColor Yellow
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    
    # Wait for processes to finish
    Start-Sleep -Seconds 2
    Write-Host "   Node.js processes stopped" -ForegroundColor Green
} else {
    Write-Host "   No Node.js processes found" -ForegroundColor Gray
}

Write-Host ""

# Step 3: Clear cache and lockfile
Write-Host "3. Clearing Next.js cache..." -ForegroundColor Yellow
Set-Location $webPath

# Remove lockfile if exists
$lockFile = ".next\lock"
if (Test-Path $lockFile) {
    try {
        Remove-Item -Path $lockFile -Force -ErrorAction Stop
        Write-Host "   Lockfile removed" -ForegroundColor Green
    } catch {
        Write-Host "   ERROR removing lockfile: $_" -ForegroundColor Red
        Write-Host "   Trying to change attributes..." -ForegroundColor Yellow
        try {
            $file = Get-Item $lockFile -Force
            $file.Attributes = "Normal"
            Remove-Item -Path $lockFile -Force
            Write-Host "   Lockfile removed after changing attributes" -ForegroundColor Green
        } catch {
            Write-Host "   Could not remove lockfile. Try removing manually." -ForegroundColor Red
        }
    }
}

# Remove entire .next directory
if (Test-Path ".next") {
    try {
        # First try to remove with attribute changes
        Get-ChildItem -Path ".next" -Recurse -Force | ForEach-Object {
            $_.Attributes = "Normal"
        }
        Remove-Item -Recurse -Force ".next" -ErrorAction Stop
        Write-Host "   .next directory removed" -ForegroundColor Green
    } catch {
        Write-Host "   WARNING: Could not fully remove .next: $_" -ForegroundColor Yellow
        Write-Host "   Continuing with build..." -ForegroundColor Yellow
    }
} else {
    Write-Host "   .next directory not found" -ForegroundColor Gray
}

Write-Host ""

# Step 4: Sync with repository (optional)
Write-Host "4. Syncing with repository..." -ForegroundColor Yellow
Set-Location "C:\onlyWS"
try {
    git pull origin main 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   Code synced" -ForegroundColor Green
    } else {
        Write-Host "   WARNING: Could not sync (may have conflicts)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   WARNING: Git not available or has issues" -ForegroundColor Yellow
}

Write-Host ""

# Step 5: Build project
Write-Host "5. Building Next.js project..." -ForegroundColor Yellow
Set-Location $webPath

$buildOutput = npm run build 2>&1
$buildSuccess = $LASTEXITCODE -eq 0

# Output build results
$buildOutput | ForEach-Object {
    if ($_ -match "Failed to compile|Type error|error TS|Build error|Access is denied") {
        Write-Host $_ -ForegroundColor Red
    } elseif ($_ -match "Compiled successfully|Build completed|Creating an optimized") {
        Write-Host $_ -ForegroundColor Green
    } else {
        Write-Host $_
    }
}

Write-Host ""

if ($buildSuccess) {
    Write-Host "=== Build completed successfully! ===" -ForegroundColor Green
    Write-Host ""
    
    # Step 6: Start service
    Write-Host "6. Starting service $serviceName..." -ForegroundColor Yellow
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service) {
        Start-Service -Name $serviceName
        Start-Sleep -Seconds 3
        $service.Refresh()
        
        if ($service.Status -eq "Running") {
            Write-Host "   Service started successfully" -ForegroundColor Green
        } else {
            Write-Host "   ERROR: Service did not start. Status: $($service.Status)" -ForegroundColor Red
        }
    } else {
        Write-Host "   Service not found" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "=== Done! ===" -ForegroundColor Green
} else {
    Write-Host "=== Build failed with errors ===" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check output above for error details." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If error is 'Access is denied', try:" -ForegroundColor Yellow
    Write-Host "1. Run PowerShell as Administrator" -ForegroundColor White
    Write-Host "2. Check that service is fully stopped" -ForegroundColor White
    Write-Host "3. Delete .next manually and retry" -ForegroundColor White
    exit 1
}
