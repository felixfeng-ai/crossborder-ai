import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'

const DIST_DIR = path.resolve('dist')
const MANIFEST_PATH = path.join(DIST_DIR, '.vite', 'manifest.json')
const MAX_INITIAL_GZIP_BYTES = 250 * 1024
const MAX_SINGLE_GZIP_BYTES = 120 * 1024

if (!fs.existsSync(MANIFEST_PATH)) {
  throw new Error('缺少 dist/.vite/manifest.json，请先执行 npm run build')
}

const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'))
const keys = Object.keys(manifest)
const entryKey =
  keys.find((key) => manifest[key].isEntry)
const landingKey = keys.find((key) =>
  key.endsWith('src/pages/landing/LandingPage.tsx'),
)

if (!entryKey || !landingKey) {
  throw new Error(
    `无法定位入口或首页 chunk：entry=${entryKey || 'missing'}, landing=${
      landingKey || 'missing'
    }`,
  )
}

const selected = new Set()

function collectStaticImports(key) {
  if (selected.has(key)) return
  selected.add(key)
  for (const imported of manifest[key]?.imports || []) {
    collectStaticImports(imported)
  }
}

collectStaticImports(entryKey)
collectStaticImports(landingKey)

const files = new Set()
for (const key of selected) {
  const item = manifest[key]
  if (item.file) files.add(item.file)
  for (const css of item.css || []) files.add(css)
}

const fontFiles = [
  'fonts/inter-latin-variable.woff2',
  'fonts/jetbrains-mono-latin.woff2',
].filter((file) => fs.existsSync(path.join(DIST_DIR, file)))

let initialGzipBytes = 0
let largestGzipBytes = 0
let largestFile = ''
const rows = []

for (const file of files) {
  const filePath = path.join(DIST_DIR, file)
  if (!fs.existsSync(filePath)) continue
  const raw = fs.readFileSync(filePath)
  const gzip = zlib.gzipSync(raw, { level: 9 }).length
  initialGzipBytes += gzip
  rows.push({ file, raw: raw.length, gzip })
  if (gzip > largestGzipBytes) {
    largestGzipBytes = gzip
    largestFile = file
  }
}

for (const file of fontFiles) {
  const raw = fs.readFileSync(path.join(DIST_DIR, file))
  initialGzipBytes += raw.length
  rows.push({ file, raw: raw.length, gzip: raw.length })
}

rows.sort((a, b) => b.gzip - a.gzip)
console.log('Initial landing JavaScript/CSS/font budget:')
for (const row of rows.slice(0, 12)) {
  console.log(
    `  ${String(Math.round(row.gzip / 1024)).padStart(4)} KB gzip  ${row.file}`,
  )
}
console.log(
  `  ${String(Math.round(initialGzipBytes / 1024)).padStart(4)} KB gzip  TOTAL`,
)

if (initialGzipBytes > MAX_INITIAL_GZIP_BYTES) {
  throw new Error(
    `首屏资源 ${initialGzipBytes} bytes 超过预算 ${MAX_INITIAL_GZIP_BYTES} bytes`,
  )
}
if (largestGzipBytes > MAX_SINGLE_GZIP_BYTES) {
  throw new Error(
    `单文件 ${largestFile} 为 ${largestGzipBytes} bytes，超过预算 ${MAX_SINGLE_GZIP_BYTES} bytes`,
  )
}
