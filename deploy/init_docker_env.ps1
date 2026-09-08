param(
    [string]$OutputPath = "deploy/docker.env",
    [int]$HttpPort = 8080,
    [string]$TenantSlug = "vinesa",
    [string]$MfaIssuer = "VINESA",
    [string]$DefaultFromEmail = "privacidad@vinesa.com.ec"
)

$ErrorActionPreference = "Stop"

if ($HttpPort -lt 1 -or $HttpPort -gt 65535) {
    throw "HTTP_PORT debe estar entre 1 y 65535."
}

if ($TenantSlug -notmatch '^[a-z0-9][a-z0-9-]*$') {
    throw "TenantSlug solo admite letras minúsculas, números y guiones."
}

if ($DefaultFromEmail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
    throw "DefaultFromEmail no tiene un formato válido."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$templatePath = Join-Path $PSScriptRoot "docker.env.example"
$targetPath = Join-Path $projectRoot $OutputPath
$databaseSlug = $TenantSlug.Replace('-', '_')
$composeProjectName = "gpc-lopdp-$TenantSlug"
$databaseName = "gpc_lopdp_$databaseSlug"
$tenantEnvFile = $OutputPath.Replace('\', '/')

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
$content = $content.Replace("COMPOSE_PROJECT_NAME=gpc-lopdp-vinesa", "COMPOSE_PROJECT_NAME=$composeProjectName")
$content = $content.Replace("TENANT_ENV_FILE=deploy/docker.env", "TENANT_ENV_FILE=$tenantEnvFile")
$content = $content.Replace("HTTP_PORT=8080", "HTTP_PORT=$HttpPort")
$content = $content.Replace("http://localhost:8080", "http://localhost:$HttpPort")
$content = $content.Replace("POSTGRES_DB=gpc_lopdp_vinesa", "POSTGRES_DB=$databaseName")
$content = $content.Replace("POSTGRES_USER=gpc_lopdp_vinesa", "POSTGRES_USER=$databaseName")
$content = $content.Replace("gpc_lopdp_vinesa:replace-with-a-unique-password@db:5432/gpc_lopdp_vinesa", "$databaseName`:replace-with-a-unique-password@db:5432/$databaseName")
$content = $content.Replace("MFA_TOTP_ISSUER=VINESA", "MFA_TOTP_ISSUER=$MfaIssuer")
$content = $content.Replace("DEFAULT_FROM_EMAIL=privacidad@vinesa.com.ec", "DEFAULT_FROM_EMAIL=$DefaultFromEmail")
$content = $content.Replace("generate-a-unique-secret", (New-UrlSafeToken 48))
$content = $content.Replace("replace-with-a-unique-password", (New-UrlSafeToken 32))
$content = $content.Replace("generate-a-32-byte-base64-key", (New-Base64Key))
$content = $content.Replace("generate-an-independent-32-byte-base64-key", (New-Base64Key))

$targetDirectory = Split-Path -Parent $targetPath
New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
Set-Content -LiteralPath $targetPath -Value $content -Encoding utf8NoBOM

Write-Output "Entorno Docker creado: $targetPath"
Write-Output "No publique este archivo ni reutilice sus secretos en otra empresa."
