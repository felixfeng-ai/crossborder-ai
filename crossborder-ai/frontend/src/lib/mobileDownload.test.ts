import { describe, expect, it } from 'vitest'

import {
  DEFAULT_MOBILE_APP_DOWNLOAD_URL,
  MOBILE_APP_BUILD_LABEL,
  resolveMobileDownloadUrl,
} from './mobileDownload'

describe('mobile download configuration', () => {
  it('publishes the current build through the stable HTTPS download endpoint', () => {
    expect(DEFAULT_MOBILE_APP_DOWNLOAD_URL).toBe(
      'https://veyaship.com/downloads/veyaship-1.0.0-18.apk',
    )
    expect(MOBILE_APP_BUILD_LABEL).toBe('Android 内测版 · 1.0.0 (18)')
  })

  it('uses the configured HTTPS download URL', () => {
    expect(
      resolveMobileDownloadUrl(' https://cdn.veyaship.com/app/veyaship-v6.apk '),
    ).toBe('https://cdn.veyaship.com/app/veyaship-v6.apk')
  })

  it('rejects invalid or non-HTTPS URLs and falls back to the current build', () => {
    expect(resolveMobileDownloadUrl('http://veyaship.com/app.apk')).toBe(
      DEFAULT_MOBILE_APP_DOWNLOAD_URL,
    )
    expect(resolveMobileDownloadUrl('not-a-url')).toBe(
      DEFAULT_MOBILE_APP_DOWNLOAD_URL,
    )
  })
})
