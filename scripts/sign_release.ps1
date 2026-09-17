# Signs the AAC Assistant release binaries with Authenticode at zero cost.
#
# Uses a self-signed code-signing certificate stored in the user certificate
# store (Cert:\CurrentUser\My). The certificate is created on first use and
# reused afterwards, so every build on the same machine is signed with the
# same identity.
#
# Honest limitation (documented in README): a self-signed signature proves
# the binaries come from this machine's certificate, but it carries no
# third-party reputation. Windows Smart App Control only trusts binaries
# with cloud reputation or a paid CA certificate, so SAC-enabled machines
# still block self-signed builds. Signing without purchase improves:
#   - consistent publisher identity on UAC prompts and file properties
#   - tamper evidence for distribution inside a trusted group
#   - a stable signer name instead of "unknown publisher" once the machine
#     owner trusts the certificate (Import-PfxCertificate / certmgr)
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sign_release.ps1 ^
#     -ExePath dist\AAC_Assistant\AAC_Assistant.exe ^
#     -InstallerPath dist\AAC_Assistant_Setup_2.0.0.exe
#
# CI usage: the release workflow imports the secret PFX into
# Cert:\CurrentUser\My itself and calls this script with
# AAC_SIGNING_THUMBPRINT, so no certificate is ever created in CI.
#
# Environment overrides:
#   AAC_SIGNING_SUBJECT     certificate subject (default "AAC Assistant Team")
#   AAC_SIGNING_THUMBPRINT  use an existing certificate by thumbprint (CI path:
#                           the workflow imports the secret PFX, then passes this)
#   AAC_SIGNING_PFX         path to export a backup PFX copy of the certificate
#   AAC_SIGNING_PFX_PASS    password for the exported PFX (default: random, printed)

param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $false)][string]$InstallerPath,
    [string]$Subject = $(if ($env:AAC_SIGNING_SUBJECT) { $env:AAC_SIGNING_SUBJECT } else { "AAC Assistant Team" }),
    [string]$Thumbprint = $(if ($env:AAC_SIGNING_THUMBPRINT) { $env:AAC_SIGNING_THUMBPRINT } else { "" }),
    [switch]$SkipTrustImport
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ExePath)) {
    Write-Error "Executable to sign not found: $ExePath"
}

# --- Locate or create the signing certificate -------------------------------
# Resolution order: explicit thumbprint (CI imports the secret PFX itself),
# then an existing certificate with the configured subject, then create one.
$existing = $null
if ($Thumbprint) {
    $existing = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object Thumbprint -eq $Thumbprint |
        Select-Object -First 1
    if (-not $existing) {
        Write-Error "No certificate with thumbprint $Thumbprint found in Cert:\CurrentUser\My"
    }
}
else {
    $existing = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -like "*CN=$Subject*" } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1
}

if ($existing) {
    $cert = $existing
    Write-Host "Reusing existing code-signing certificate: $($cert.Subject) (expires $($cert.NotAfter))"
}
else {
    Write-Host "Creating self-signed code-signing certificate '$Subject'..."
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject "CN=$Subject" `
        -KeyUsage DigitalSignature, KeyEncipherment `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -NotAfter (Get-Date).AddYears(5) `
        -CertStoreLocation Cert:\CurrentUser\My
    Write-Host "Created certificate with thumbprint $($cert.Thumbprint)"
}

# --- Optional backup export -------------------------------------------------
if ($env:AAC_SIGNING_PFX) {
    $pfxPassword = if ($env:AAC_SIGNING_PFX_PASS) { $env:AAC_SIGNING_PFX_PASS } else {
        [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    }
    $secure = ConvertTo-SecureString -String $pfxPassword -AsPlainText -Force
    Export-PfxCertificate -Cert $cert -FilePath $env:AAC_SIGNING_PFX -Password $secure | Out-Null
    Write-Host "Backup PFX exported to $env:AAC_SIGNING_PFX"
    if (-not $env:AAC_SIGNING_PFX_PASS) {
        Write-Host "PFX password (store it now): $pfxPassword"
    }
}

# --- User-scope trust for self-signed chains -------------------------------
# A self-signed cert is its own root, so signature verification reports an
# untrusted chain unless the cert is also present in the user's trusted root
# and publisher stores. Import it there (user scope only, reversible via
# certmgr) so Get-AuthenticodeSignature returns Valid on this machine.
if (-not $SkipTrustImport -and $cert.Subject -eq $cert.Issuer) {
    $cerFile = Join-Path $env:TEMP "aac-signing-$($cert.Thumbprint).cer"
    Export-Certificate -Cert $cert -FilePath $cerFile | Out-Null
    foreach ($store in "Cert:\CurrentUser\Root", "Cert:\CurrentUser\TrustedPublisher") {
        $present = Get-ChildItem $store | Where-Object Thumbprint -eq $cert.Thumbprint
        if (-not $present) {
            Import-Certificate -FilePath $cerFile -CertStoreLocation $store | Out-Null
            Write-Host "Added certificate to $store"
        }
    }
    Remove-Item $cerFile -Force
}

# --- Sign -------------------------------------------------------------------
# The installer embeds the app exe, so sign the exe first and the installer
# last: the outer signature then covers the shipped payload.
$targets = @($ExePath)
if ($InstallerPath -and (Test-Path -LiteralPath $InstallerPath)) {
    $targets += $InstallerPath
}

foreach ($target in $targets) {
    $null = Set-AuthenticodeSignature `
        -FilePath $target `
        -Certificate $cert `
        -TimestampServer "http://timestamp.digicert.com" `
        -HashAlgorithm SHA256
    $sig = Get-AuthenticodeSignature -FilePath $target
    if ($sig.Status -ne "Valid") {
        Write-Error "Signature verification failed for ${target}: $($sig.Status) $($sig.StatusMessage)"
    }
    Write-Host "Signed: $target (status: $($sig.Status), signer: $($sig.SignerCertificate.Subject))"
}

Write-Host "Signing complete."
exit 0
