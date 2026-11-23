import * as Dialog from '@radix-ui/react-dialog'
import { CheckCircle2, Download, Smartphone, X } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'

import { BrandMark } from '@/components/brand/BrandMark'
import { Button } from '@/components/ui/button'
import {
  MOBILE_APP_BUILD_LABEL,
  MOBILE_APP_DOWNLOAD_URL,
} from '@/lib/mobileDownload'

const APP_POINTS = [
  '离开电脑也能处理订单、客服和店铺任务',
  '语音或拍照发指令，Agent 随时接住工作',
  '与 Web 工作台使用同一账号和店铺权限',
]

interface DownloadAppDialogProps {
  triggerLabel?: string
  triggerClassName?: string
  triggerVariant?: 'default' | 'outline' | 'ghost'
}

export function DownloadAppDialog({
  triggerLabel,
  triggerClassName,
  triggerVariant = 'outline',
}: DownloadAppDialogProps) {
  const resolvedLabel = triggerLabel ?? '下载 App'

  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <Button
          type="button"
          variant={triggerVariant}
          size="sm"
          className={triggerClassName ?? 'gap-1.5 px-2.5 text-foreground'}
          aria-label={resolvedLabel}
          title={resolvedLabel}
        >
          <Smartphone className="h-3.5 w-3.5" aria-hidden="true" />
          <span className={triggerLabel ? undefined : 'hidden xl:inline'}>
            {resolvedLabel}
          </span>
        </Button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[80] bg-black/70 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[81] max-h-[calc(100dvh-32px)] w-[calc(100%-32px)] max-w-[620px] -translate-x-1/2 -translate-y-1/2 overflow-y-auto border border-[var(--factory-line-strong)] bg-[var(--factory-panel)] p-0 shadow-2xl outline-none">
          <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full">
                <BrandMark className="h-10 w-10 text-foreground" />
              </div>
              <div className="min-w-0">
                <Dialog.Title className="text-base font-semibold leading-6">
                  把 Veya 放进手机
                </Dialog.Title>
                <Dialog.Description className="mt-0.5 text-xs leading-5 text-muted-foreground">
                  一台手机，一个 Agent，随时处理一天的跨境工作。
                </Dialog.Description>
              </div>
            </div>
            <Dialog.Close asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="-mr-1 shrink-0"
                aria-label="关闭下载 App"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </Dialog.Close>
          </div>

          <div className="grid gap-6 p-5 sm:grid-cols-[212px_minmax(0,1fr)] sm:p-6">
            <div className="mx-auto w-fit border border-[var(--factory-line)] bg-white p-3 shadow-sm">
              <QRCodeSVG
                value={MOBILE_APP_DOWNLOAD_URL}
                size={184}
                level="M"
                marginSize={1}
                bgColor="#FFFFFF"
                fgColor="#0B0E12"
                title="扫描下载 VeyaShip Android App"
              />
            </div>

            <div className="min-w-0">
              <p className="inline-flex items-center gap-1.5 border border-[var(--factory-line)] bg-secondary px-2 py-1 text-[11px] font-medium leading-4 text-muted-foreground">
                <span className="status-dot" />
                {MOBILE_APP_BUILD_LABEL}
              </p>
              <h3 className="mt-3 text-lg font-semibold leading-7">扫码安装 Android 版</h3>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                用 Android 手机扫码；当前设备已经打开 Web 时，也可以直接下载安装包。
              </p>

              <ul className="mt-4 space-y-2.5">
                {APP_POINTS.map((point) => (
                  <li key={point} className="flex gap-2 text-xs leading-5 text-foreground">
                    <CheckCircle2
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--factory-success)]"
                      aria-hidden="true"
                    />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>

              <Button asChild className="mt-5 h-10 w-full gap-2">
                <a
                  href={MOBILE_APP_DOWNLOAD_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Download className="h-4 w-4" aria-hidden="true" />
                  直接下载 APK
                </a>
              </Button>

              <p className="mt-3 text-[11px] leading-5 text-muted-foreground">
                Android 首次安装内测包时，需要在系统中允许当前浏览器安装应用。
                iOS 版本仍在准备中。
              </p>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
