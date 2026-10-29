#!/usr/bin/env node
/**
 * style-gate —— 全站视觉值门禁（零依赖）
 *
 * <style> 块与 styles/*.css 里禁止清单外的裸字号/裸色值。
 * 新视觉值必须走 tokens.css 的 var()，存量未迁值记在 style-legacy.json。
 * 用法：
 *   node scripts/style-gate.mjs [文件...]       校验（默认全扫，传路径则只扫这些）；违例退出码 1
 *   node scripts/style-gate.mjs --write-ledger  按当前代码重扫并重写 style-legacy.json
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SRC = path.join(FE, 'src')
const LEDGER = path.join(FE, 'style-legacy.json')

// 在途工作（并行会话），合入后移除本行并重扫清单
const GATE_SKIP = new Set(['components/opportunity/OpportunityProcessBoard.vue'])
const CSS_DIR = path.join(SRC, 'styles')
const CSS_SKIP = new Set(['tokens.css']) // tokens.css 是值源本身

const PRIMITIVE_HEX = new Set(['#fff', '#ffffff', '#000', '#000000'])
const FONT_ALLOW_RE = /^(?:0|inherit|var\(--[a-z0-9-]+(?:\s*,[^)]*)?\)|clamp\([^\n]*\)|[0-9.]+(?:em|rem|%|vh|vw))$/i
const NAMED_COLORS_RE = /\b(aqua|black|blue|fuchsia|gray|green|lime|maroon|navy|olive|orange|purple|red|silver|teal|white|yellow)\b/gi
const COLOR_PROPS_RE = /^(color|background|background-color|background-image|border|border-top|border-right|border-bottom|border-left|border-color|border-top-color|border-right-color|border-bottom-color|border-left-color|outline|outline-color|box-shadow|text-shadow|fill|stroke|caret-color|column-rule-color|text-decoration-color)$/
const NAMED_ALLOW = new Set(['transparent', 'currentcolor', 'inherit'])

function collectProps(css) {
  const props = []
  const re = /(?:^|[;{\n])([ \t]*[-a-zA-Z]+[ \t]*:)/g
  let m
  while ((m = re.exec(css))) {
    props.push({ idx: m.index + m[0].length - m[1].length, name: m[1].trim().replace(/:$/, '').toLowerCase() })
  }
  return props
}

function propAt(props, i) {
  let p = ''
  for (const pr of props) {
    if (pr.idx <= i) p = pr.name
    else break
  }
  return p
}

function inFallback(css, i) {
  const open = css.lastIndexOf('var(', i)
  if (open === -1) return false
  const close = css.indexOf(')', open)
  return close !== -1 && close > i
}

function canonRgba(r, g, b, a) {
  return `${+r},${+g},${+b},${+a}`
}

// 扫一个样式块，产出违例列表（kind: font-size | hex | rgba | named-color）
function checkBlock(css, ledger, residue, rel, baseLine) {
  const errors = []
  const lineOf = (i) => baseLine + (css.slice(0, i).match(/\n/g) || []).length + 1
  const push = (kind, value, i) => {
    const v = kind === 'rgba' ? canonRgba(...value) : value
    if (residue) {
      const key = kind === 'font-size' ? 'fonts' : kind === 'named-color' ? 'named' : kind === 'rgba' ? 'rgbas' : 'hexes'
      const map = residue[key]
      const e = map.get(v) || { count: 0, files: new Set() }
      e.count++
      e.files.add(rel)
      map.set(v, e)
    } else {
      errors.push({ file: rel, line: lineOf(i), kind, value: v })
    }
  }

  const fontRe = /font-size(\s*:\s*)([^;}]+)/gi
  fontRe.lastIndex = 0
  let m
  while ((m = fontRe.exec(css))) {
    const val = m[2].trim()
    if (FONT_ALLOW_RE.test(val)) continue
    if (ledger.fonts.includes(val.toLowerCase())) continue
    push('font-size', val.toLowerCase(), m.index)
  }

  const hexRe = /#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b/g
  while ((m = hexRe.exec(css))) {
    if (inFallback(css, m.index)) continue
    const low = '#' + m[1].toLowerCase()
    if (PRIMITIVE_HEX.has(low)) continue
    if (ledger.hexes.includes(low)) continue
    push('hex', low, m.index)
  }

  const rgbaRe = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)/gi
  while ((m = rgbaRe.exec(css))) {
    if (inFallback(css, m.index)) continue
    const key = canonRgba(m[1], m[2], m[3], m[4])
    if (ledger.rgbas.includes(key)) continue
    push('rgba', [m[1], m[2], m[3], m[4]], m.index)
  }

  const declRe = /([-a-zA-Z]+)\s*:\s*([^;{}]+)/g
  while ((m = declRe.exec(css))) {
    if (!COLOR_PROPS_RE.test(m[1].toLowerCase())) continue
    const valNoVar = m[2].replace(/var\([^)]*\)/g, '')
    let nm
    NAMED_COLORS_RE.lastIndex = 0
    while ((nm = NAMED_COLORS_RE.exec(valNoVar))) {
      const w = nm[1].toLowerCase()
      if (NAMED_ALLOW.has(w)) continue
      if (ledger.named.includes(w)) continue
      push('named-color', w, m.index)
    }
  }
  return errors
}

function walkVue(dir, rel, acc) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const r = rel ? `${rel}/${e.name}` : e.name
    if (e.isDirectory()) walkVue(path.join(dir, e.name), r, acc)
    else if (e.name.endsWith('.vue')) acc.push({ abs: path.join(dir, e.name), rel: r })
  }
  return acc
}

function run(writeLedger, onlyPaths) {
  const ledger = writeLedger
    ? { fonts: [], hexes: [], rgbas: [], named: [] }
    : JSON.parse(fs.readFileSync(LEDGER, 'utf8'))
  const residue = writeLedger ? { fonts: new Map(), hexes: new Map(), rgbas: new Map(), named: new Map() } : null
  const errors = []
  const note = (k) => {
    if (residue) return
    errors.push(k)
  }

  const scanContent = (content, rel, isVue) => {
    if (isVue) {
      const re = /<style[^>]*>([\s\S]*?)<\/style>/g
      let m
      while ((m = re.exec(content))) {
        const baseLine = (content.slice(0, m.index).match(/\n/g) || []).length
        for (const e of checkBlock(m[1], ledger, residue, rel, baseLine)) note(e)
      }
    } else {
      for (const e of checkBlock(content, ledger, residue, rel, 0)) note(e)
    }
  }

  if (onlyPaths.length) {
    for (const p of onlyPaths) {
      const abs = path.resolve(p)
      scanContent(fs.readFileSync(abs, 'utf8'), path.basename(abs), abs.endsWith('.vue'))
    }
  } else {
    for (const { abs, rel } of walkVue(SRC, '', [])) {
      if (GATE_SKIP.has(rel)) continue
      scanContent(fs.readFileSync(abs, 'utf8'), rel, true)
    }
    for (const f of fs.readdirSync(CSS_DIR)) {
      if (!f.endsWith('.css') || CSS_SKIP.has(f)) continue
      scanContent(fs.readFileSync(path.join(CSS_DIR, f), 'utf8'), `styles/${f}`, false)
    }
  }

  if (writeLedger) {
    const ledgerOut = {
      _note: 'style-gate 遗留白名单：存量未迁值（改哪页迁哪页，随迁移收缩）。勿手工增补；重扫：node scripts/style-gate.mjs --write-ledger',
      fonts: [...residue.fonts.keys()].sort(),
      hexes: [...residue.hexes.keys()].sort(),
      rgbas: [...residue.rgbas.keys()].sort((a, b) => a.localeCompare(b)),
      named: [...residue.named.keys()].sort(),
    }
    fs.writeFileSync(LEDGER, JSON.stringify(ledgerOut, null, 2) + '\n')
    const n = (k) => ledgerOut[k].length
    console.log(`style-legacy.json 已重扫生成：fonts=${n('fonts')} hexes=${n('hexes')} rgbas=${n('rgbas')} named=${n('named')}`)
    return
  }

  if (errors.length) {
    const byFile = new Map()
    for (const e of errors) {
      if (!byFile.has(e.file)) byFile.set(e.file, [])
      byFile.get(e.file).push(e)
    }
    for (const [f, list] of byFile) {
      for (const e of list) console.log(`${f}:${e.line}  ${e.kind}  ${e.value}`)
    }
    console.error(`style-gate：${errors.length} 处违例（新增裸值必须走 tokens var()）`)
    process.exit(1)
  }
  console.log('style-gate：通过')
}

const argPaths = process.argv.slice(2).filter((a) => !a.startsWith('--'))
const writeLedger = process.argv.includes('--write-ledger')
run(writeLedger, argPaths)
