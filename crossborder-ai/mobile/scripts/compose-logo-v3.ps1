Add-Type -AssemblyName System.Drawing
$outDir = "D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22"

function New-MarkIcon([string]$path, [bool]$dark) {
  $bmp = New-Object System.Drawing.Bitmap ([int]1024), ([int]1024)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

  if ($dark) {
    $bg = [System.Drawing.Color]::FromArgb(255, 11, 14, 18)
    $fg = [System.Drawing.Color]::White
  } else {
    $bg = [System.Drawing.Color]::White
    $fg = [System.Drawing.Color]::FromArgb(255, 11, 14, 18)
  }
  $g.Clear($bg)

  $m = New-Object System.Drawing.Drawing2D.Matrix
  $center = New-Object System.Drawing.PointF ([float]512), ([float]512)
  $m.RotateAt([float]-4.0, $center)
  $g.Transform = $m

  $brush = New-Object System.Drawing.SolidBrush $fg

  # sail only: slanted head, wind bulge, straight edge on the mast
  $sail = New-Object System.Drawing.Drawing2D.GraphicsPath
  $sail.AddLine(556,250, 492,268)
  $sail.AddBezier(492,268, 400,360, 330,560, 322,742)
  $sail.AddLine(322,742, 556,742)
  $sail.AddLine(556,742, 556,250)
  $sail.CloseFigure()
  $g.FillPath($brush, $sail)

  # mast: 30 wide, tip above the sail head
  $g.FillRectangle($brush, 556, 216, 30, 566)

  # star: four points, centre 716,296, R=74, r=19.5
  $pts = New-Object System.Collections.Generic.List[System.Drawing.PointF]
  $pts.Add((New-Object System.Drawing.PointF ([float]716), ([float]222)))
  $pts.Add((New-Object System.Drawing.PointF ([float]729.8), ([float]282.2)))
  $pts.Add((New-Object System.Drawing.PointF ([float]790), ([float]296)))
  $pts.Add((New-Object System.Drawing.PointF ([float]729.8), ([float]309.8)))
  $pts.Add((New-Object System.Drawing.PointF ([float]716), ([float]370)))
  $pts.Add((New-Object System.Drawing.PointF ([float]702.2), ([float]309.8)))
  $pts.Add((New-Object System.Drawing.PointF ([float]642), ([float]296)))
  $pts.Add((New-Object System.Drawing.PointF ([float]702.2), ([float]282.2)))
  $g.FillPolygon($brush, $pts.ToArray())

  $g.ResetTransform()
  [void]$bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $brush.Dispose()
  $sail.Dispose()
  $g.Dispose()
  [void]$bmp.Dispose()
  $path
}

$black = New-MarkIcon "$outDir\logo-v3-black.png" $true
$white = New-MarkIcon "$outDir\logo-v3-white.png" $false

$sizes = @(180, 96, 48, 24)
$src = [System.Drawing.Image]::FromFile($black)
$padS = 28
$W = [int](($sizes | Measure-Object -Sum).Sum + ($sizes.Count + 1) * $padS)
$H = [int](200 + 2 * $padS + 30)
$sheet = New-Object System.Drawing.Bitmap ([int]$W), ([int]$H)
$gs = [System.Drawing.Graphics]::FromImage($sheet)
$gs.Clear([System.Drawing.Color]::FromArgb(255, 238, 239, 241))
$gs.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$gs.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
$font = New-Object System.Drawing.Font("Microsoft YaHei", 9, [System.Drawing.FontStyle]::Regular)
$brushTxt = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 92, 99, 108))
$x = $padS
foreach ($s in $sizes) {
  $y = [int]($padS + (200 - $s) / 2)
  $gs.DrawImage($src, $x, $y, $s, $s)
  $gs.DrawString(("{0}px" -f $s), $font, $brushTxt, $x, [float]($padS + 200 + 4))
  $x += $s + $padS
}
$gs.Dispose()
[void]$sheet.Save("$outDir\logo-v3-scale.png", [System.Drawing.Imaging.ImageFormat]::Png)
$src.Dispose()
[void]$sheet.Dispose()
$font.Dispose()
$brushTxt.Dispose()

"$outDir\logo-v3-scale.png"
