# Git workflow script: sync, commit, tag, and push to main branch
# Install GitHub CLI: winget install GitHub.cli or visit https://cli.github.com/
# Authenticate: Run gh auth login before using the script

param(
    [string]$CommitMessage = "Update version"
)

# Configuration
$branch = "main"
$versionFile = "version.txt"

# Get current version
if (Test-Path $versionFile) {
    $currentVersion = Get-Content $versionFile -Raw
} else {
    # Initialize with v2.0.0 for main branch
    $currentVersion = "v2.0.0"
}

# Parse version - extract prefix and numeric parts
$match = $currentVersion.Trim() -match '^([a-zA-Z]*)(\d+)\.(\d+)\.(\d+)$'
if (-not $match) {
    Write-Host "Invalid version format. Expected format: v2.x.x" -ForegroundColor Red
    exit 1
}

$prefix = $matches[1]
$major = [int]$matches[2]
$minor = [int]$matches[3]
$patch = [int]$matches[4]

# Increment patch version (v2.x.x)
$newVersion = "$prefix$major.$minor.$($patch + 1)"

Write-Host "================================" -ForegroundColor Cyan
Write-Host "  Hive Schedule Manager Deploy" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Branch:          $branch" -ForegroundColor White
Write-Host "Current version: $currentVersion" -ForegroundColor Cyan
Write-Host "New version:     $newVersion" -ForegroundColor Green
Write-Host ""

# Confirm deployment
$confirm = Read-Host "Continue with deployment? (y/n)"
if ($confirm -ne 'y' -and $confirm -ne 'Y') {
    Write-Host "Deployment cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""

# 1. Sync with remote
Write-Host "[1/7] Syncing with remote $branch branch..." -ForegroundColor Yellow
git pull origin $branch
if ($LASTEXITCODE -ne 0) { 
    Write-Host "Error: Failed to pull from remote. Make sure you're on the $branch branch." -ForegroundColor Red
    exit 1 
}

# 2. Verify we're on correct branch
Write-Host "[2/7] Verifying branch..." -ForegroundColor Yellow
$currentBranch = git branch --show-current
if ($currentBranch -ne $branch) {
    Write-Host "Error: Not on $branch branch. Current branch: $currentBranch" -ForegroundColor Red
    Write-Host "Switch to $branch branch: git checkout $branch" -ForegroundColor Yellow
    exit 1
}
Write-Host "OK - On $branch branch" -ForegroundColor Green

# 3. Stage changes
Write-Host "[3/7] Staging changes..." -ForegroundColor Yellow
git add .
if ($LASTEXITCODE -ne 0) { 
    Write-Host "Error staging changes" -ForegroundColor Red
    exit 1 
}

# 4. Commit changes
Write-Host "[4/7] Committing changes..." -ForegroundColor Yellow
git commit -m "$CommitMessage - $newVersion"
if ($LASTEXITCODE -ne 0) { 
    Write-Host "Warning: No changes to commit or commit failed" -ForegroundColor Yellow
}

# 5. Create tag
Write-Host "[5/7] Creating tag $newVersion..." -ForegroundColor Yellow
git tag -a $newVersion -m "Release version $newVersion - $CommitMessage"
if ($LASTEXITCODE -ne 0) { 
    Write-Host "Error creating tag. Tag may already exist." -ForegroundColor Red
    Write-Host "To delete existing tag: git tag -d $newVersion" -ForegroundColor Yellow
    exit 1 
}
Write-Host "OK - Tag $newVersion created" -ForegroundColor Green

# 6. Push to GitHub
Write-Host "[6/7] Pushing to GitHub..." -ForegroundColor Yellow
Write-Host "  - Pushing branch: $branch" -ForegroundColor Gray
git push -u origin $branch
if ($LASTEXITCODE -ne 0) { 
    Write-Host "Error pushing branch to GitHub" -ForegroundColor Red
    exit 1 
}

Write-Host "  - Pushing tag: $newVersion" -ForegroundColor Gray
git push origin $newVersion
if ($LASTEXITCODE -ne 0) { 
    Write-Host "Error pushing tag to GitHub" -ForegroundColor Red
    exit 1 
}
Write-Host "OK - Pushed to GitHub" -ForegroundColor Green

# 7. Create GitHub Release
Write-Host "[7/7] Creating GitHub release..." -ForegroundColor Yellow

# Simple release message
$releaseMsg = "$CommitMessage - See commit history for details"

gh release create $newVersion --title "Release $newVersion" --notes $releaseMsg --target $branch
if ($LASTEXITCODE -ne 0) { 
    Write-Host "Warning: Failed to create GitHub release. The code is pushed but release creation failed." -ForegroundColor Yellow
    Write-Host "You can create the release manually on GitHub." -ForegroundColor Yellow
} else {
    Write-Host "OK - GitHub release created" -ForegroundColor Green
}

# 8. Save new version to file
$newVersion | Out-File $versionFile -NoNewline
git add $versionFile
git commit -m "Update version to $newVersion"
git push origin $branch

Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "  Deployment Complete!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "Version:  $newVersion" -ForegroundColor White
Write-Host "Branch:   $branch" -ForegroundColor White
Write-Host "Release:  https://github.com/rrwood/hive-schedule-manager/releases/tag/$newVersion" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Verify the release on GitHub" -ForegroundColor White
Write-Host "2. Test installation via HACS" -ForegroundColor White
Write-Host "3. Update documentation if needed" -ForegroundColor White
Write-Host ""
