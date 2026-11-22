Add-Type -AssemblyName System.Drawing
$root = "D:\Project\crossborder-ai\mobile\artifacts"
$items = @(
  @("$root\design-2026-11-22-round2\01-notification.png", "design"),
  @("$root\ui-verify-v68\activity\home-390x844.png", "before"),
  @("$root\ui-verify-v71\activity\home-390x844.png", "after")
)
$cellH = 1100
$pad = 14
$widths = @()
foreach ($it in $items) {
  $img = [System.Drawing.Image]::FromFile($it[0])
  $widths += [int]($img.Width * $cellH / $img.Height)
  $img.Dispose()
}
$W = ($widths | Measure-Object -Sum).Sum + ($pad * ($items.Count + 1))
$H = [int]($cellH + 2 * $pad)
$bmp = New-Object System.Drawing.Bitmap ([int]$W), $H
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 235, 236, 238))
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$x = $pad
for ($i = 0; $i -lt $items.Count; $i++) {
  $img = [System.Drawing.Image]::FromFile($items[$i][0])
  $g.DrawImage($img, $x, $pad, $widths[$i], $cellH)
  $img.Dispose()
  $x += $widths[$i] + $pad
}
$out = "$root\ui-review-2026-11-22\header-white-demo.png"
[void]$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
[void]$bmp.Dispose()
"$out"
