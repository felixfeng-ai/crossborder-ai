import { Sparkles } from 'lucide-react'
import { Label } from '@/components/ui/label'
import {
  qualityTierCredits,
  type VideoQualityTier,
  type VideoStylePreset,
} from '@/lib/videos/quality'

interface VideoQualityControlsProps {
  tiers: VideoQualityTier[]
  styles: VideoStylePreset[]
  qualityTier: string
  stylePreset: string
  duration?: number
  onQualityTierChange: (value: string) => void
  onStylePresetChange: (value: string) => void
}

/** 三个视频入口共用的质量档位和导演风格控制。 */
export function VideoQualityControls({
  tiers,
  styles,
  qualityTier,
  stylePreset,
  duration,
  onQualityTierChange,
  onStylePresetChange,
}: VideoQualityControlsProps) {
  const tier = tiers.find((item) => item.id === qualityTier)
  const style = styles.find((item) => item.id === stylePreset)
  const credits = duration
    ? qualityTierCredits(tiers, qualityTier, duration)
    : 0

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="video-quality-tier">质量档位</Label>
          <select
            id="video-quality-tier"
            value={qualityTier}
            onChange={(event) => onQualityTierChange(event.target.value)}
            className="h-9 w-full border border-input bg-background px-2 text-[11px] outline-none focus:ring-2 focus:ring-ring"
          >
            {tiers.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="video-style-preset">画面风格</Label>
          <select
            id="video-style-preset"
            value={stylePreset}
            onChange={(event) => onStylePresetChange(event.target.value)}
            className="h-9 w-full border border-input bg-background px-2 text-[11px] outline-none focus:ring-2 focus:ring-ring"
          >
            {styles.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="border border-border bg-background px-3 py-2.5">
        <div className="flex items-start gap-2">
          <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--factory-accent)]" />
          <div className="min-w-0">
            <p className="text-[11px] font-medium">
              {tier
                ? `${tier.model.replace('MiniMax-', '')} · ${tier.resolution} · ${tier.credits_per_second} 积分/秒`
                : '请选择质量档位'}
            </p>
            <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
              {style?.description || '使用平台默认视觉方向'}
              {credits > 0 ? ` · 本镜头预计 ${credits} 积分` : ''}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
