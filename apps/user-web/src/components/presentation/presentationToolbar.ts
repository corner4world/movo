import { watch, type Ref } from 'vue'
import * as fabric from 'fabric'

interface PresentationToolbarContext {
  getCanvas: () => fabric.Canvas | null
  angleToCoordsPercent: (angle: number) => { x1: number; y1: number; x2: number; y2: number }
  selectedObj: Ref<any>
  selectedIsText: Ref<boolean>
  selectedIsShape: Ref<boolean>
  toolFontSize: Ref<number>
  toolColor: Ref<string>
  toolBold: Ref<boolean>
  toolAlign: Ref<string>
  toolFillMode: Ref<'solid' | 'gradient'>
  toolFillColor: Ref<string>
  toolGradientFrom: Ref<string>
  toolGradientTo: Ref<string>
  toolGradientAngle: Ref<number>
  toolStrokeColor: Ref<string>
  toolOpacity: Ref<number>
  toolCornerRadius: Ref<number>
}

export function createPresentationToolbar(context: PresentationToolbarContext) {
  const { getCanvas, angleToCoordsPercent, selectedObj, selectedIsText, selectedIsShape, toolFontSize, toolColor, toolBold, toolAlign, toolFillMode, toolFillColor, toolGradientFrom, toolGradientTo, toolGradientAngle, toolStrokeColor, toolOpacity, toolCornerRadius } = context

function syncToolbarFromSelection() {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  selectedObj.value = obj || null
  selectedIsText.value = obj instanceof fabric.Textbox
  selectedIsShape.value = !!(obj && !selectedIsText.value && !(obj as any)._isGuide)

  if (obj instanceof fabric.Textbox) {
    toolFontSize.value = obj.fontSize || 18
    toolColor.value = (obj.fill as string) || '#222222'
    toolBold.value = obj.fontWeight === 'bold'
    toolAlign.value = obj.textAlign || 'left'
  }
  if (selectedIsShape.value && obj) {
    const fill = (obj as any).fill
    if (fill && typeof fill === 'object' && fill.type === 'linear') {
      // It's a gradient
      toolFillMode.value = 'gradient'
      const stops = fill.colorStops || []
      toolGradientFrom.value = stops[0]?.color || '#3b82f6'
      toolGradientTo.value = stops[stops.length - 1]?.color || '#8b5cf6'
      // Rough angle extraction from coords
      const coords = fill.coords || {}
      const dx = (coords.x2 ?? 1) - (coords.x1 ?? 0)
      const dy = (coords.y2 ?? 0) - (coords.y1 ?? 0)
      toolGradientAngle.value = Math.round((Math.atan2(dy, dx) * 180 / Math.PI + 90 + 360) % 360)
    } else {
      toolFillMode.value = 'solid'
      toolFillColor.value = (typeof fill === 'string' && fill !== 'transparent') ? fill : '#ffffff'
    }
    const stroke = (obj as any).stroke
    toolStrokeColor.value = (typeof stroke === 'string' && stroke !== 'transparent') ? stroke : '#000000'
    toolOpacity.value = Math.round((obj.opacity ?? 1) * 100)
    toolCornerRadius.value = (obj as any).rx || 0
  }
}

function onSelectionCreated() { syncToolbarFromSelection() }

function onSelectionCleared() {
  selectedObj.value = null
  selectedIsText.value = false
  selectedIsShape.value = false
}

function applyFontSize(size: number) {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (obj instanceof fabric.Textbox) {
    obj.set('fontSize', size)
    fc?.renderAll()
  }
}

function applyColor(color: string) {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (obj instanceof fabric.Textbox) {
    obj.set('fill', color)
    fc?.renderAll()
  }
}

function applyBold(bold: boolean) {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (obj instanceof fabric.Textbox) {
    obj.set('fontWeight', bold ? 'bold' : 'normal')
    fc?.renderAll()
  }
}

function applyAlign(align: string) {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (obj instanceof fabric.Textbox) {
    obj.set('textAlign', align)
    fc?.renderAll()
  }
}

watch(toolFontSize, applyFontSize)
watch(toolColor, applyColor)
watch(toolBold, applyBold)
watch(toolAlign, applyAlign)

function applyFillColor(color: string) {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (obj && !(obj instanceof fabric.Textbox) && toolFillMode.value === 'solid') {
    obj.set('fill', color)
    fc?.renderAll()
  }
}

function applyGradientFill() {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (!obj || !fc || obj instanceof fabric.Textbox) return
  const w = (obj.width || 1) * (obj.scaleX || 1)
  const h = (obj.height || 1) * (obj.scaleY || 1)
  const coords = angleToCoordsPercent(toolGradientAngle.value)
  const gradient = new fabric.Gradient({
    type: 'linear',
    gradientUnits: 'percentage',
    coords: { x1: coords.x1, y1: coords.y1, x2: coords.x2, y2: coords.y2 },
    colorStops: [
      { offset: 0, color: toolGradientFrom.value },
      { offset: 1, color: toolGradientTo.value },
    ],
  })
  obj.set('fill', gradient)
  fc.renderAll()
}
function applyStrokeColor(color: string) {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (obj && !(obj instanceof fabric.Textbox)) {
    obj.set('stroke', color)
    if (!obj.strokeWidth) obj.set('strokeWidth', 1)
    fc?.renderAll()
  }
}
function applyOpacity(val: number) {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (obj) {
    obj.set('opacity', Math.max(0, Math.min(100, val)) / 100)
    fc?.renderAll()
  }
}
function applyCornerRadius(val: number) {
  const fc = getCanvas()
  const obj = fc?.getActiveObject()
  if (obj && 'rx' in obj) {
    (obj as any).set('rx', val);
    (obj as any).set('ry', val)
    fc?.renderAll()
  }
}

function startAngleDrag(e: MouseEvent) {
  e.preventDefault()
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2

  function calcAngle(ex: number, ey: number) {
    const deg = Math.round(Math.atan2(ex - cx, -(ey - cy)) * 180 / Math.PI + 360) % 360
    // Snap to 45-degree increments when close
    const snap45 = Math.round(deg / 45) * 45
    toolGradientAngle.value = Math.abs(deg - snap45) < 8 ? snap45 % 360 : deg
  }

  function onMove(ev: MouseEvent) { calcAngle(ev.clientX, ev.clientY) }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  calcAngle(e.clientX, e.clientY)
}

watch(toolFillColor, applyFillColor)
watch(toolStrokeColor, applyStrokeColor)
watch(toolOpacity, applyOpacity)
watch(toolCornerRadius, applyCornerRadius)
watch(toolFillMode, (mode) => {
  if (mode === 'gradient') applyGradientFill()
  else applyFillColor(toolFillColor.value)
})
watch(toolGradientFrom, () => { if (toolFillMode.value === 'gradient') applyGradientFill() })
watch(toolGradientTo, () => { if (toolFillMode.value === 'gradient') applyGradientFill() })
watch(toolGradientAngle, () => { if (toolFillMode.value === 'gradient') applyGradientFill() })

// ---------------------------------------------------------------------------
  return { syncToolbarFromSelection, onSelectionCreated, onSelectionCleared, startAngleDrag }
}
