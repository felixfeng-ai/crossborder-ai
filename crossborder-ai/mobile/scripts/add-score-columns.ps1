$p = 'D:\Project\crossborder-ai\mobile\artifacts\ui-review-2026-11-22\compare.html'
$t = [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)

# 每页：还原度 / 没到 100% 的原因 / 更符合 iOS 简约
$data = @{
  1  = @{ s = '96%'; w = '黑卡 249pt vs 稿 247pt（−2pt）；字体度量、iOS 字距与阴影渲染无法逐像素对齐'; x = '实现 · 字号收成 3 档、彩色只留语义' }
  2  = @{ s = '88%'; w = '缺右上 ✕ 关闭（头部只给了 ‹ 返回）；黑卡 282pt vs 稿 292pt；倒计时是真实时间'; x = '实现 · 少一层标题、无多余胶囊' }
  3  = @{ s = '97%'; w = '可见文案逐字一致；输入框占位符不在截图文本层，未做像素核对；字体渲染差异'; x = '持平 · 稿与实现都是单列＋一条黑按钮' }
  4  = @{ s = '92%'; w = '结构与稿一致，但字号与 52pt 按钮高度尚未逐像素核对（未验证项）'; x = '持平 · 三框＋黑按钮结构同构' }
  5  = @{ s = '91%'; w = '「客户与评价」整组未做（客户消息只留在常用区）；徽标数字按真实计数，稿是示例 3/2/4/1'; x = '实现 · 彩色占比 0.61% vs 稿 0.85%' }
  6  = @{ s = '93%'; w = '「全部已读」缺接口（只有 read_at，没有标记接口）；分组卡数少于稿'; x = '实现 · 蓝只用于未读，删掉类型胶囊' }
  7  = @{ s = '88%'; w = '行文案走真实字段（当前工作区/我的角色/工作区类型），稿写店铺连接/团队成员/数据导出；稿的「提醒·通知中心」入口已删'; x = '实现 · 4 张白卡、无彩色块' }
  8  = @{ s = '89%'; w = '筛选行未做（素材无分类字段）；工具条 4 项 vs 稿 3 项'; x = '稿 · 筛选行把层级收成一条' }
  9  = @{ s = '95%'; w = '稿多一行「剩余时间 4 小时 48 分」；主按钮文案改用 action label'; x = '实现 · 单黑按钮收口' }
  10 = @{ s = '97%'; w = '结构逐项对上；选中描边 1.5px 与稿等效，字体渲染差异'; x = '持平 · 两行候选＋一条底部按钮' }
  11 = @{ s = '96%'; w = '图下尺寸未写（生成结果只回 url，无宽高字段）'; x = '实现 · 三图等分、双按钮并排' }
  12 = @{ s = '94%'; w = '「联系支持」无可点入口（项目里没有支持通道，不做假链接）'; x = '实现 · 红只给状态点' }
  13 = @{ s = '96%'; w = '订单短编号胶囊未做（接口只给 uuid）'; x = '实现 · 无按钮、归档文案居中' }
  14 = @{ s = '98%'; w = '订单号显示 #1284/#1285（preview 数据），稿写 #1264'; x = '稿 · 一条琥珀提示概括，字段行更少' }
  15 = @{ s = '94%'; w = '#1264/#1285 胶囊未做（只给 uuid）；三步执行过程文案与稿不同'; x = '持平 · 状态点＋30pt 标题结构同构' }
  16 = @{ s = '78%'; w = '离线横幅未实现；空态/加载没有可复现夹具，未截到实现图'; x = '实现 · 单行空态＋13pt 副文' }
}

$order = 1..16
foreach ($n in $order) {
  $d = $data[$n]
  $cell = '<td class="score"><b>' + $d.s + '</b></td><td class="why">' + $d.w + '</td><td class="simple">' + $d.x + '</td><td class="imgs">'
  $needle = '<td class="num">' + $n + '</td>'
  $i = $t.IndexOf($needle)
  if ($i -lt 0) { "ROW $n not found"; continue }
  $j = $t.IndexOf('<td class="imgs">', $i)
  if ($j -lt 0) { "IMGS $n not found"; continue }
  $t = $t.Substring(0, $j) + $cell + $t.Substring($j + '<td class="imgs">'.Length)
}

# 表头补 3 列
$t = $t.Replace('<th>差异</th><th class="imgs">设计稿 / 实现</th>',
  '<th>差异</th><th>还原度</th><th>没到 100% 的原因</th><th>更符合 iOS 简约</th><th class="imgs">设计稿 / 实现</th>')

# 样式补宽
$t = $t.Replace('td.imgs { width:250px; }',
  'td.imgs { width:250px; } td.score { width:64px; font-variant-numeric:tabular-nums; } td.why { width:230px; } td.simple { width:150px; color:#536071; }')

# 图例与口径说明
$oldLegend = '<span><span class="tag no">未覆盖</span><b>该行没有实现截图或未做</b></span>
</div>'
$newLegend = '<span><span class="tag no">未覆盖</span><b>该行没有实现截图或未做</b></span>
  <span><b>还原度口径</b>：100 起步，结构缺失 −7、功能/接口缺失 −5、尺寸偏差 −3、数据差异 −1、渲染栈固有 −1</span>
</div>'
$t = $t.Replace($oldLegend, $newLegend)

# 结尾加“为什么到不了 100%”
$oldEnd = '<div class="sub" style="margin-top:18px">15 个页面两张对照齐全；第 16 行只有稿。代码侧本轮 8 个源码文件改完，<code>tsc</code> 0 · <code>vitest</code> 41/41 · <code>eslint</code> 0。</div>'
$newEnd = @'
<div class="sub" style="margin-top:18px">15 个页面两张对照齐全；第 16 行只有稿。代码侧 8 个源码文件改完，<code>tsc</code> 0 · <code>vitest</code> 41/41 · <code>eslint</code> 0。</div>

<div style="margin-top:26px;background:#fff;border-radius:14px;padding:22px 26px">
  <div style="font-size:15px;font-weight:600;margin-bottom:10px">为什么都到不了 100%</div>
  <div style="font-size:13px;line-height:1.9;color:#22262D">
    <b>一、数据源缺口（占差异的一半以上）</b><br>
    稿上的尺码、素材分类、订单短编号（#1264）、剩余时间、徽标示例数、支持入口，项目里都没有对应字段或接口。这些位置只能降级显示或不显示，属于「没有数据可选」，不是样式没做。
    <br><br>
    <b>二、产品结构缺口</b><br>
    客户与评价分组、通知「全部已读」、素材库筛选、计划页右上 ✕、离线横幅，是功能层面缺一块，需要后端或交互补，不是调样式能补。
    <br><br>
    <b>三、渲染栈固有差异</b><br>
    实现跑在 Expo + RN Web 预览里，中文是 Noto Sans SC，稿是设计字体；iOS 的字距、行高取整、阴影扩散、圆角抗锯齿都不同。再加稿件是 1044×2259 的非真机渲染、实现是 390×844 真机比例，换算本身有 ±2–3pt 误差。这一项决定「视觉等效」上限约 96–98%，像素级永不为 100%。
  </div>
</div>
'@
$t = $t.Replace($oldEnd, $newEnd)

[System.IO.File]::WriteAllText($p, $t, (New-Object System.Text.UTF8Encoding($false)))

$count = ([regex]'class="score"').Matches($t).Count
$th = ([regex]'<th>还原度</th>').Matches($t).Count
"scoreCells=$count  headerCol=$th"
& 'D:\Project\crossborder-ai\mobile\scripts\make-selfcontained.ps1'
