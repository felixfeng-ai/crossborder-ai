Add-Type -AssemblyName System.Drawing
$root = "D:\Project\crossborder-ai\mobile\artifacts"
$items = @(
  @("$root\design-2026-11-22-round2\01-notification.png", "design"),
  @("$root\ui-verify-v68\activity\home-390x844.png", "before"),
  @("$root\ui-verify-v71\activity\home-390x844.png", "after")
)
$targetW = 720
$cropRatio = 0.30
$pad = 14
$boxW = @()
$boxH = @()
foreach ($it in $items) {
  $img = [System.Drawing.Image]::FromFile($it[0])
  $cropH = [int]($img.Height * $cropRatio)
  $boxH += [int]($cropH * $targetW / $img.Width)
  $boxW += [int]($img.Width * $cropH / ($img.Width) * $targetW / $img.Width)
  $img.Dispose()
}
$maxH = ($boxH | Measure-Object -Maximum).Maximum
$W = ($pad * ($items.Count + 1)) + $targetW * $items.Count
$bmp = New-Object System.Drawing.Bitmap ([int]$W), ([int]($maxH + 2 * $pad))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 232, 233, 235))
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$x = $pad
for ($i = 0; $i -lt $items.Count; $i++) {
  $img = [System.Drawing.Image]::FromFile($items[$i][0])
  $cropH = [int]($img.Height * $cropRatio)
  $srcRect = New-Object System.Drawing.Rectangle 0, 0, $img.Width, $cropH
  $h = [int]($cropH * $targetW / $img.Width)
  $dstRect = New-Object System.Drawing.Rectangle $x, $pad, $targetW, $h
  $g.DrawImage($img, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
  $img.Dispose()
  $x += $targetW + $pad
}
$out = "$root\ui-review-2026-11-22\header-white-crop.png"
[void]$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
[void]$bmp.Dispose()
"$out"
