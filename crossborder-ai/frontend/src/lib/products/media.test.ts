import { describe, expect, it } from 'vitest'

import { normalizeProductMedia } from './media'

describe('normalizeProductMedia', () => {
  it('combines the gallery and main image without duplicates', () => {
    expect(
      normalizeProductMedia({
        main_image_url: 'https://cdn.example.com/a.jpg',
        image_urls: [
          'https://cdn.example.com/a.jpg',
          'https://cdn.example.com/b.jpg',
          '',
        ],
        video_url: 'https://cdn.example.com/main.mp4',
      }),
    ).toEqual({
      images: [
        'https://cdn.example.com/a.jpg',
        'https://cdn.example.com/b.jpg',
      ],
      videoUrl: 'https://cdn.example.com/main.mp4',
    })
  })

  it('keeps legacy products with only main_image_url working', () => {
    expect(
      normalizeProductMedia({
        main_image_url: 'https://cdn.example.com/legacy.jpg',
      }),
    ).toEqual({
      images: ['https://cdn.example.com/legacy.jpg'],
      videoUrl: null,
    })
  })
})
