Add-Type -AssemblyName System.Drawing
$root = "D:\Project\crossborder-ai\mobile\artifacts"
$src = "$root\ref\states-4in1.png"
$sheet = [System.Drawing.Image]::FromFile($src)
$crops = @(
  @(38, 252, "14-task-select.png"),
  @(282, 252, "15-task-media-ok.png"),
  @(520, 252, "16-task-media-fail.png"),
  @(764, 252, "17-task-done.png")
)
foreach ($crop in $crops) {
  $rect = New-Object System.Drawing.Rectangle $crop[0], 0, $crop[1], $sheet.Height
  $bmp = New-Object System.Drawing.Bitmap $crop[1], $sheet.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.DrawImage($sheet, (New-Object System.Drawing.Rectangle 0, 0, $crop[1], $sheet.Height), $rect, [System.Drawing.GraphicsUnit]::Pixel)
  $out = "$root\design-2026-11-22-round2\$($crop[2])"
  [void]$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose()
  [void]$bmp.Dispose()
  "$out"
}
[void]$sheet.Dispose()
