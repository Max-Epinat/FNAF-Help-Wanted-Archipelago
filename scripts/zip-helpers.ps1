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

    # Entry names are built while walking the tree, never by cutting the source path off a file's FullName: on a CI runner the temp
    # folder is given as an 8.3 short path (RUNNER~1) while FullName comes back long, and the cut then lands inside a name.
    function Add-Directory {
        param($Archive, [string]$Directory, [string]$EntryPrefix)
        foreach ($item in Get-ChildItem -LiteralPath $Directory -Force) {
            if ($item.PSIsContainer) {
                Add-Directory -Archive $Archive -Directory $item.FullName -EntryPrefix ($EntryPrefix + $item.Name + "/")
            }
            else {
                [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $Archive, $item.FullName, ($EntryPrefix + $item.Name), [System.IO.Compression.CompressionLevel]::Optimal)
            }
        }
    }

    $archive = [System.IO.Compression.ZipFile]::Open($ZipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        Add-Directory -Archive $archive -Directory $source -EntryPrefix $prefix
    }
    finally {
        $archive.Dispose()
    }
}
