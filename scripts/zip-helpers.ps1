# Shared by build-apworld.ps1 and build-release.ps1 (dot-sourced).
#
# Zip entry names must use forward slashes (the zip standard). Windows PowerShell's Compress-Archive writes backslashes, and so does
# [System.IO.Compression.ZipFile]::CreateFromDirectory when it runs inside Windows PowerShell 5.1, so entries are named explicitly.
# A zip with backslashes extracts incorrectly on Linux, for example on an Archipelago host that loads the apworld there.

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function New-StandardZip {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDir,
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][bool]$IncludeBaseDirectory
    )

    $source = (Resolve-Path $SourceDir).Path.TrimEnd('\')
    $prefix = if ($IncludeBaseDirectory) { (Split-Path $source -Leaf) + "/" } else { "" }

    $archive = [System.IO.Compression.ZipFile]::Open($ZipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        Get-ChildItem -Path $source -Recurse -File -Force | ForEach-Object {
            $relative = $_.FullName.Substring($source.Length + 1).Replace('\', '/')
            [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive, $_.FullName, ($prefix + $relative), [System.IO.Compression.CompressionLevel]::Optimal)
        }
    }
    finally {
        $archive.Dispose()
    }
}
