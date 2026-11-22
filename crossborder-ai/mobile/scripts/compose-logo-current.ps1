Add-Type -AssemblyName System.Drawing
$root = "D:\Project\crossborder-ai\mobile\assets"
$out = "D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22\logo-current.png"

$items = @(
  @("$root\icon.png", "APP ICON (store)"),
  @("$root\android-icon-foreground.png", "ANDROID ADAPTIVE"),
  @("$root\brand\star-ark.png", "AGENT AVATAR MARK"),
  @("$root\brand\sign-in-mark.png", "SIGN-IN MARK"),
  @("$root\brand\veyaship-wordmark.png", "WORDMARK")
)

$cell = 380
$pad = 18
$labelH = 26
$ws = @()
foreach ($it in $items) {
  $img = [System.Drawing.Image]::FromFile($it[0])
  $ws += [int]($img.Width * $cell / $img.Height)
  $img.Dispose()
}
$W = [int](($ws | Measure-Object -Sum).Sum + ($items.Count + 1) * $pad)
$H = [int]($cell + $labelH + 2 * $pad)
$bmp = New-Object System.Drawing.Bitmap ([int]$W), ([int]$H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 238, 239, 241))
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
$font = New-Object System.Drawing.Font("Microsoft YaHei", 9, [System.Drawing.FontStyle]::Regular)
$brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 92, 99, 108))
$x = $pad
for ($i = 0; $i -lt $items.Count; $i++) {
  $img = [System.Drawing.Image]::FromFile($items[$i][0])
  $g.DrawImage($img, $x, $pad + $labelH, $ws[$i], $cell)
  $img.Dispose()
  $g.DrawString($items[$i][1], $font, $brush, $x, $pad)
  $x += $ws[$i] + $pad
}
[void]$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$font.Dispose()
$brush.Dispose()
[void]$bmp.Dispose()
"$out"
