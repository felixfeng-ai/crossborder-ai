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

  # hull: 640 wide crescent, 60 thick at the middle
  $hull = New-Object System.Drawing.Drawing2D.GraphicsPath
  $hull.AddBezier(190,708, 340,690, 680,690, 830,708)
  $hull.AddBezier(830,708, 680,772, 340,772, 190,708)
  $hull.CloseFigure()
  $g.FillPath($brush, $hull)

  # sail: wider slanted head, tighter wind bulge
  $sail = New-Object System.Drawing.Drawing2D.GraphicsPath
  $sail.AddLine(520,232, 452,252)
  $sail.AddBezier(452,252, 315,340, 232,570, 266,700)
  $sail.AddLine(266,700, 520,700)
  $sail.AddLine(520,700, 520,232)
  $sail.CloseFigure()
  $g.FillPath($brush, $sail)

  # mast: 30 wide, tip 30 above the sail head
  $g.FillRectangle($brush, 520, 200, 30, 546)

  # star: four points, centre 690,286, R=72, r=19
  $pts = New-Object System.Collections.Generic.List[System.Drawing.PointF]
  $pts.Add((New-Object System.Drawing.PointF ([float]690), ([float]214)))
  $pts.Add((New-Object System.Drawing.PointF ([float]703.4), ([float]272.6)))
  $pts.Add((New-Object System.Drawing.PointF ([float]762), ([float]286)))
  $pts.Add((New-Object System.Drawing.PointF ([float]703.4), ([float]299.4)))
  $pts.Add((New-Object System.Drawing.PointF ([float]690), ([float]358)))
  $pts.Add((New-Object System.Drawing.PointF ([float]676.6), ([float]299.4)))
  $pts.Add((New-Object System.Drawing.PointF ([float]618), ([float]286)))
  $pts.Add((New-Object System.Drawing.PointF ([float]676.6), ([float]272.6)))
  $g.FillPolygon($brush, $pts.ToArray())

  $g.ResetTransform()
  [void]$bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $brush.Dispose()
  $hull.Dispose()
  $sail.Dispose()
  $g.Dispose()
  [void]$bmp.Dispose()
  $path
}

$black = New-MarkIcon "$outDir\logo-v2-black.png" $true
$white = New-MarkIcon "$outDir\logo-v2-white.png" $false

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
[void]$sheet.Save("$outDir\logo-v2-scale.png", [System.Drawing.Imaging.ImageFormat]::Png)
$src.Dispose()
[void]$sheet.Dispose()
$font.Dispose()
$brushTxt.Dispose()

"$outDir\logo-v2-scale.png"
