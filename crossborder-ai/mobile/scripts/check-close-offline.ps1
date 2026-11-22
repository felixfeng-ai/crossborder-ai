Add-Type -AssemblyName System.Drawing

function Inspect($path, $x0, $x1, $y0, $y1, $label) {
  $img = [System.Drawing.Bitmap]::FromFile($path)
  $dark = 0; $amber = 0; $total = 0
  for ($y = $y0; $y -lt $y1; $y++) {
    for ($x = $x0; $x -lt $x1; $x++) {
      $c = $img.GetPixel($x, $y)
      $total++
      if ($c.R -lt 90 -and $c.G -lt 90 -and $c.B -lt 95) { $dark++ }
      if ([math]::Abs($c.R - 251) -lt 12 -and [math]::Abs($c.G - 232) -lt 14 -and [math]::Abs($c.B - 200) -lt 20) { $amber++ }
    }
  }
  $img.Dispose()
  "$label dark=$dark amber=$amber total=$total ratio=$([math]::Round($amber * 100 / $total, 2))%"
}

Inspect 'D:\Project\crossborder-ai\mobile\artifacts\ui-verify-v68\plan\home-390x844.png' 600 780 0 240 'PLAN-X(top-right)'
Inspect 'D:\Project\crossborder-ai\mobile\artifacts\ui-verify-v68\offline\home-390x844.png' 0 780 0 140 'OFFLINE-BANNER'
