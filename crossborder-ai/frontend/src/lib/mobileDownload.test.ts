import { describe, expect, it } from 'vitest'

import {
  DEFAULT_MOBILE_APP_DOWNLOAD_URL,
  resolveMobileDownloadUrl,
} from './mobileDownload'

describe('mobile download configuration', () => {
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
