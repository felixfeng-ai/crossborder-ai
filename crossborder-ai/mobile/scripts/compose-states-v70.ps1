Add-Type -AssemblyName System.Drawing
$root = "D:\Project\crossborder-ai\mobile\artifacts"
$sheet = [System.Drawing.Image]::FromFile("$root\ref\states-4in1.png")
$cellW = 300
$cellH = 620
$pad = 12
$states = @("select", "media-ok", "media-fail", "done")
$W = 4 * $cellW + 5 * $pad
$H = 2 * $cellH + 3 * $pad
$bmp = New-Object System.Drawing.Bitmap($W, $H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 242, 243, 245))
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$srcW = [int]($sheet.Width / 4)
$crops = @(
  @(38, 252),
  @(282, 252),
  @(520, 252),
  @(764, 252)
)
for ($i = 0; $i -lt 4; $i++) {
  $x = $pad + $i * ($cellW + $pad)
  $cropX = $crops[$i][0]
  $cropW = $crops[$i][1]
  $srcRect = New-Object System.Drawing.Rectangle $cropX, 0, $cropW, $sheet.Height
  $dstRect = New-Object System.Drawing.Rectangle $x, $pad, $cellW, $cellH
  $g.DrawImage($sheet, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
  $impl = [System.Drawing.Image]::FromFile("$root\ui-verify-v70\$($states[$i])\home-390x844.png")
  $ratio = [Math]::Min($cellW / $impl.Width, $cellH / $impl.Height)
  $dw = [int]($impl.Width * $ratio)
  $dh = [int]($impl.Height * $ratio)
  $dx = $x + [int](($cellW - $dw) / 2)
  $g.DrawImage($impl, $dx, (2 * $pad + $cellH), $dw, $dh)
  $impl.Dispose()
}
$out = "$root\ui-review-2026-11-22\states-four-v70.png"
[void]$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
[void]$bmp.Dispose()
[void]$sheet.Dispose()
"$out"
