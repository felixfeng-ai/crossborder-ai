Add-Type -AssemblyName System.Drawing

$out = 'D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22\states-v68.png'
$items = @(
  @{ p = 'D:\Project\crossborder-ai\mobile\artifacts\ui-verify-v68\empty\home-390x844.png'; t = 'EMPTY' },
  @{ p = 'D:\Project\crossborder-ai\mobile\artifacts\ui-verify-v68\loading\home-390x844.png'; t = 'LOADING' },
  @{ p = 'D:\Project\crossborder-ai\mobile\artifacts\ui-verify-v68\offline\home-390x844.png'; t = 'OFFLINE' }
)
$target = 1000
$imgs = @(); $sumW = 0
foreach ($i in $items) {
  $im = [System.Drawing.Image]::FromFile($i.p)
  $nh = $target
  $nw = [int]($im.Width * $nh / $im.Height)
  $bmp = New-Object System.Drawing.Bitmap($nw, $nh)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.DrawImage($im, 0, 0, $nw, $nh)
  $g.Dispose(); $im.Dispose()
  $imgs += @{ bmp = $bmp; t = $i.t; w = $nw }
  $sumW += $nw
}
$gap = 36; $pad = 36; $head = 52
$totalW = $pad * 2 + $sumW + $gap * ($imgs.Count - 1)
$totalH = $pad * 2 + $head + $target
$canvas = New-Object System.Drawing.Bitmap($totalW, $totalH)
$g2 = [System.Drawing.Graphics]::FromImage($canvas)
$g2.Clear([System.Drawing.Color]::FromArgb(242, 243, 245))
$g2.TextRenderingHint = 'AntiAliasGridFit'
$font = New-Object System.Drawing.Font('Consolas', 19, [System.Drawing.FontStyle]::Bold)
$x = $pad
foreach ($it in $imgs) {
  $g2.DrawString($it.t, $font, [System.Drawing.Brushes]::Black, [single]$x, [single]30)
  $g2.DrawImage($it.bmp, $x, $pad + $head, $it.w, $target)
  $x += $it.w + $gap
}
$g2.Dispose()
[void]$canvas.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$canvas.Dispose()
foreach ($it in $imgs) { [void]$it.bmp.Dispose() }
$chk = [System.Drawing.Image]::FromFile($out)
"OK $($chk.Width)x$($chk.Height) $([math]::Round((Get-Item $out).Length/1KB))KB"
$chk.Dispose()
