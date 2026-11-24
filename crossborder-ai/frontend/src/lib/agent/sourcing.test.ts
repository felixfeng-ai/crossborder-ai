import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  buildFindSourcesPrompt,
  buildProfitFromSourcePrompt,
} from './sourcing'

describe('1688 sourcing prompts', () => {
  it('creates a source discovery prompt from an Amazon candidate', () => {
    const prompt = buildFindSourcesPrompt({
      name: 'Wireless Pet Water Fountain',
      asin: 'B000IMAGE1',
      image_url: 'https://img.example.com/pet.jpg',
    })

    expect(prompt).toContain('find_1688_sources')
    expect(prompt).toContain('Wireless Pet Water Fountain')
    expect(prompt).toContain('B000IMAGE1')
    expect(prompt).toContain('https://img.example.com/pet.jpg')
    expect(prompt).toContain('中文采购关键词')
    expect(prompt).toContain('相似货源')
  })

  it('creates a profit prompt from a selected 1688 supplier', () => {
    const prompt = buildProfitFromSourcePrompt({
      title: '跨境无线宠物饮水机',
      url: 'https://detail.1688.com/offer/628196518518.html',
      price: '18.50',
      moq: 2,
    })

    expect(prompt).toContain('analyze_product_decision')
    expect(prompt).toContain(
      'https://detail.1688.com/offer/628196518518.html',
    )
    expect(prompt).toContain('采购价')
    expect(prompt).toContain('不要自动下单')
  })

  it('keeps sourcing actions visible in production cards', () => {
    const reportCard = fs.readFileSync(
      path.resolve(process.cwd(), 'src/components/agent/ProductReportCard.tsx'),
      'utf8',
    )
    const sourceCard = fs.readFileSync(
      path.resolve(process.cwd(), 'src/components/agent/SourceSupplierCard.tsx'),
      'utf8',
    )

    expect(reportCard).toContain('1688 找货源')
    expect(reportCard).toContain('onFindSources')
    expect(sourceCard).toContain('用这个货源算利润')
    expect(sourceCard).toContain('onUseSource')
  })
})
