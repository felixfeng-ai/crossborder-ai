export interface ProductMediaSource {
  main_image_url?: string | null
  image_urls?: string[] | null
  video_url?: string | null
}

export interface ProductMedia {
  images: string[]
  videoUrl: string | null
}

/** 兼容新旧商品接口，统一整理主图、图集和视频地址。 */
export function normalizeProductMedia(product: ProductMediaSource): ProductMedia {
  const candidates = [
    ...(Array.isArray(product.image_urls) ? product.image_urls : []),
    product.main_image_url,
  ]
  const images = Array.from(
    new Set(
      candidates
        .map((url) => String(url || '').trim())
        .filter(Boolean),
    ),
  )
  const videoUrl = String(product.video_url || '').trim() || null
  return { images, videoUrl }
}
