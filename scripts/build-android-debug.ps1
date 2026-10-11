param(
  [string]$SdkRoot = 'D:\Android\Sdk',
  [string]$JdkRoot = 'D:\Android\jdk-21.0.12.1+1'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$androidRoot = Join-Path $projectRoot 'android'
$platformJar = Join-Path $SdkRoot 'platforms\android-36\android.jar'
$aapt = Join-Path $SdkRoot 'build-tools\35.0.0\aapt2.exe'
$java = Join-Path $JdkRoot 'bin\java.exe'

if (-not (Test-Path -LiteralPath $java -PathType Leaf)) {
  throw "缺少 JDK 21：$java。可从 Microsoft Build of OpenJDK 下载 ZIP，或用 -JdkRoot 指定安装目录。"
}
if (-not (Test-Path -LiteralPath $platformJar -PathType Leaf) -or
    -not (Test-Path -LiteralPath $aapt -PathType Leaf)) {
  Write-Host "Android SDK 组件未齐：" -ForegroundColor Yellow
  Write-Host "  platform android-36: $(Test-Path -LiteralPath $platformJar -PathType Leaf)"
  Write-Host "  build-tools 35.0.0: $(Test-Path -LiteralPath $aapt -PathType Leaf)"
  Write-Host '请先在 Android SDK Manager 阅读并接受所需许可，再安装 platforms;android-36 和 build-tools;35.0.0。'
  exit 2
}

# Windows PowerShell 5.1 turns any native stderr output into a terminating error, so an ordinary
# tool warning (for example Vite's chunk-size notice) aborts the build. Run each native tool with
# stderr tolerated and check its exit code explicitly instead.
function Invoke-NativeTool([scriptblock]$Command, [string]$FailureMessage) {
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & $Command } finally { $ErrorActionPreference = $previous }
  if ($LASTEXITCODE -ne 0) { throw "$FailureMessage：$LASTEXITCODE" }
}

$env:JAVA_HOME = $JdkRoot
$env:ANDROID_HOME = $SdkRoot
Push-Location $projectRoot
try {
  Invoke-NativeTool { npm.cmd run android:sync } '前端构建或 Capacitor 同步失败'
  Push-Location $androidRoot
  try {
    Invoke-NativeTool { .\gradlew.bat :app:assembleDebug } 'Android Gradle 编译失败'
  } finally {
    Pop-Location
  }
  $apk = Join-Path $androidRoot 'app\build\outputs\apk\debug\app-debug.apk'
  if (-not (Test-Path -LiteralPath $apk -PathType Leaf)) { throw "编译完成，但未找到 APK：$apk" }
  Write-Host "调试 APK：$apk" -ForegroundColor Green
} finally {
  Pop-Location
}
