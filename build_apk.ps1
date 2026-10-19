# HuoCatDesk Android 构建：搭 SDK + 编译 APK。全程 D 盘。
# 用法: powershell -ExecutionPolicy Bypass -File build_apk.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSCommandPath -Parent   # p2pdesk/
$android = Join-Path $root 'android'
$ad = Join-Path $root '.android'        # 下载的 zip 在此
$sdk = Join-Path $root '.android_sdk'   # SDK 装到 D 盘
$java = 'D:\Program Files\Zulu\zulu-17'
$env:JAVA_HOME = $java
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:GRADLE_USER_HOME = Join-Path $ad '.gradle'   # Gradle 缓存进 D 盘
$env:Path = "$java\bin;$env:Path"

function Step($m){ Write-Host "==== $m ====" -ForegroundColor Cyan }

# 1. 解压 cmdline-tools -> $sdk\cmdline-tools\latest
Step 'extract cmdline-tools'
$ctZip = Join-Path $ad 'cmdline-tools.zip'
if (-not (Test-Path $ctZip)) { throw "cmdline-tools.zip 不在 $ad" }
$ctTmp = Join-Path $sdk '_ct_tmp'
if (Test-Path $ctTmp) { Remove-Item $ctTmp -Recurse -Force }
Expand-Archive -Path $ctZip -DestinationPath $ctTmp -Force
# zip 顶层是 cmdline-tools/，移到 latest
New-Item -ItemType Directory -Force -Path (Join-Path $sdk 'cmdline-tools') | Out-Null
$ctSrc = Join-Path $ctTmp 'cmdline-tools'
if (-not (Test-Path $ctSrc)) { $ctSrc = $ctTmp }  # 某些版本无顶层文件夹
$ctDest = Join-Path $sdk 'cmdline-tools\latest'
if (Test-Path $ctDest) { Remove-Item $ctDest -Recurse -Force }
Move-Item $ctSrc $ctDest
Remove-Item $ctTmp -Recurse -Force -ErrorAction SilentlyContinue
$sdkmanager = Join-Path $ctDest 'bin\sdkmanager.bat'
if (-not (Test-Path $sdkmanager)) { throw "sdkmanager 不在 $ctDest" }
Write-Host "sdkmanager: $sdkmanager"

# 2. 解压 gradle
Step 'extract gradle'
$gradleZip = Join-Path $ad 'gradle-8.9-bin.zip'
if (-not (Test-Path $gradleZip)) { throw "gradle zip 不在 $ad" }
Expand-Archive -Path $gradleZip -DestinationPath $ad -Force
$gradle = Join-Path $ad 'gradle-8.9\bin\gradle.bat'
if (-not (Test-Path $gradle)) { throw "gradle 不在 $gradle" }

# 3. 接受许可 + 装 SDK 组件
Step 'install SDK components (platform-tools, android-34, build-tools 34)'
$y = ''; for ($i = 0; $i -lt 30; $i++) { $y += "y`n" }
Write-Host 'accepting licenses...'
$y | & $sdkmanager --licenses 2>&1 | Out-Null
Write-Host 'installing components...'
& $sdkmanager 'platform-tools' 'platforms;android-34' 'build-tools;34.0.0' 2>&1 | ForEach-Object { Write-Host $_ }

# 4. local.properties
Step 'write local.properties'
$lp = Join-Path $android 'local.properties'
$sdkDir = $sdk -replace '\\', '\\'
Set-Content -Path $lp -Value "sdk.dir=$sdkDir" -Encoding ASCII

# 5. 编译
Step 'gradle assembleDebug'
Push-Location $android
try {
    & $gradle 'assembleDebug' '--no-daemon' '--console=plain' 2>&1 | ForEach-Object { Write-Host $_ }
    $rc = $LASTEXITCODE
} finally { Pop-Location }
if ($rc -ne 0) { throw "gradle build failed (exit $rc)" }

$apk = Join-Path $android 'app\build\outputs\apk\debug\app-debug.apk'
if (Test-Path $apk) {
    Write-Host ""
    Write-Host "APK OK: $apk  ($([math]::Round((Get-Item $apk).Length/1MB,1)) MB)" -ForegroundColor Green
} else {
    throw "APK not found at $apk"
}
