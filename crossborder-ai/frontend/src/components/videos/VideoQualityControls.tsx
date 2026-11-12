import { useEffect, useState } from 'react'
import { Bot, Clapperboard, Sparkles, WandSparkles } from 'lucide-react'
import { Label } from '@/components/ui/label'
import {
  availableVideoProviders,
  providerDefaultQualityTier,
  qualityTierCredits,
  recommendedQualityTier,
  tiersForProvider,
  videoProviderHint,
  videoProviderLabel,
  type VideoProvider,
  type VideoProviderMode,
  type VideoQualityContext,
  type VideoQualityTier,
  type VideoStylePreset,
} from '@/lib/videos/quality'

interface VideoQualityControlsProps {
  tiers: VideoQualityTier[]
  styles: VideoStylePreset[]
  qualityTier: string
  stylePreset: string
  duration?: number
  context: VideoQualityContext
  onQualityTierChange: (value: string) => void
  onStylePresetChange: (value: string) => void
}

const ENGINE_OPTIONS: Array<{
  id: VideoProviderMode
  label: string
  icon: typeof WandSparkles
}> = [
  { id: 'auto', label: '自动', icon: WandSparkles },
  { id: 'minimax', label: 'MiniMax', icon: Bot },
  { id: 'jimeng', label: '即梦', icon: Clapperboard },
]

/** 三个视频入口共用的质量档位和导演风格控制。 */
export function VideoQualityControls({
  tiers,
  styles,
  qualityTier,
  stylePreset,
  duration,
  context,
  onQualityTierChange,
  onStylePresetChange,
}: VideoQualityControlsProps) {
  const [providerMode, setProviderMode] = useState<VideoProviderMode>('auto')
  const tier = tiers.find((item) => item.id === qualityTier)
  const style = styles.find((item) => item.id === stylePreset)
  const providers = availableVideoProviders(tiers)
  const visibleTiers = providerMode === 'auto'
    ? tiers
    : tiersForProvider(tiers, providerMode)
  const credits = duration
    ? qualityTierCredits(tiers, qualityTier, duration)
    : 0

  useEffect(() => {
    if (!tiers.length) return
    if (providerMode === 'auto') {
      const recommended = recommendedQualityTier(tiers, context)
      if (recommended && recommended.id !== qualityTier) {
        onQualityTierChange(recommended.id)
      }
      return
    }
    const providerTiers = tiersForProvider(tiers, providerMode)
    if (!providerTiers.some((item) => item.id === qualityTier)) {
      const fallback = providerDefaultQualityTier(tiers, providerMode)
      if (fallback) onQualityTierChange(fallback.id)
    }
  }, [context, onQualityTierChange, providerMode, qualityTier, tiers])

  const selectProvider = (nextMode: VideoProviderMode) => {
    setProviderMode(nextMode)
    if (nextMode === 'auto') {
      const recommended = recommendedQualityTier(tiers, context)
      if (recommended) onQualityTierChange(recommended.id)
      return
    }
    const fallback = providerDefaultQualityTier(tiers, nextMode)
    if (fallback) onQualityTierChange(fallback.id)
  }

  const selectQuality = (nextTierId: string) => {
    const nextTier = tiers.find((item) => item.id === nextTierId)
    if (nextTier?.provider === 'minimax' || nextTier?.provider === 'jimeng') {
      setProviderMode(nextTier.provider as VideoProvider)
    }
    onQualityTierChange(nextTierId)
  }

  const activeProvider = providerMode === 'auto'
    ? tier?.provider
    : providerMode

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label>生成引擎</Label>
        <div className="grid grid-cols-3 overflow-hidden border border-input bg-background">
          {ENGINE_OPTIONS.map((option) => {
            const Icon = option.icon
            const disabled = option.id !== 'auto' && !providers.includes(option.id)
            const selected = providerMode === option.id
            return (
              <button
                key={option.id}
                type="button"
                aria-pressed={selected}
                disabled={disabled}
                title={disabled ? '管理员尚未配置该视频引擎' : undefined}
                onClick={() => selectProvider(option.id)}
                className={[
                  'flex h-9 items-center justify-center gap-1.5 border-r border-input px-2 text-[10px] font-medium transition-colors last:border-r-0 sm:text-[11px]',
                  selected
                    ? 'bg-[color:var(--factory-accent)] text-[color:var(--factory-accent-foreground)]'
                    : 'bg-background text-muted-foreground hover:bg-muted hover:text-foreground',
                  disabled ? 'cursor-not-allowed opacity-40 hover:bg-background' : '',
                ].join(' ')}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                {option.label}
              </button>
            )
          })}
        </div>
        <p className="text-[10px] leading-4 text-muted-foreground">
          {providerMode === 'auto'
            ? `按当前创作模式自动匹配。${videoProviderHint(tier?.provider || '')}`
            : videoProviderHint(providerMode)}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="video-quality-tier">质量档位</Label>
          <select
            id="video-quality-tier"
            value={qualityTier}
            onChange={(event) => selectQuality(event.target.value)}
            className="h-9 w-full border border-input bg-background px-2 text-[11px] outline-none focus:ring-2 focus:ring-ring"
          >
            {visibleTiers.map((item) => (
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
                ? `${videoProviderLabel(tier.provider)} · ${tier.name} · ${tier.resolution} · ${tier.credits_per_second} 积分/秒`
                : '请选择质量档位'}
            </p>
            <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
              {providerMode === 'auto'
                ? `已为你匹配 ${videoProviderLabel(activeProvider || '')}。`
                : style?.description || '使用平台默认视觉方向'}
              {credits > 0 ? ` · 本镜头预计 ${credits} 积分` : ''}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
