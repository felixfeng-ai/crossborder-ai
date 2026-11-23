import { useEffect, useRef, useState } from 'react'
import {
  ArrowUp,
  AudioLines,
  Camera,
  CheckCircle2,
  CircleAlert,
  Link2,
  Loader2,
  MessageSquareText,
  ScanLine,
  X,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  buildAgentTurnPayload,
  canSubmitAgentDraft,
  type AgentComposerMode,
} from '@/features/agent-work/composer'
import {
  createOperationIdempotencyKey,
  useAgentTurnQuery,
  useSubmitAgentTurnMutation,
  useTranscribeAgentAudioMutation,
  useUploadAgentImageMutation,
} from '@/features/agent-work/queries'
import type { ImageAsset } from '@/features/agent-work/types'

const MODES: Array<{
  id: AgentComposerMode
  label: string
  icon: typeof MessageSquareText
}> = [
  { id: 'text', label: '文字', icon: MessageSquareText },
  { id: 'link', label: '商品链接', icon: Link2 },
  { id: 'order', label: '订单号', icon: ScanLine },
]

interface CrossSurfaceComposerProps {
  workspaceId: string
}

export function CrossSurfaceComposer({
  workspaceId,
}: CrossSurfaceComposerProps) {
  const navigate = useNavigate()
  const [mode, setMode] = useState<AgentComposerMode>('text')
  const [text, setText] = useState('')
  const [images, setImages] = useState<ImageAsset[]>([])
  const [audioAssetId, setAudioAssetId] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  const [recordedSeconds, setRecordedSeconds] = useState(0)
  const [error, setError] = useState('')
  const [turnId, setTurnId] = useState<string | null>(null)
  const imageInput = useRef<HTMLInputElement>(null)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const mediaStream = useRef<MediaStream | null>(null)
  const audioChunks = useRef<BlobPart[]>([])
  const recordStartedAt = useRef(0)
  const submitKey = useRef('')
  const mounted = useRef(true)

  const uploadImage = useUploadAgentImageMutation(workspaceId)
  const transcribeAudio = useTranscribeAgentAudioMutation(workspaceId)
  const submitTurn = useSubmitAgentTurnMutation(workspaceId)
  const turn = useAgentTurnQuery(workspaceId, turnId)
  const draft = {
    mode,
    text,
    imageAssetIds: images.map((image) => image.id),
    audioAssetId,
    recording,
  }
  const canSubmit =
    canSubmitAgentDraft(draft) &&
    !uploadImage.isPending &&
    !transcribeAudio.isPending &&
    !submitTurn.isPending

  useEffect(() => {
    if (!recording) return
    const timer = window.setInterval(() => {
      setRecordedSeconds(
        Math.floor((Date.now() - recordStartedAt.current) / 1000),
      )
    }, 250)
    return () => window.clearInterval(timer)
  }, [recording])

  useEffect(
    () => () => {
      mounted.current = false
      mediaRecorder.current?.stop()
      mediaStream.current?.getTracks().forEach((track) => track.stop())
    },
    [],
  )

  const pickImages = async (files: FileList | null) => {
    if (!files?.length) return
    setError('')
    try {
      for (const file of Array.from(files).slice(0, 4)) {
        if (!file.type.startsWith('image/')) continue
        const asset = await uploadImage.mutateAsync(file)
        setImages((current) =>
          current.length >= 4 ? current : [...current, asset],
        )
      }
    } catch {
      setError('图片没有上传成功，请检查文件格式和网络后重试')
    } finally {
      if (imageInput.current) imageInput.current.value = ''
    }
  }

  const startRecording = async () => {
    if (recording || transcribeAudio.isPending) return
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('当前浏览器不支持录音，请改用音频文件或文字输入')
      return
    }
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStream.current = stream
      const recorder = new MediaRecorder(stream)
      mediaRecorder.current = recorder
      audioChunks.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size) audioChunks.current.push(event.data)
      }
      recorder.onstop = () => {
        const durationMs = Math.max(500, Date.now() - recordStartedAt.current)
        if (!mounted.current) return
        const blob = new Blob(audioChunks.current, {
          type: recorder.mimeType || 'audio/webm',
        })
        const file = new File([blob], `voice-${Date.now()}.webm`, {
          type: blob.type || 'audio/webm',
        })
        stream.getTracks().forEach((track) => track.stop())
        mediaStream.current = null
        void transcribeAudio
          .mutateAsync({
            file,
            durationMs,
            idempotencyKey: createOperationIdempotencyKey(),
          })
          .then((result) => {
            setAudioAssetId(result.asset_id)
            setText((current) =>
              current.trim() ? `${current}\n${result.transcript}` : result.transcript,
            )
          })
          .catch(() => {
            setError('语音识别失败，可以重录或改用文字输入')
          })
      }
      recordStartedAt.current = Date.now()
      setRecordedSeconds(0)
      recorder.start()
      setRecording(true)
    } catch {
      setError('没有获得麦克风权限，可以改用音频文件或文字输入')
    }
  }

  const stopRecording = () => {
    if (!recording) return
    setRecording(false)
    mediaRecorder.current?.stop()
  }

  const submit = async () => {
    if (!canSubmit || submitTurn.isPending) return
    setError('')
    if (!submitKey.current) submitKey.current = createOperationIdempotencyKey()
    try {
      const response = await submitTurn.mutateAsync({
        payload: buildAgentTurnPayload(draft),
        idempotencyKey: submitKey.current,
      })
      submitKey.current = ''
      setTurnId(response.agent_turn_id)
      setText('')
      setImages([])
      setAudioAssetId(null)
      setMode('text')
    } catch {
      setError('Agent 没有接收这次工作，请刷新或检查网络后重试')
    }
  }

  return (
    <section
      className="border border-border bg-[var(--factory-panel)]"
      data-cross-surface-composer="true"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">交给 Agent</span>
          <Badge variant="outline" className="text-[11px]">
            Web + App 同一工作区
          </Badge>
        </div>
        <div className="flex gap-1">
          {MODES.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setMode(item.id)}
                className={`inline-flex h-8 items-center gap-1.5 border px-2.5 text-[11px] ${
                  mode === item.id
                    ? 'border-[var(--factory-accent)] bg-[color:color-mix(in_srgb,var(--factory-accent)_10%,transparent)] text-foreground'
                    : 'border-border text-muted-foreground hover:text-foreground'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="p-4">
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={3}
          placeholder={
            mode === 'link'
              ? '粘贴 1688、Shopify、Amazon 或 Temu 商品链接'
              : mode === 'order'
                ? '输入订单号、物流单号或买家问题'
                : '告诉 Agent 今天要处理什么'
          }
          className="min-h-24 w-full resize-y border border-border bg-background px-3 py-2.5 text-sm leading-6 outline-none focus:border-[var(--factory-accent)]"
        />

        {!!images.length && (
          <div className="mt-3 flex flex-wrap gap-2">
            {images.map((image) => (
              <span
                key={image.id}
                className="inline-flex items-center gap-1.5 border border-border bg-background px-2 py-1 text-[11px]"
              >
                <Camera className="h-3.5 w-3.5" />
                <span className="max-w-36 truncate">{image.name}</span>
                <button
                  type="button"
                  aria-label={`移除 ${image.name}`}
                  onClick={() =>
                    setImages((current) =>
                      current.filter((entry) => entry.id !== image.id),
                    )
                  }
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        {audioAssetId && (
          <div className="mt-3 flex items-center justify-between gap-3 border border-[color:rgba(157,187,173,0.3)] bg-[color:rgba(157,187,173,0.08)] px-3 py-2 text-xs text-[var(--factory-mint)]">
            <span className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              语音已转写，提交时会发送给同一 Agent turn
            </span>
            <button
              type="button"
              onClick={() => setAudioAssetId(null)}
              aria-label="移除语音"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {error && (
          <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-[var(--factory-coral)]">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </p>
        )}

        <input
          ref={imageInput}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="hidden"
          onChange={(event) => void pickImages(event.target.files)}
        />

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={uploadImage.isPending || images.length >= 4}
              onClick={() => imageInput.current?.click()}
            >
              {uploadImage.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Camera className="mr-2 h-4 w-4" />
              )}
              图片
            </Button>
            <Button
              type="button"
              size="sm"
              variant={recording ? 'destructive' : 'outline'}
              disabled={transcribeAudio.isPending}
              onClick={() =>
                recording ? stopRecording() : void startRecording()
              }
            >
              {transcribeAudio.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <AudioLines className="mr-2 h-4 w-4" />
              )}
              {transcribeAudio.isPending
                ? '正在转写'
                : recording
                  ? `结束录音 ${recordedSeconds}s`
                  : '语音'}
            </Button>
          </div>

          <Button
            onClick={() => void submit()}
            disabled={!canSubmit}
            className="min-w-28"
          >
            {submitTurn.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <ArrowUp className="mr-2 h-4 w-4" />
            )}
            交给 Agent
          </Button>
        </div>
      </div>

      {turnId && (
        <div className="border-t border-border px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium">
                {turn.data?.status === 'failed'
                  ? 'Agent 没有完成任务'
                  : turn.data?.status === 'succeeded'
                    ? 'Agent 已接收并完成一轮处理'
                    : 'Agent 正在处理'}
              </p>
              <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                {turn.data?.error ||
                  turn.data?.result_summary ||
                  '任务状态会与 App 同步。'}
              </p>
            </div>
            {!!turn.data?.created_work_item_ids.length && (
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  navigate(`/app/tasks/${turn.data?.created_work_item_ids[0]}`)
                }
              >
                查看任务
              </Button>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
