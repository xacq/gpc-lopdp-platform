param(
    [string]$OutputPath = "deploy/docker.env",
    [int]$HttpPort = 8080
)

$ErrorActionPreference = "Stop"

if ($HttpPort -lt 1 -or $HttpPort -gt 65535) {
    throw "HTTP_PORT debe estar entre 1 y 65535."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$templatePath = Join-Path $PSScriptRoot "docker.env.example"
$targetPath = Join-Path $projectRoot $OutputPath

if (Test-Path -LiteralPath $targetPath) {
    throw "El archivo ya existe: $targetPath"
}

function New-Base64Key {
    $bytes = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes)
}

function New-UrlSafeToken([int]$Size = 36) {
    $bytes = [byte[]]::new($Size)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$content = Get-Content -LiteralPath $templatePath -Raw
$content = $content.Replace("HTTP_PORT=8080", "HTTP_PORT=$HttpPort")
$content = $content.Replace("http://localhost:8080", "http://localhost:$HttpPort")
$content = $content.Replace("generate-a-unique-secret", (New-UrlSafeToken 48))
$content = $content.Replace("replace-with-a-unique-password", (New-UrlSafeToken 32))
$content = $content.Replace("generate-a-32-byte-base64-key", (New-Base64Key))
$content = $content.Replace("generate-an-independent-32-byte-base64-key", (New-Base64Key))

$targetDirectory = Split-Path -Parent $targetPath
New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
Set-Content -LiteralPath $targetPath -Value $content -Encoding utf8NoBOM

Write-Output "Entorno Docker creado: $targetPath"
Write-Output "No publique este archivo ni reutilice sus secretos en otra empresa."
