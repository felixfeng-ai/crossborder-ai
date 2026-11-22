$root = 'D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22'
$src = Join-Path $root 'compare.html'
$dst = Join-Path $root 'compare-selfcontained.html'
$txt = [System.IO.File]::ReadAllText($src, [System.Text.Encoding]::UTF8)

Add-Type -AssemblyName System.Drawing
$thumbDir = Join-Path $root 'thumbs'
if (!(Test-Path $thumbDir)) { New-Item -ItemType Directory -Path $thumbDir | Out-Null }

$regex = [regex]'src="(\.\./[^"]+)"'
$map = @{}
$i = 0
foreach ($m in $regex.Matches($txt)) {
  $rel = $m.Groups[1].Value
  if ($map.ContainsKey($rel)) { continue }
  $abs = [System.IO.Path]::GetFullPath((Join-Path $root $rel))
  if (!(Test-Path $abs)) { "MISSING $rel"; continue }
  $img = [System.Drawing.Image]::FromFile($abs)
  $tw = 320
  $th = [int]($img.Height * $tw / $img.Width)
  $bmp = New-Object System.Drawing.Bitmap($tw, $th)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.DrawImage($img, 0, 0, $tw, $th)
  $g.Dispose(); $img.Dispose()
  $i++
  $tp = Join-Path $thumbDir ("t{0}.jpg" -f $i)
  $bmp.Save($tp, [System.Drawing.Imaging.ImageFormat]::Jpeg)
  $bmp.Dispose()
  $bytes = [System.IO.File]::ReadAllBytes($tp)
  $b64 = [Convert]::ToBase64String($bytes)
  $map[$rel] = "data:image/jpeg;base64,$b64"
}
foreach ($k in $map.Keys) {
  $txt = $txt.Replace('src="' + $k + '"', 'src="' + $map[$k] + '"')
}
[System.IO.File]::WriteAllText($dst, $txt, (New-Object System.Text.UTF8Encoding($false)))

$tr = ([regex]'<tr').Matches($txt).Count
$imgs = ([regex]'<img ').Matches($txt).Count
$left = ([regex]'\.\./').Matches($txt).Count
"thumbs=$i  tr=$tr  imgs=$imgs  relpaths=$left  size=$([math]::Round((Get-Item $dst).Length/1KB))KB"
