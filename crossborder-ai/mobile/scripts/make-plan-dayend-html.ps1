Add-Type -AssemblyName System.Drawing

$root = 'D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22'
$pairs = @(
  @{ src = 'D:\Project\crossborder-ai\mobile\artifacts\ref\design-plan.png'; cap = '设计稿' },
  @{ src = 'D:\Project\crossborder-ai\mobile\artifacts\ui-verify-v66\plan\home-390x844.png'; cap = '实现 v66' }
)

$b64 = @()
foreach ($p in $pairs) {
  $im = [System.Drawing.Image]::FromFile($p.src)
  $w = 420
  $h = [int]($im.Height * $w / $im.Width)
  $bmp = New-Object System.Drawing.Bitmap($w, $h)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.DrawImage($im, 0, 0, $w, $h)
  $g.Dispose(); $im.Dispose()
  $ms = New-Object System.IO.MemoryStream
  $enc = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
  $ep = New-Object System.Drawing.Imaging.EncoderParameters(1)
  $ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, 86)
  $bmp.Save($ms, $enc, $ep)
  $bmp.Dispose()
  $b64 += [Convert]::ToBase64String($ms.ToArray())
  $ms.Dispose()
}

$html = @"
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>今日计划 · 日结行移出白卡</title>
<style>
  body { margin:0; padding:40px 32px 56px; background:#F2F3F5; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; color:#111419; }
  h1 { font-size:22px; margin:0 0 6px; letter-spacing:-0.2px; }
  .sub { color:#68707C; font-size:13px; margin-bottom:26px; }
  .row { display:flex; gap:28px; align-items:flex-start; }
  figure { margin:0; background:#fff; border-radius:18px; padding:14px; box-shadow:0 10px 26px rgba(17,20,25,.07); }
  figure img { display:block; width:420px; border-radius:10px; }
  figcaption { margin-top:10px; font-size:12px; color:#68707C; text-align:center; }
  .notes { margin-top:30px; background:#fff; border-radius:18px; padding:22px 24px; max-width:900px; box-shadow:0 10px 26px rgba(17,20,25,.07); }
  .notes h2 { font-size:14px; margin:0 0 12px; }
  .notes li { font-size:13px; line-height:1.85; color:#22262D; }
  .notes li b { font-weight:600; }
  code { background:#F0F2F5; border-radius:5px; padding:1px 5px; font-size:12px; }
</style>
</head>
<body>
  <h1>今日计划 · 日结行已移出「Agent 进度」白卡</h1>
  <div class="sub">左为设计稿，右为当前实现（v66，390×844）。白卡只留 2 项进度，日结改为卡外独立行，空心圆 + 倒计时。</div>
  <div class="row">
    <figure><img src="data:image/jpeg;base64,$($b64[0])" alt=""><figcaption>设计稿</figcaption></figure>
    <figure><img src="data:image/jpeg;base64,$($b64[1])" alt=""><figcaption>实现 v66</figcaption></figure>
  </div>
  <div class="notes">
    <h2>这一版改了什么</h2>
    <ul>
      <li><b>日结不再进卡</b>：<code>dayEndRow</code> 从 <code>progressCard</code> 内部移到卡外，去掉 <code>borderTop</code> 分割线与白底，只留 12px 间距。</li>
      <li><b>卡片只装 2 项</b>：与稿一致 —— 同步 3 个 SKU 库存、持续观察评价回复；计数仍是「2 项」。</li>
      <li><b>卡外行结构</b>：空心圆（未开始）→ 20:00 日结 → 副文「Agent 整理一天的结果和明日计划」→ 右「10 小时后」。</li>
      <li><b>像素核对</b>：v65 白卡纵向一直延伸到日结行底部（含日结），v66 白卡底边提前 66px 收住，日结文字落在卡外。</li>
    </ul>
  </div>
</body>
</html>
"@

$out = Join-Path $root 'plan-dayend.html'
[System.IO.File]::WriteAllText($out, $html, (New-Object System.Text.UTF8Encoding($false)))
"$out  $([math]::Round((Get-Item $out).Length/1KB))KB"
