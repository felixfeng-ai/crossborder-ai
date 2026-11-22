Add-Type -AssemblyName System.Drawing
$outDir = "D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22"

$a = "$outDir\logo-ai-a.png"
$b = "$outDir\logo-v2-black.png"
$c = "$outDir\logo-v3-black.png"

$cellH = 420
$pad = 20
$labelH = 24
$smallH = 48

$W = [int](3 * $cellH + 4 * $pad)
$H = [int]($labelH + $cellH + 16 + $smallH + 30 + 2 * $pad)

$bmp = New-Object System.Drawing.Bitmap ([int]$W), ([int]$H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 238, 239, 241))
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias

$font = New-Object System.Drawing.Font("Microsoft YaHei", 9, [System.Drawing.FontStyle]::Regular)
$brushTxt = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 92, 99, 108))

$items = @(
  @($a, "A / flat black, ai draft"),
  @($b, "B / my geometry, full boat"),
  @($c, "C / my geometry, sail only")
)

$x = $pad
for ($i = 0; $i -lt 3; $i++) {
  $img = [System.Drawing.Image]::FromFile($items[$i][0])
  $g.DrawImage($img, $x, $pad + $labelH, $cellH, $cellH)
  $g.DrawString($items[$i][1], $font, $brushTxt, $x, $pad)
  $img.Dispose()
  $y2 = [int]($pad + $labelH + $cellH + 16)
  $img = [System.Drawing.Image]::FromFile($items[$i][0])
  $g.DrawImage($img, $x, $y2, $smallH, $smallH)
  $img.Dispose()
  $g.DrawString("48px", $font, $brushTxt, $x, [float]($y2 + $smallH + 4))
  $x += $cellH + $pad
}

[void]$bmp.Save("$outDir\logo-compare.png", [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$font.Dispose()
$brushTxt.Dispose()
[void]$bmp.Dispose()

# colour sanity check on the ai draft: is it truly flat black and white
$src = New-Object System.Drawing.Bitmap ($a)
$step = 12
$dark = 0
$light = 0
$mid = 0
for ($y = 0; $y -lt $src.Height; $y += $step) {
  for ($x = 0; $x -lt $src.Width; $x += $step) {
    $p = $src.GetPixel($x, $y)
    $avg = ($p.R + $p.G + $p.B) / 3
    if ($avg -lt 40) { $dark++ } elseif ($avg -gt 215) { $light++ } else { $mid++ }
  }
}
$src.Dispose()
"ai draft samples: dark=$dark light=$light mid=$mid"
"$outDir\logo-compare.png"
