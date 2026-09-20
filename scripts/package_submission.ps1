# 打包提交包：排除密钥/数据/依赖，产出可直接上传的 zip
# 用法：powershell -ExecutionPolicy Bypass -File scripts\package_submission.ps1
param(
    [string]$OutDir = "dist_submission",
    [string]$Name   = "BAYTECH2026_可视化AI导演台"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Stage = Join-Path $Root $OutDir
$Target = Join-Path $Stage $Name
$Zip = Join-Path $Stage ($Name + ".zip")

# 绝不进包的路径（密钥、数据库、运行痕迹、依赖、缓存）
$excludeDirs = @('.env', 'data', '.runtime', '.runtime_deps', '.venv', '.pytest_tmp', '.pytest_cache',
                 'node_modules', 'dist', '.depsclean', '.deps', '.deps313', '__pycache__', '.git')
$excludeFiles = @('*.db', '*.pyc', '*.pyo', '*.log', 'backend-8100.log')

function Test-Excluded([string]$relative) {
    foreach ($part in $relative -split '[\\/]') {
        if ($excludeDirs -contains $part) { return $true }
    }
    foreach ($pattern in $excludeFiles) {
        if ($relative -like $pattern) { return $true }
    }
    return $false
}

Write-Host "==> 准备打包：$Root" -ForegroundColor Cyan
if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Target -Force | Out-Null

$copied = 0
Get-ChildItem -LiteralPath $Root -Force | Where-Object { $_.Name -ne $OutDir } | ForEach-Object {
    $source = $_.FullName
    $relative = $_.Name
    if (Test-Excluded $relative) { Write-Host "    skip $relative" -ForegroundColor DarkGray; return }
    if ($_.PSIsContainer) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $Target $relative) -Recurse -Force
    } else {
        Copy-Item -LiteralPath $source -Destination (Join-Path $Target $relative) -Force
    }
    $copied++
}

# 二次清理：递归删除被复制进来的依赖/缓存目录与数据库
Get-ChildItem -LiteralPath $Target -Recurse -Force -Directory |
    Where-Object { $excludeDirs -contains $_.Name } |
    ForEach-Object { Write-Host "    prune $($_.FullName.Substring($Target.Length + 1))" -ForegroundColor DarkGray; Remove-Item -LiteralPath $_.FullName -Recurse -Force }
Get-ChildItem -LiteralPath $Target -Recurse -Force -File |
    Where-Object { $_.Extension -in @('.db', '.pyc', '.pyo') -or $_.Name -eq '.env' } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

# 安全校验：包里绝不能出现密钥与数据库
$leaks = Get-ChildItem -LiteralPath $Target -Recurse -Force -File |
    Where-Object { $_.Name -eq '.env' -or $_.Extension -eq '.db' }
if ($leaks) {
    Write-Host "!! 检测到敏感文件，已中止：" -ForegroundColor Red
    $leaks | ForEach-Object { Write-Host "   $($_.FullName)" -ForegroundColor Red }
    exit 1
}

Compress-Archive -Path (Join-Path $Target '*') -DestinationPath $Zip -Force
$size = [math]::Round((Get-Item -LiteralPath $Zip).Length / 1MB, 2)
Write-Host ""
Write-Host "[OK] 打包完成：$Zip（$size MB，$copied 个顶层条目）" -ForegroundColor Green
Write-Host "     包内已排除：.env（密钥）、data/（数据库与素材）、.runtime/、依赖目录、缓存" -ForegroundColor Green
Write-Host "     启动说明：$Name\docs\SUBMISSION_GUIDE.md" -ForegroundColor Green
