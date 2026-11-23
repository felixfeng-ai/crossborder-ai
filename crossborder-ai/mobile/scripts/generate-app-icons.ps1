Add-Type -AssemblyName System.Drawing

$assets = Join-Path $PSScriptRoot "..\assets"
$masterPath = Join-Path $assets "brand\app-mark.png"
$foregroundPath = Join-Path $assets "android-icon-foreground.png"

function Save-Png([System.Drawing.Bitmap]$bitmap, [string]$path) {
  $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
}

# 首次执行时从现有透明前景图生成唯一主标；之后只从主标复制，避免重复缩放。
if (-not (Test-Path $masterPath)) {
  $source = [System.Drawing.Bitmap]::FromFile($foregroundPath)
  $master = [System.Drawing.Bitmap]::new(512, 512, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $graphics = [System.Drawing.Graphics]::FromImage($master)
  $graphics.Clear([System.Drawing.Color]::Transparent)
  $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceOver
  $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
  $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

  # 当前 V 主体中心约在 x=218，整体纵向中心约在 y=255.5。
  # 缩放 88% 后把 V 中心校正到 256，并将星点保留在右上。
  $scale = 0.88
  $drawX = 256 - 218 * $scale
  $drawY = 256 - 255.5 * $scale
  $drawSize = 512 * $scale
  $destination = [System.Drawing.RectangleF]::new($drawX, $drawY, $drawSize, $drawSize)
  $graphics.DrawImage($source, $destination)

  $graphics.Dispose()
  $source.Dispose()
  Save-Png $master $masterPath
  $master.Dispose()
}

$master = [System.Drawing.Bitmap]::FromFile($masterPath)

# Android 自适应图标：透明前景 + 纯墨色背景。
Copy-Item -LiteralPath $masterPath -Destination $foregroundPath -Force

$background = [System.Drawing.Bitmap]::new(512, 512, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$backgroundGraphics = [System.Drawing.Graphics]::FromImage($background)
$backgroundGraphics.Clear([System.Drawing.Color]::FromArgb(255, 11, 14, 18))
$backgroundGraphics.Dispose()
Save-Png $background (Join-Path $assets "android-icon-background.png")
$background.Dispose()

# 旧版 Android 与商店图标使用同一标记，保证侧载安装页和桌面图标一致。
$appIcon = [System.Drawing.Bitmap]::new(1024, 1024, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$appIconGraphics = [System.Drawing.Graphics]::FromImage($appIcon)
$appIconGraphics.Clear([System.Drawing.Color]::FromArgb(255, 11, 14, 18))
$appIconGraphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
$appIconGraphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$appIconGraphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$appIconGraphics.DrawImage($master, 0, 0, 1024, 1024)
$appIconGraphics.Dispose()
Save-Png $appIcon (Join-Path $assets "icon.png")

$favicon = [System.Drawing.Bitmap]::new(48, 48, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$faviconGraphics = [System.Drawing.Graphics]::FromImage($favicon)
$faviconGraphics.Clear([System.Drawing.Color]::FromArgb(255, 11, 14, 18))
$faviconGraphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
$faviconGraphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$faviconGraphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$faviconGraphics.DrawImage($appIcon, 0, 0, 48, 48)
$faviconGraphics.Dispose()
Save-Png $favicon (Join-Path $assets "favicon.png")
$favicon.Dispose()
$appIcon.Dispose()

# Android 单色图标只需要保留形状 alpha，系统会统一着色。
$monochrome = [System.Drawing.Bitmap]::new(432, 432, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
for ($y = 0; $y -lt 432; $y++) {
  for ($x = 0; $x -lt 432; $x++) {
    $sx = [Math]::Min(511, [int][Math]::Floor($x * 512 / 432))
    $sy = [Math]::Min(511, [int][Math]::Floor($y * 512 / 432))
    $alpha = $master.GetPixel($sx, $sy).A
    if ($alpha -gt 0) {
      $monochrome.SetPixel(
        $x,
        $y,
        [System.Drawing.Color]::FromArgb($alpha, 255, 255, 255)
      )
    }
  }
}
Save-Png $monochrome (Join-Path $assets "android-icon-monochrome.png")
$monochrome.Dispose()

# 启动图是透明画布：白色主体改为墨色，星点保留暖金。
$darkMaster = [System.Drawing.Bitmap]::new(512, 512, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
for ($y = 0; $y -lt 512; $y++) {
  for ($x = 0; $x -lt 512; $x++) {
    $pixel = $master.GetPixel($x, $y)
    if ($pixel.A -eq 0) { continue }
    $color = if ($pixel.R -gt 200 -and $pixel.G -gt 200 -and $pixel.B -gt 200) {
      [System.Drawing.Color]::FromArgb($pixel.A, 11, 14, 18)
    } else {
      [System.Drawing.Color]::FromArgb($pixel.A, 231, 163, 58)
    }
    $darkMaster.SetPixel($x, $y, $color)
  }
}

$splash = [System.Drawing.Bitmap]::new(1024, 1024, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$splashGraphics = [System.Drawing.Graphics]::FromImage($splash)
$splashGraphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
$splashGraphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$splashGraphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$splashGraphics.DrawImage($darkMaster, 0, 0, 1024, 1024)
$splashGraphics.Dispose()
Save-Png $splash (Join-Path $assets "splash-icon.png")
$splash.Dispose()
$darkMaster.Dispose()
$master.Dispose()

Write-Output "VeyaShip app icon assets regenerated."
