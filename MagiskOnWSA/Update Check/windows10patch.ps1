param(
    [string]$OutputDir = "."
)

$ErrorActionPreference = 'Stop'

Clear-Host
Write-Output "`r`nPatching Windows 10 AppxManifest file..."
$manifestPath = Join-Path $OutputDir "AppxManifest.xml"
if (-not (Test-Path $manifestPath)) {
    Write-Error "AppxManifest.xml not found in $OutputDir"
    exit 1
}
$xml = [xml](Get-Content $manifestPath)
$nsm = New-Object Xml.XmlNamespaceManager($xml.NameTable)
$nsm.AddNamespace('rescap', "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities")
$nsm.AddNamespace('desktop6', "http://schemas.microsoft.com/appx/manifest/desktop/windows10/6")
$node = $xml.Package.Capabilities.SelectSingleNode("rescap:Capability[@Name='customInstallActions']", $nsm)
if ($null -ne $node) {
    $xml.Package.Capabilities.RemoveChild($node) | Out-Null
}
$node = $xml.Package.Extensions.SelectSingleNode("desktop6:Extension[@Category='windows.customInstall']", $nsm)
if ($null -ne $node) {
    $xml.Package.Extensions.RemoveChild($node) | Out-Null
}
$xml.Package.Dependencies.TargetDeviceFamily.MinVersion = "10.0.19041.264"
$xml.Save($manifestPath)

Write-Output "`r`nDownloading modified DLL files..."
$ProgressPreference = 'SilentlyContinue'
$clientDir = Join-Path $OutputDir "WsaClient"
if (-not (Test-Path $clientDir)) {
    New-Item -ItemType Directory -Path $clientDir | Out-Null
}
Invoke-WebRequest -Uri "https://github.com/MustardChef/WSAPatch/raw/main/DLLs%20for%20WSABuilds/winhttp.dll" -OutFile (Join-Path $clientDir "winhttp.dll")
Invoke-WebRequest -Uri "https://github.com/MustardChef/WSAPatch/raw/main/DLLs%20for%20WSABuilds/WsaPatch.dll" -OutFile (Join-Path $clientDir "WsaPatch.dll")
Invoke-WebRequest -Uri "https://github.com/MustardChef/WSAPatch/raw/main/DLLs%20for%20WSABuilds/icu.dll" -OutFile (Join-Path $clientDir "icu.dll")
Write-Output "Windows 10 patch complete."
