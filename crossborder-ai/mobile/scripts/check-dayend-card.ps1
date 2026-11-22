Add-Type -AssemblyName System.Drawing

# 沿卡内空白竖列（x=30）找最长纯白段 = 白卡本体；卡外背景是 #F2F3F5，不会误判。
function Get-CardBand($path, $col) {
  $img = [System.Drawing.Image]::FromFile($path)
  $h = $img.Height
  $bmp = New-Object System.Drawing.Bitmap($img)
  $runs = @()
  $start = -1
  for ($y = 0; $y -lt $h; $y++) {
    $c = $bmp.GetPixel($col, $y)
    $isWhite = ($c.R -ge 250 -and $c.G -ge 250 -and $c.B -ge 250)
    if ($isWhite) {
      if ($start -lt 0) { $start = $y }
    }
    elseif ($start -ge 0) {
      if (($y - $start) -gt 8) { $runs += @{ s = $start; e = $y - 1; len = $y - 1 - $start } }
      $start = -1
    }
  }
  if ($start -ge 0) { $runs += @{ s = $start; e = $h - 1; len = $h - 1 - $start } }
  $bmp.Dispose(); $img.Dispose()
  $runs | Sort-Object { $_.len } -Descending | Select-Object -First 3
}

function Get-DarkTextRows($path, $fromY, $toY) {
  $img = [System.Drawing.Image]::FromFile($path)
  $w = $img.Width; $h = $img.Height
  $bmp = New-Object System.Drawing.Bitmap($img)
  $hit = @()
  $fromY = [math]::Max(0, $fromY); $toY = [math]::Min($h - 1, $toY)
  for ($y = $fromY; $y -le $toY; $y += 2) {
    $n = 0
    for ($x = 24; $x -lt ($w - 24); $x += 3) {
      $c = $bmp.GetPixel($x, $y)
      if ($c.R -lt 110 -and $c.G -lt 110 -and $c.B -lt 110) { $n++ }
    }
    if ($n -gt 4) { $hit += $y }
  }
  $bmp.Dispose(); $img.Dispose()
  if ($hit.Count -eq 0) { return $null }
  [pscustomobject]@{ first = $hit[0]; last = $hit[-1]; rows = $hit.Count }
}

foreach ($v in @('v65', 'v66')) {
  $f = "D:\Project\crossborder-ai\mobile\artifacts\ui-verify-$v\plan\home-390x844.png"
  "=== $v ==="
  $bands = Get-CardBand $f 700
  foreach ($b in $bands) { "  white-run y=$($b.s)..$($b.e) len=$($b.len)" }
  if (-not $bands) { "  no white band" ; continue }
  $card = $bands[0]
  $t = Get-DarkTextRows $f ($card.e + 4) ($card.e + 130)
  if ($t) { "  below-card text y=$($t.first)..$($t.last) rows=$($t.rows)" } else { "  below-card text: none" }
}
