import type { Ref } from 'vue'
import * as fabric from 'fabric'
import { t } from '../../composables/i18n'
import { authenticatedJsonHeaders } from '../../api/authHeaders'
import { canonicalPresentationStyle } from '../../utils/presentationStyle'
import { resolveAlignedTextTop, resolveFontWeight, resolveTextInsets } from '../../utils/presentationTextLayout'
import { linePageEndpoints } from '../../utils/presentationLineGeometry'
import { CANVAS_W, CANVAS_H } from './presentationConstants'

export function createPresentationRenderer(context: { getCanvas: () => fabric.Canvas | null; pages: Ref<any[]>; props: { blueprint: any }; guideLines: fabric.Line[] }) {
  const { getCanvas, pages, props, guideLines } = context

function isTransparent(val: string | undefined): boolean {
  if (!val) return true
  const v = val.trim().toLowerCase()
  return v === 'transparent' || v === 'none' || v === 'inherit' || v === 'initial' || v === ''
}

interface GradientStop { offset: number; color: string }

function parseLinearGradient(val: string): { angle: number; stops: GradientStop[] } | null {
  const m = val.match(/linear-gradient\s*\((.+)\)\s*$/i)
  if (!m) return null
  const inner = m[1]
  // Split on top-level commas
  const parts: string[] = []
  let depth = 0, buf = ''
  for (const ch of inner) {
    if (ch === '(') depth++
    else if (ch === ')') depth--
    else if (ch === ',' && depth === 0) { parts.push(buf.trim()); buf = ''; continue }
    buf += ch
  }
  if (buf.trim()) parts.push(buf.trim())
  if (parts.length < 2) return null

  let angle = 180
  let colorParts = parts
  const first = parts[0].trim().toLowerCase()
  const angleMatch = first.match(/^(-?\d+(?:\.\d+)?)\s*deg$/)
  if (angleMatch) {
    angle = parseFloat(angleMatch[1])
    colorParts = parts.slice(1)
  } else if (first.startsWith('to ')) {
    const dirMap: Record<string, number> = {
      'to top': 0, 'to right': 90, 'to bottom': 180, 'to left': 270,
      'to top right': 45, 'to bottom right': 135, 'to bottom left': 225, 'to top left': 315,
    }
    angle = dirMap[first] ?? 180
    colorParts = parts.slice(1)
  }

  const stops: GradientStop[] = []
  for (let i = 0; i < colorParts.length; i++) {
    const p = colorParts[i].trim()
    const posMatch = p.match(/(\d+(?:\.\d+)?)\s*%\s*$/)
    let offset = i / Math.max(1, colorParts.length - 1)
    let colorStr = p
    if (posMatch) {
      offset = parseFloat(posMatch[1]) / 100
      colorStr = p.slice(0, posMatch.index).trim()
    }
    stops.push({ offset, color: colorStr })
  }
  return stops.length >= 2 ? { angle, stops } : null
}

function angleToCoordsPercent(angle: number): { x1: number; y1: number; x2: number; y2: number } {
  // Fabric gradient coords are 0–1 within the object
  const rad = ((angle - 90) * Math.PI) / 180
  const cos = Math.cos(rad), sin = Math.sin(rad)
  return {
    x1: 0.5 - cos * 0.5,
    y1: 0.5 - sin * 0.5,
    x2: 0.5 + cos * 0.5,
    y2: 0.5 + sin * 0.5,
  }
}

function makeFabricGradient(val: string, width: number, height: number): fabric.Gradient<'linear'> | string {
  if (isTransparent(val)) return 'transparent'
  const parsed = parseLinearGradient(val)
  if (!parsed) return val // plain color string
  const coords = angleToCoordsPercent(parsed.angle)
  return new fabric.Gradient({
    type: 'linear',
    gradientUnits: 'percentage',
    coords: { x1: coords.x1, y1: coords.y1, x2: coords.x2, y2: coords.y2 },
    colorStops: parsed.stops.map(s => ({ offset: s.offset, color: s.color })),
  })
}

function resolveBackground(val: string | undefined, width: number, height: number): string | fabric.Gradient<'linear'> {
  if (!val || isTransparent(val)) return 'transparent'
  return makeFabricGradient(val, width, height)
}

// ---------------------------------------------------------------------------
// Blueprint → Fabric
// ---------------------------------------------------------------------------
function loadPageToCanvas(pageIndex: number) {
  const fc = getCanvas()
  if (!fc) return
  guideLines.length = 0
  fc.clear()
  // Reset background — fc.clear() does NOT reset backgroundColor
  fc.backgroundColor = '#ffffff'
  const page = pages.value[pageIndex]
  if (!page) return

  // Page background (may be gradient)
  const pageBg = page.style?.background || page.style?.background_color || props.blueprint?.theme?.page_background || '#ffffff'
  const bgParsed = parseLinearGradient(pageBg)
  if (bgParsed) {
    // Fabric canvas.backgroundColor can't be a gradient — add a full-page rect instead
    const bgRect = new fabric.Rect({
      left: 0, top: 0, width: CANVAS_W, height: CANVAS_H,
      fill: makeFabricGradient(pageBg, CANVAS_W, CANVAS_H),
      selectable: false, evented: false,
    })
    fc.add(bgRect)
  } else {
    fc.backgroundColor = isTransparent(pageBg) ? '#ffffff' : pageBg
  }

  const blocks = [...(page.blocks || [])].sort((a: any, b: any) => (a.z_index || 0) - (b.z_index || 0))
  for (const block of blocks) {
    addBlockToCanvas(block, { x: 0, y: 0, w: 1, h: 1 })
  }
  fc.renderAll()
}

function resolveBlockGeometry(
  block: any,
  parentRect: { x: number; y: number; w: number; h: number },
) {
  const coordSpace = (block.coordinate_space || 'page').toLowerCase()
  let bx: number, by: number, bw: number, bh: number
  if (coordSpace === 'parent') {
    bx = parentRect.x + (block.x || 0) * parentRect.w
    by = parentRect.y + (block.y || 0) * parentRect.h
    bw = (block.w || 0) * parentRect.w
    bh = (block.h || 0) * parentRect.h
  } else {
    bx = block.x || 0; by = block.y || 0
    bw = block.w || 0; bh = block.h || 0
  }
  return {
    bx, by, bw, bh,
    left: bx * CANVAS_W,
    top: by * CANVAS_H,
    width: Math.max(1, bw * CANVAS_W),
    height: Math.max(1, bh * CANVAS_H),
  }
}

function resolveStroke(style: any): { stroke: string; strokeWidth: number } {
  const raw = style.border_color || style.border || ''
  if (!raw || isTransparent(raw)) return { stroke: 'transparent', strokeWidth: 0 }
  // Parse "Npx solid #color"
  const m = raw.match?.(/(\d+(?:\.\d+)?)\s*px\s+solid\s+(#[0-9a-fA-F]{3,8})/)
  if (m) return { stroke: m[2], strokeWidth: parseFloat(m[1]) }
  return { stroke: raw, strokeWidth: parseFloat(style.border_width) || 1 }
}

function addIconFallback(
  canvas: fabric.Canvas, blockId: string, blockType: string,
  left: number, top: number, width: number, height: number,
  iconName: string, color: string,
) {
  const label = new fabric.Text(iconName, {
    left: left + 2, top: top + height * 0.2,
    fontSize: Math.max(8, Math.min(14, Math.min(width, height) * 0.3)),
    fill: color, selectable: true,
  })
  ;(label as any)._blockId = blockId
  ;(label as any)._blockType = blockType
  canvas.add(label)
  canvas.renderAll()
}

function addChartPlaceholder(
  canvas: fabric.Canvas, blockId: string, blockType: string,
  left: number, top: number, width: number, height: number, title: string,
) {
  const rect = new fabric.Rect({
    left, top, width, height,
    fill: '#f8fafc', stroke: '#94a3b8', strokeWidth: 1,
    rx: 10, ry: 10, selectable: true,
  })
  ;(rect as any)._blockId = blockId
  ;(rect as any)._blockType = blockType
  canvas.add(rect)
  canvas.add(new fabric.Text(title, {
    left: left + 10, top: top + 10,
    fontSize: 14, fill: '#64748b',
    selectable: false, evented: false,
  }))
  canvas.renderAll()
}

function addImagePlaceholder(
  canvas: fabric.Canvas, block: any, blockType: string,
  left: number, top: number, width: number, height: number,
) {
  const promptText = block.image_prompt || t('ppt.image_placeholder')
  const rect = new fabric.Rect({
    left, top, width, height,
    fill: '#e8ecf0',
    stroke: '#b0b8c4',
    strokeWidth: 2,
    strokeDashArray: [6, 4],
    rx: 8, ry: 8,
    selectable: true,
  })
  ;(rect as any)._blockId = block.id
  ;(rect as any)._blockType = blockType
  canvas.add(rect)
  const label = new fabric.Text(promptText, {
    left: left + 10, top: top + height / 2 - 8,
    fontSize: 13,
    fill: '#8896a7',
    selectable: false,
    evented: false,
  })
  canvas.add(label)
  canvas.renderAll()
}

// Render a background/border container rect for any block that has visible styling.
// This mirrors HTML renderer which applies ALL style props on every block's <div>.
function renderBlockContainer(
  blockId: string, style: any,
  left: number, top: number, width: number, height: number,
): boolean {
  const fc = getCanvas()
  if (!fc) return false
  const bgVal = style.background || style.background_color || ''
  const hasBg = bgVal && !isTransparent(bgVal)

  // Check for any border (full border, or single-side like border_left)
  const borderColor = style.border_color || ''
  const borderLeft = style.border_left || ''
  const borderRight = style.border_right || ''
  const borderTop = style.border_top || ''
  const borderBottom = style.border_bottom || ''
  const hasBorder = (borderColor && !isTransparent(borderColor))
    || borderLeft || borderRight || borderTop || borderBottom
  const hasBoxShadow = style.box_shadow && style.box_shadow !== 'none'

  if (!hasBg && !hasBorder && !hasBoxShadow) return false

  const { stroke, strokeWidth } = resolveStroke(style)
  const opacity = style.opacity != null ? parseFloat(style.opacity) : 1.0

  // Parse box_shadow to Fabric Shadow
  let shadow: fabric.Shadow | undefined
  if (hasBoxShadow) {
    const sv = style.box_shadow as string
    // Preset names
    const presets: Record<string, string> = {
      soft: '0 8px 24px rgba(15,23,42,0.10)',
      subtle: '0 4px 14px rgba(15,23,42,0.08)',
      medium: '0 10px 28px rgba(15,23,42,0.14)',
      strong: '0 16px 40px rgba(15,23,42,0.18)',
    }
    const resolved = presets[sv.toLowerCase()] || sv
    // Parse "offsetX offsetY blur color"
    const sm = resolved.match(/(-?\d+)(?:px)?\s+(-?\d+)(?:px)?\s+(\d+)(?:px)?\s+(rgba?\([^)]+\)|#[0-9a-fA-F]{3,8})/)
    if (sm) {
      shadow = new fabric.Shadow({
        offsetX: parseInt(sm[1]),
        offsetY: parseInt(sm[2]),
        blur: parseInt(sm[3]),
        color: sm[4],
      })
    }
  }

  const rect = new fabric.Rect({
    left, top, width, height,
    fill: hasBg ? resolveBackground(bgVal, width, height) : '#ffffff',
    stroke, strokeWidth,
    rx: parseFloat(style.border_radius) || 0,
    ry: parseFloat(style.border_radius) || 0,
    opacity: isNaN(opacity) ? 1 : opacity,
    shadow: shadow || null,
    selectable: false, evented: false,
  })
  ;(rect as any)._blockId = blockId + '_container'
  ;(rect as any)._blockType = 'container'

  fc.add(rect)
  drawSideBorders(style, left, top, width, height)
  return true
}

// Draw single-side borders as colored rects with matching corner radius
function drawSideBorders(style: any, left: number, top: number, width: number, height: number) {
  const fc = getCanvas()
  if (!fc) return
  const radius = parseFloat(style.border_radius) || 0
  const borderDefs = [
    { key: 'border_left',   getRect: (bw: number) => ({ x: left, y: top, w: bw, h: height, rx: radius, ry: radius }) },
    { key: 'border_right',  getRect: (bw: number) => ({ x: left + width - bw, y: top, w: bw, h: height, rx: radius, ry: radius }) },
    { key: 'border_top',    getRect: (bw: number) => ({ x: left, y: top, w: width, h: bw, rx: radius, ry: radius }) },
    { key: 'border_bottom', getRect: (bw: number) => ({ x: left, y: top + height - bw, w: width, h: bw, rx: radius, ry: radius }) },
  ]
  for (const def of borderDefs) {
    const val = style[def.key]
    if (!val) continue
    const m = (val as string).match?.(/(\d+(?:\.\d+)?)\s*px\s+solid\s+(#[0-9a-fA-F]{3,8}|rgba?\([^)]+\))/)
    if (!m) continue
    const bw = parseFloat(m[1])
    const r = def.getRect(bw)
    const br = new fabric.Rect({
      left: r.x, top: r.y, width: r.w, height: r.h,
      fill: m[2],
      rx: r.rx, ry: r.ry,
      selectable: false, evented: false,
    })
    ;(br as any)._blockType = 'container'
    ;(br as any)._isGuide = true
    fc.add(br)
  }
}

function addBlockToCanvas(
  block: any,
  parentRect: { x: number; y: number; w: number; h: number },
) {
  const fc = getCanvas()
  if (!fc) return
  const type = (block.type || 'text_box').toLowerCase()
  const { bx, by, bw, bh, left, top, width, height } = resolveBlockGeometry(block, parentRect)
  const style = canonicalPresentationStyle(block.style, type)
  const bgVal = style.background || style.background_color || ''
  const { stroke, strokeWidth } = resolveStroke(style)
  const opacity = Number.isFinite(parseFloat(style.opacity)) ? parseFloat(style.opacity) : 1

  const addTextObject = (
    content: string,
    boxLeft: number,
    boxTop: number,
    boxWidth: number,
    boxHeight: number,
    textStyle: any,
    attachBlockIdentity = true,
  ) => {
    if (!fc || !content) return
    const insets = resolveTextInsets(textStyle.padding)
    const textWidth = Math.max(1, boxWidth - insets.left - insets.right)
    const fontSize = parseFloat(textStyle.font_size) || 18
    const lineHeight = parseFloat(textStyle.line_height) || 1.2
    const tb = new fabric.Textbox(content.replace(/\\n/g, '\n'), {
      left: boxLeft + insets.left,
      top: boxTop + insets.top,
      width: textWidth,
      fontSize,
      fontWeight: resolveFontWeight(textStyle.font_weight),
      fontStyle: textStyle.font_style === 'italic' ? 'italic' : 'normal',
      fill: textStyle.color || '#222222',
      textAlign: (textStyle.text_align || 'left') as any,
      fontFamily: textStyle.font_family || "'PingFang SC', 'Microsoft YaHei', sans-serif",
      lineHeight,
      splitByGrapheme: true,
      selectable: attachBlockIdentity,
      editable: attachBlockIdentity,
      opacity,
    })
    tb.set({
      top: resolveAlignedTextTop(
        boxTop,
        boxHeight,
        Number(tb.height || fontSize * lineHeight),
        insets,
        textStyle.vertical_align,
      ),
    })
    if (attachBlockIdentity) {
      ;(tb as any)._blockId = block.id
      ;(tb as any)._blockType = type
      ;(tb as any)._layoutBox = {
        left: boxLeft,
        top: boxTop,
        width: boxWidth,
        height: boxHeight,
        textLeft: Number(tb.left || 0),
        textTop: Number(tb.top || 0),
        textWidth: Number(tb.width || textWidth),
      }
    } else {
      ;(tb as any)._isGuide = true
      ;(tb as any)._blockType = 'container-label'
    }
    fc.add(tb)
  }

  if (type === 'rectangle' || type === 'group') {
    // Parse box-shadow for this shape
    let shapeShadow: fabric.Shadow | undefined
    const bsVal = style.box_shadow
    if (bsVal && bsVal !== 'none') {
      const presets: Record<string, string> = {
        soft: '0 8px 24px rgba(15,23,42,0.10)', subtle: '0 4px 14px rgba(15,23,42,0.08)',
        medium: '0 10px 28px rgba(15,23,42,0.14)', strong: '0 16px 40px rgba(15,23,42,0.18)',
      }
      const resolved = presets[(bsVal + '').toLowerCase()] || bsVal
      const sm = (resolved + '').match(/(-?\d+)(?:px)?\s+(-?\d+)(?:px)?\s+(\d+)(?:px)?\s+(rgba?\([^)]+\)|#[0-9a-fA-F]{3,8})/)
      if (sm) shapeShadow = new fabric.Shadow({ offsetX: +sm[1], offsetY: +sm[2], blur: +sm[3], color: sm[4] })
    }
    const rect = new fabric.Rect({
      left, top, width, height,
      fill: resolveBackground(bgVal, width, height),
      stroke, strokeWidth,
      rx: parseFloat(style.border_radius) || 0,
      ry: parseFloat(style.border_radius) || 0,
      shadow: shapeShadow || null,
      opacity,
      selectable: true,
    })
    ;(rect as any)._blockId = block.id
    ;(rect as any)._blockType = type
    fc.add(rect)
    drawSideBorders(style, left, top, width, height)

    const childRect = { x: bx, y: by, w: bw, h: bh }
    for (const child of (block.children || [])) {
      addBlockToCanvas(child, childRect)
    }

  } else if (type === 'circle') {
    const r = Math.min(width, height) / 2
    const circle = new fabric.Circle({
      left, top, radius: r,
      fill: resolveBackground(bgVal, r * 2, r * 2),
      stroke, strokeWidth,
      opacity,
      selectable: true,
    })
    ;(circle as any)._blockId = block.id
    ;(circle as any)._blockType = type
    fc.add(circle)
    addTextObject(block.content || '', left, top, r * 2, r * 2, {
      ...style,
      text_align: style.text_align || 'center',
      vertical_align: style.vertical_align || 'middle',
    }, false)

  } else if (type === 'text_box') {
    // Render container (background, border, shadow) — same as HTML renderer
    renderBlockContainer(block.id, style, left, top, width, height)

    addTextObject(block.content || '', left, top, width, height, style)

  } else if (type === 'line') {
    const coordSpace = (block.coordinate_space || 'page').toLowerCase()
    const endpointX = block.x2 ?? block.x ?? 0
    const endpointY = block.y2 ?? block.y ?? 0
    const x1 = bx * CANVAS_W
    const y1 = by * CANVAS_H
    const x2 = (coordSpace === 'parent' ? parentRect.x + endpointX * parentRect.w : endpointX) * CANVAS_W
    const y2 = (coordSpace === 'parent' ? parentRect.y + endpointY * parentRect.h : endpointY) * CANVAS_H
    const lineColor = style.color || style.background || '#000000'
    const lineWeight = parseFloat(style.line_weight) || 2

    const line = new fabric.Line([x1, y1, x2, y2], {
      stroke: isTransparent(lineColor) ? '#000' : lineColor,
      strokeWidth: lineWeight,
      opacity,
      selectable: true,
    })
    ;(line as any)._blockId = block.id
    ;(line as any)._blockType = type
    fc.add(line)

  } else if (type === 'icon') {
    renderBlockContainer(block.id, style, left, top, width, height)

    let iconName = (block.icon || block.content || 'sparkles').trim()
    iconName = iconName.replace(/^(tabler:|icon[-:])/i, '').trim() || 'sparkles'
    const iconColor = style.color || props.blueprint?.theme?.accent_color || '#3b82f6'
    const colorHex = iconColor.replace('#', '')
    const canvas = fc
    // Match HTML renderer: icon SVG sits inside block's (left,top,width,height)
    // with width="100%" height="100%" and preserveAspectRatio="xMidYMid meet".
    // We create an offscreen canvas at exactly (width×height) pixels (×2 for DPI),
    // draw the SVG centered (uniform scale, like preserveAspectRatio meet),
    // and place the FabricImage at exactly (left, top) with scale to match.
    const ocW = Math.max(Math.round(width), 8) * 2
    const ocH = Math.max(Math.round(height), 8) * 2
    const svgUrl = `/askai-api/api/icons/${encodeURIComponent(iconName)}.svg?color=${colorHex}`
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      if (!canvas) return
      const oc = document.createElement('canvas')
      oc.width = ocW
      oc.height = ocH
      const ctx = oc.getContext('2d')!
      ctx.clearRect(0, 0, ocW, ocH)
      // Manually implement preserveAspectRatio="xMidYMid meet":
      // uniform scale square icon into ocW×ocH, centered
      const iconSize = Math.min(ocW, ocH)
      const dx = (ocW - iconSize) / 2
      const dy = (ocH - iconSize) / 2
      ctx.drawImage(img, dx, dy, iconSize, iconSize)
      // Place at exact block position, scale back to block pixel size
      const fabricImg = new fabric.FabricImage(oc, {
        left,
        top,
        scaleX: width / ocW,
        scaleY: height / ocH,
        selectable: true,
        objectCaching: false,
      })
      ;(fabricImg as any)._blockId = block.id
      ;(fabricImg as any)._blockType = type
      canvas.add(fabricImg)
      canvas.renderAll()
    }
    img.onerror = () => addIconFallback(canvas!, block.id, type, left, top, width, height, iconName, iconColor)
    img.src = svgUrl

  } else if (type === 'chart') {
    renderBlockContainer(block.id, style, left, top, width, height)
    const chartType = block.chart_type || ''
    const chartData = block.chart_data || {}
    const chartTitle = chartData.title || block.content || t('ppt.chart_placeholder')
    const canvas = fc
    const pxW = Math.round(Math.max(width, 160))
    const pxH = Math.round(Math.max(height, 120))

    // Build theme from blueprint
    const theme = props.blueprint?.theme || {}
    const chartTheme = {
      accent_color: theme.accent_color || '#2563eb',
      title_color: theme.title_color || '#0f172a',
      body_color: theme.body_color || '#334155',
      muted_color: theme.muted_color || '#64748b',
      surface_background: theme.surface_background || '#ffffff',
      page_background: theme.page_background || '#ffffff',
    }

    if (chartType) {
      fetch('/askai-api/api/documents/render-chart-svg', {
        method: 'POST',
        headers: authenticatedJsonHeaders(),
        body: JSON.stringify({
          chart_type: chartType,
          chart_data: chartData,
          width: pxW,
          height: pxH,
          theme: chartTheme,
        }),
      })
        .then(r => r.ok ? r.text() : Promise.reject('chart render failed'))
        .then(svgStr => {
          if (!canvas) return
          const dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgStr)
          return fabric.FabricImage.fromURL(dataUrl).then((img: any) => {
            if (!canvas) return
            const imgW = img.width || pxW
            const imgH = img.height || pxH
            img.set({
              left, top,
              scaleX: width / imgW,
              scaleY: height / imgH,
              selectable: true,
            })
            ;(img as any)._blockId = block.id
            ;(img as any)._blockType = type
            canvas.add(img)
            canvas.renderAll()
          })
        })
        .catch(() => {
          // Fallback placeholder
          addChartPlaceholder(canvas!, block.id, type, left, top, width, height, chartTitle)
        })
    } else {
      addChartPlaceholder(canvas!, block.id, type, left, top, width, height, chartTitle)
    }

  } else if (type === 'image') {
    renderBlockContainer(block.id, style, left, top, width, height)
    const src = String(block.content || '').trim()
    const isRealUrl = src.startsWith('http://') || src.startsWith('https://') || src.startsWith('/')
    if (isRealUrl) {
      // Insert a synchronous placeholder NOW so the image occupies its correct
      // z-order slot. When the real image finishes loading, we swap it into the
      // same array index — otherwise async onload would push it to the top of
      // the canvas stack and cover later-added text/scrim blocks above it.
      const canvasRef = fc!
      const slot = new fabric.Rect({
        left, top, width, height,
        fill: '#e8ecf0',
        stroke: '#b0b8c4',
        strokeWidth: 1,
        strokeDashArray: [4, 4],
        rx: 8, ry: 8,
        selectable: false,
        evented: false,
      })
      ;(slot as any)._blockId = block.id + '_image_slot'
      ;(slot as any)._blockType = 'container'
      ;(slot as any)._isGuide = true
      canvasRef.add(slot)

      const nativeImg = new Image()
      const radiusPx = (() => {
        const r = parseFloat(String(style.border_radius ?? style.borderRadius ?? '')) || 12
        return Math.max(0, Math.min(r, Math.min(width, height) / 2))
      })()
      nativeImg.onload = () => {
        if (!canvasRef) return
        const iw = nativeImg.naturalWidth || nativeImg.width || 1
        const ih = nativeImg.naturalHeight || nativeImg.height || 1
        // Device-pixel-ratio upscale so rounded edges don't look chunky.
        const dpr = 2
        const ocW = Math.max(Math.round(width), 8) * dpr
        const ocH = Math.max(Math.round(height), 8) * dpr
        const oc = document.createElement('canvas')
        oc.width = ocW
        oc.height = ocH
        const ctx = oc.getContext('2d')!
        // Rounded rect clip
        const r = radiusPx * dpr
        ctx.beginPath()
        ctx.moveTo(r, 0)
        ctx.lineTo(ocW - r, 0)
        ctx.quadraticCurveTo(ocW, 0, ocW, r)
        ctx.lineTo(ocW, ocH - r)
        ctx.quadraticCurveTo(ocW, ocH, ocW - r, ocH)
        ctx.lineTo(r, ocH)
        ctx.quadraticCurveTo(0, ocH, 0, ocH - r)
        ctx.lineTo(0, r)
        ctx.quadraticCurveTo(0, 0, r, 0)
        ctx.closePath()
        ctx.clip()
        // object-fit: cover — scale so short side fills, crop overflow
        const scale = Math.max(ocW / iw, ocH / ih)
        const drawW = iw * scale
        const drawH = ih * scale
        const dx = (ocW - drawW) / 2
        const dy = (ocH - drawH) / 2
        ctx.drawImage(nativeImg, dx, dy, drawW, drawH)
        const fabricImg = new fabric.FabricImage(oc, {
          left, top,
          scaleX: width / ocW,
          scaleY: height / ocH,
          selectable: true,
          objectCaching: false,
        })
        ;(fabricImg as any)._blockId = block.id
        ;(fabricImg as any)._blockType = type
        // Slot the image at the z-position the placeholder reserved for it.
        const objs = canvasRef.getObjects()
        const slotIndex = objs.indexOf(slot as any)
        canvasRef.remove(slot)
        canvasRef.add(fabricImg)
        if (slotIndex >= 0 && typeof (canvasRef as any).moveObjectTo === 'function') {
          ;(canvasRef as any).moveObjectTo(fabricImg, slotIndex)
        } else if (slotIndex >= 0 && typeof (fabricImg as any).moveTo === 'function') {
          ;(fabricImg as any).moveTo(slotIndex)
        }
        canvasRef.renderAll()
      }
      nativeImg.onerror = () => {
        // Swap the subtle slot placeholder for the labelled-prompt placeholder.
        if (canvasRef) canvasRef.remove(slot)
        addImagePlaceholder(fc!, block, type, left, top, width, height)
      }
      nativeImg.src = src
    } else {
      addImagePlaceholder(fc!, block, type, left, top, width, height)
    }
  }
}

// ---------------------------------------------------------------------------
  return { isTransparent, parseLinearGradient, angleToCoordsPercent, makeFabricGradient, resolveBackground, loadPageToCanvas, resolveBlockGeometry, resolveStroke, addIconFallback, addChartPlaceholder, addImagePlaceholder, renderBlockContainer, drawSideBorders, addBlockToCanvas }
}
