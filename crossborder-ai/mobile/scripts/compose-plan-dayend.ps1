Add-Type -AssemblyName System.Drawing

# 通用两图并排：左稿右实现，等高缩放。
$out = 'D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22\plan-dayend-fix.png'
$items = @(
  @{ p = 'D:\Project\crossborder-ai\mobile\artifacts\ref\design-plan.png'; t = 'DESIGN' },
  @{ p = 'D:\Project\crossborder-ai\mobile\artifacts\ui-verify-v66\plan\home-390x844.png'; t = 'IMPLEMENTED (v66)' }
)
$target = 1180
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
$gap = 44; $pad = 44; $head = 60
$totalW = $pad * 2 + $sumW + $gap * ($imgs.Count - 1)
$totalH = $pad * 2 + $head + $target
$canvas = New-Object System.Drawing.Bitmap($totalW, $totalH)
$g2 = [System.Drawing.Graphics]::FromImage($canvas)
$g2.Clear([System.Drawing.Color]::FromArgb(242, 243, 245))
$g2.TextRenderingHint = 'AntiAliasGridFit'
$font = New-Object System.Drawing.Font('Consolas', 21, [System.Drawing.FontStyle]::Bold)
$x = $pad
foreach ($it in $imgs) {
  $g2.DrawString($it.t, $font, [System.Drawing.Brushes]::Black, [single]$x, [single]36)
  $g2.DrawImage($it.bmp, $x, $pad + $head, $it.w, $target)
  $x += $it.w + $gap
}
$g2.Dispose()
$canvas.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$canvas.Dispose()
foreach ($it in $imgs) { $it.bmp.Dispose() }
$chk = [System.Drawing.Image]::FromFile($out)
"$out  $($chk.Width) x $($chk.Height)  $([math]::Round((Get-Item $out).Length/1KB))KB"
$chk.Dispose()
