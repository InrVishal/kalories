$ProgressPreference = 'SilentlyContinue'

# SDK path inside user profile
$s = "C:\Users\visha\android-sdk"
# URL
$u = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
# ZIP file path (stored in C:\Users\visha\android-sdk)
$z = "$s\cmdline-zip.zip"
# Destination directory
$d = "$s\cmdline-tools\latest"
# SDK manager path
$m = "$d\bin\sdkmanager.bat"
# Extraction directory
$x = "$s\extracted-tools"

if (Test-Path $z) { Remove-Item -Force $z }

if (Test-Path $m) {
    Write-Host "✅ Already installed at $d"
} else {
    Write-Host "📥 Creating SDK directory: $s"
    New-Item -ItemType Directory -Force -Path $s | Out-Null

    Write-Host "📥 Downloading Android Command Line Tools..."
    Invoke-WebRequest -Uri $u -OutFile $z

    Write-Host "📦 Extracting..."
    if (Test-Path $x) { Remove-Item -Recurse -Force $x }
    Expand-Archive -Path $z -DestinationPath $x

    Write-Host "📂 Moving tools to $d..."
    $i = "$x\cmdline-tools"
    New-Item -ItemType Directory -Force -Path "$s\cmdline-tools" | Out-Null
    Move-Item -Path $i -Destination $d -Force

    # Clean up zip and extract folder
    Remove-Item -Force $z
    if (Test-Path $x) { Remove-Item -Recurse -Force $x }
}

Write-Host "⚙️ Installing Platform Tools..."
& $m --sdk_root=$s "platform-tools" "platforms;android-34" "build-tools;34.0.0"

Write-Host "✍️ Accepting Licenses..."
$y = @("y") * 20
$y | & $m --sdk_root=$s --licenses

Write-Host "🎉 Android SDK setup completed!"
