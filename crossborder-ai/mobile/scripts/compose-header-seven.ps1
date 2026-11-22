Add-Type -AssemblyName System.Drawing
$root = "D:\Project\crossborder-ai\mobile\artifacts"
$out = "$root\ui-review-2026-11-22\header-white-seven.png"
$names = @("home", "functions", "library", "account", "plan", "activity", "task-done")
$cellH = 620
$pad = 12
$labelH = 26
$imgs = @()
foreach ($n in $names) { $imgs += "$root\ui-verify-v73\$n\home-390x844.png" }
$colW = [int](390 * $cellH / 844)
$W = [int]($names.Count * $colW + ($names.Count + 1) * $pad)
$H = [int]($cellH + $labelH + 2 * $pad)
$bmp = New-Object System.Drawing.Bitmap ([int]$W), ([int]$H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 238, 239, 241))
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
$font = New-Object System.Drawing.Font("Microsoft YaHei", 10, [System.Drawing.FontStyle]::Regular)
$brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 90, 97, 106))
$x = $pad
for ($i = 0; $i -lt $names.Count; $i++) {
  $img = [System.Drawing.Image]::FromFile($imgs[$i])
  $g.DrawImage($img, $x, $pad + $labelH, $colW, $cellH)
  $img.Dispose()
  $g.DrawString($names[$i].ToUpper(), $font, $brush, $x + 4, $pad)
  $x += $colW + $pad
}
[void]$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$font.Dispose()
$brush.Dispose()
[void]$bmp.Dispose()
"$out"
