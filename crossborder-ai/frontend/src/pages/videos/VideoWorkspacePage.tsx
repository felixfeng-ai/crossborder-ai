import { useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Clapperboard } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { videoTabFromSearch, type VideoWorkspaceTab } from '@/lib/navigation'
import MarketingVideosPage from './MarketingVideosPage'
import VideosPage from './VideosPage'


export default function VideoWorkspacePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = videoTabFromSearch(searchParams.toString())

  const switchTab = (value: string) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', value as VideoWorkspaceTab)
    setSearchParams(next, { replace: true })
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-5"
    >
      <div>
        <h1 className="page-title flex items-center gap-2">
          <Clapperboard className="h-6 w-6 text-primary" />
          视频工作台
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
          在营销成片和单镜头生成之间切换，两个模式共用商品素材与服务状态。
        </p>
      </div>

      <Tabs value={tab} onValueChange={switchTab}>
        <TabsList className="w-full justify-start sm:w-auto">
          <TabsTrigger value="marketing" className="min-w-28">
            营销成片
          </TabsTrigger>
          <TabsTrigger value="single" className="min-w-28">
            单镜头生成
          </TabsTrigger>
        </TabsList>
        <TabsContent value="marketing" className="mt-4">
          <MarketingVideosPage embedded />
        </TabsContent>
        <TabsContent value="single" className="mt-4">
          <VideosPage embedded />
        </TabsContent>
      </Tabs>
    </motion.div>
  )
}
