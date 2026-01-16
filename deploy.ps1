# Git workflow script: sync, commit, tag, and push

param(
    [string]$CommitMessage = "Update version"
)

# Get current version
$versionFile = "version.txt"
if (Test-Path $versionFile) {
    $currentVersion = Get-Content $versionFile -Raw
} else {
    $currentVersion = "0.0.1"
}

# Parse and increment version
$versionParts = $currentVersion.Trim().Split('.')
$major, $minor, $patch = [int]$versionParts[0], [int]$versionParts[1], [int]$versionParts[2]
$newVersion = "$major.$minor.$($patch + 1)"

Write-Host "Current version: $currentVersion" -ForegroundColor Cyan
Write-Host "New version: $newVersion" -ForegroundColor Green
Write-Host ""

# 1. Sync
Write-Host "[1/5] Syncing with remote..." -ForegroundColor Yellow
git pull origin main
if ($LASTEXITCODE -ne 0) { exit 1 }

# 2. Stage
Write-Host "[2/5] Staging changes..." -ForegroundColor Yellow
git add .

# 3. Commit
Write-Host "[3/5] Committing changes..." -ForegroundColor Yellow
git commit -m "$CommitMessage - $newVersion"

# 4. Tag
Write-Host "[4/5] Creating tag..." -ForegroundColor Yellow
git tag -a $newVersion -m "Release version $newVersion"
if ($LASTEXITCODE -ne 0) { Write-Host "Error creating tag"; exit 1 }

# 5. Push
Write-Host "[5/5] Pushing to origin..." -ForegroundColor Yellow
git push -u origin main
git push origin $newVersion

# Save version
$newVersion | Out-File $versionFile -NoNewline

Write-Host ""
Write-Host "✓ Deployment complete! Version $newVersion pushed." -ForegroundColor Green"