Add-Type -AssemblyName System.Drawing

$root = 'D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22'
$rows = @(
  @{ n = 1; name = '首页'; d = '..\ref\design-home.png'; i = '..\ui-verify-v65\home\home-390x844.png' },
  @{ n = 2; name = '今日计划'; d = '..\ref\design-plan.png'; i = '..\ui-verify-v66\plan\home-390x844.png' },
  @{ n = 3; name = '登录'; d = '..\design-2026-11-22-round2\13-login.png'; i = '..\ui-verify-v63\login\home-390x844.png' },
  @{ n = 4; name = '创建账号'; d = '..\design-2026-11-22-round2\04-signup.png'; i = '..\ui-verify-v63\signup\home-390x844.png' },
  @{ n = 5; name = '全部功能'; d = '..\design-2026-11-22-round2\09-functions.png'; i = '..\ui-verify-v63\functions\home-390x844.png' },
  @{ n = 6; name = '通知中心'; d = '..\design-2026-11-22-round2\01-notification.png'; i = '..\ui-verify-v63\activity\home-390x844.png' },
  @{ n = 7; name = '账号'; d = '..\design-2026-11-22-round2\02-account.png'; i = '..\ui-verify-v63\account\home-390x844.png' },
  @{ n = 8; name = '素材库'; d = '..\design-2026-11-22-round2\10-library.png'; i = '..\ui-verify-v63\library\home-390x844.png' },
  @{ n = 9; name = '等待决定'; d = '..\design-2026-11-22-round2\11-task-waiting.png'; i = '..\ui-verify-v63\task-waiting\home-390x844.png' },
  @{ n = 10; name = '选单'; d = '..\design-2026-11-22-round2\05-task-select.png'; i = '..\ui-verify-v63\task-select\home-390x844.png' },
  @{ n = 11; name = '素材成功'; d = '..\design-2026-11-22-round2\06-task-media-ok.png'; i = '..\ui-verify-v63\media-ok\home-390x844.png' },
  @{ n = 12; name = '素材失败'; d = '..\design-2026-11-22-round2\00-task-media-fail.png'; i = '..\ui-verify-v63\media-fail\home-390x844.png' },
  @{ n = 13; name = '已完成'; d = '..\design-2026-11-22-round2\07-task-done.png'; i = '..\ui-verify-v63\done\home-390x844.png' },
  @{ n = 14; name = '确认面板'; d = '..\design-2026-11-22-round2\12-confirm-sheet.png'; i = '..\ui-verify-v63\confirm-sheet\home-390x844.png' },
  @{ n = 15; name = 'Agent 回执'; d = '..\design-2026-11-22-round2\03-agent-turn.png'; i = '..\ui-verify-v63\agent\home-390x844.png' },
  @{ n = 16; name = '空态合集'; d = '..\design-2026-11-22-round2\08-states.png'; i = $null }
)

function Analyze($path) {
  if (-not $path -or -not (Test-Path $path)) { return $null }
  $img = [System.Drawing.Image]::FromFile($path)
  $W = 195
  $H = [int]($img.Height * $W / $img.Width)
  $bmp = New-Object System.Drawing.Bitmap($img, $W, $H)
  $img.Dispose()

  $n = $W * $H
  $white = New-Object bool[] $n
  $colored = New-Object bool[] $n
  $lineGray = New-Object bool[] $n
  $colorCount = 0
  for ($y = 0; $y -lt $H; $y++) {
    for ($x = 0; $x -lt $W; $x++) {
      $c = $bmp.GetPixel($x, $y)
      $idx = $y * $W + $x
      if ($c.R -ge 249 -and $c.G -ge 249 -and $c.B -ge 249) { $white[$idx] = $true }
      # 语义色：蓝 / 琥珀 / 绿 / 红（含浅底）
      $isBlue = ($c.B -gt 150 -and $c.B - $c.R -gt 60 -and $c.B - $c.G -gt 40)
      $isAmber = (($c.R -gt 210 -and $c.G -gt 140 -and $c.G -lt 200 -and $c.B -lt 130) -or ($c.R -gt 240 -and $c.G -gt 220 -and $c.B -gt 185 -and $c.B -lt 215))
      $isGreen = ($c.G -gt 120 -and $c.G - $c.R -gt 40 -and $c.G - $c.B -gt 20)
      $isRed = ($c.R -gt 150 -and $c.R - $c.G -gt 70 -and $c.B -lt 90)
      if ($isBlue -or $isAmber -or $isGreen -or $isRed) { $colored[$idx] = $true; $colorCount++ }
      # 浅灰分割线（#E9EBEE 附近）
      if ([math]::Abs($c.R - 235) -lt 12 -and [math]::Abs($c.G - 237) -lt 12 -and [math]::Abs($c.B - 240) -lt 12) { $lineGray[$idx] = $true }
    }
  }

  # 白色连通块（卡片），面积 >= 1.2% 面积
  $minArea = [int]($n * 0.012)
  $seen = New-Object bool[] $n
  $blocks = 0
  $stack = New-Object System.Collections.Generic.Stack[int]
  for ($start = 0; $start -lt $n; $start++) {
    if (-not $white[$start] -or $seen[$start]) { continue }
    $stack.Clear(); $stack.Push($start); $seen[$start] = $true; $area = 0
    while ($stack.Count -gt 0) {
      $p = $stack.Pop(); $area++
      $py = [int][math]::Floor($p / $W); $px = $p - $py * $W
      foreach ($d in @(@(1, 0), @(-1, 0), @(0, 1), @(0, -1))) {
        $nx = $px + $d[0]; $ny = $py + $d[1]
        if ($nx -lt 0 -or $ny -lt 0 -or $nx -ge $W -or $ny -ge $H) { continue }
        $q = $ny * $W + $nx
        if ($white[$q] -and -not $seen[$q]) { $seen[$q] = $true; $stack.Push($q) }
      }
    }
    if ($area -ge $minArea) { $blocks++ }
  }

  # 横向长分割线（连续浅灰 >= 55% 宽的行）
  $lines = 0
  for ($y = 0; $y -lt $H; $y++) {
    $run = 0; $best = 0
    for ($x = 0; $x -lt $W; $x++) {
      if ($lineGray[$y * $W + $x]) { $run++; if ($run -gt $best) { $best = $run } } else { $run = 0 }
    }
    if ($best -gt ($W * 0.55)) { $lines++ }
  }

  $bmp.Dispose()
  [pscustomobject]@{
    colorPct = [math]::Round($colorCount * 100.0 / $n, 2)
    cards = $blocks
    hairlines = $lines
  }
}

$out = @()
foreach ($r in $rows) {
  $d = Analyze (Join-Path $root $r.d)
  $ip = if ($r.i) { Join-Path $root $r.i } else { $null }
  $i = Analyze $ip
  $out += [pscustomobject]@{
    n = $r.n; page = $r.name
    稿_彩色百分比 = if ($d) { $d.colorPct } else { '' }
    稿_白卡数 = if ($d) { $d.cards } else { '' }
    稿_长分割线 = if ($d) { $d.hairlines } else { '' }
    实现_彩色百分比 = if ($i) { $i.colorPct } else { '' }
    实现_白卡数 = if ($i) { $i.cards } else { '' }
    实现_长分割线 = if ($i) { $i.hairlines } else { '' }
  }
}
$csv = 'D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22\metrics.csv'
$out | Export-Csv -Path $csv -NoTypeInformation -Encoding UTF8
$out | Format-Table -AutoSize | Out-String -Width 220
