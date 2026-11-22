Add-Type -AssemblyName System.Drawing
$root = "D:\Project\crossborder-ai\mobile\artifacts"
$out = "$root\ui-review-2026-11-22\header-white-final.png"

$rows = @(
  @{ label = "HOME  /  首页"; cols = @(
      @("$root\ref\design-home.png", "DESIGN"),
      @("$root\ui-verify-v72\home\home-390x844.png", "BEFORE"),
      @("$root\ui-verify-v73\home\home-390x844.png", "AFTER")
    ) },
  @{ label = "TASK DETAIL  /  任务详情"; cols = @(
      @("$root\design-2026-11-22-round2\07-task-done.png", "DESIGN"),
      @("$root\ui-verify-v72\task-done\home-390x844.png", "BEFORE"),
      @("$root\ui-verify-v73\task-done\home-390x844.png", "AFTER")
    ) }
)

$cellH = 900
$pad = 16
$labelH = 34
$barH = 22

$widths = @()
foreach ($row in $rows) {
  foreach ($c in $row.cols) {
    $img = [System.Drawing.Image]::FromFile($c[0])
    $widths += [int]($img.Width * $cellH / $img.Height)
    $img.Dispose()
  }
}
$colW = ($widths | Measure-Object -Maximum).Maximum
$W = [int](3 * $colW + 4 * $pad)
$H = [int]($rows.Count * ($labelH + $cellH + $barH + $pad) + $pad)

$bmp = New-Object System.Drawing.Bitmap ([int]$W), ([int]$H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 238, 239, 241))
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
$font = New-Object System.Drawing.Font("Microsoft YaHei", 11, [System.Drawing.FontStyle]::Bold)
$fontSmall = New-Object System.Drawing.Font("Microsoft YaHei", 9, [System.Drawing.FontStyle]::Regular)
$brushText = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 60, 66, 74))
$brushSub = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 122, 130, 140))
$brushWhite = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)

$y = $pad
foreach ($row in $rows) {
  $g.DrawString($row.label, $font, $brushText, $pad, $y)
  $y += $labelH
  $x = $pad
  for ($i = 0; $i -lt $row.cols.Count; $i++) {
    $img = [System.Drawing.Image]::FromFile($row.cols[$i][0])
    $w = [int]($img.Width * $cellH / $img.Height)
    $g.DrawImage($img, $x, $y, $w, $cellH)
    $img.Dispose()
    $barY = $y + $cellH
    $g.FillRectangle($brushWhite, $x, $barY, $w, $barH)
    $g.DrawString($row.cols[$i][1], $fontSmall, $brushSub, $x + 8, $barY + 4)
    $x += $colW + $pad
  }
  $y += $cellH + $barH + $pad
}

[void]$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$font.Dispose()
$fontSmall.Dispose()
$brushText.Dispose()
$brushSub.Dispose()
$brushWhite.Dispose()
[void]$bmp.Dispose()
"$out"
