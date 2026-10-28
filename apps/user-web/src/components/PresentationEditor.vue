<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick, computed } from 'vue'
import * as fabric from 'fabric'
import { renderPresentationPptx, saveBlueprint } from '../api/documents'
import { t, useLocale } from '../composables/i18n'
import { authenticatedJsonHeaders } from '../api/authHeaders'
import { canonicalPresentationStyle } from '../utils/presentationStyle'
import { resolveAlignedTextTop, resolveFontWeight, resolveTextInsets } from '../utils/presentationTextLayout'
import { linePageEndpoints } from '../utils/presentationLineGeometry'
import { CANVAS_W, CANVAS_H } from './presentation/presentationConstants'
import { createPresentationRenderer } from './presentation/presentationRenderer'
import { createPresentationBlueprintAdapter } from './presentation/presentationBlueprintAdapter'
import { createPresentationGuides } from './presentation/presentationGuides'
import { createPresentationToolbar } from './presentation/presentationToolbar'

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------
const props = defineProps<{
  blueprint: any
  userId: string
  blueprintObjectPath: string
}>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'exported', result: any): void
  (e: 'saved', blueprint: any): void
}>()

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const canvasEl = ref<HTMLCanvasElement | null>(null)
const canvasWrapperEl = ref<HTMLDivElement | null>(null)
const displayScale = ref(0.65)
let resizeOb: ResizeObserver | null = null
let fc: fabric.Canvas | null = null

const currentPageIndex = ref(0)
const pages = ref<any[]>([])
const exporting = ref(false)
const saving = ref(false)

// Toolbar state
const selectedObj = ref<fabric.FabricObject | null>(null)
const selectedIsText = ref(false)
const selectedIsShape = ref(false)
// Text tools
const toolFontSize = ref(18)
const toolColor = ref('#222222')
const toolBold = ref(false)
const toolAlign = ref('left')
// Shape tools
const toolFillMode = ref<'solid' | 'gradient'>('solid')
const toolFillColor = ref('#ffffff')
const toolGradientFrom = ref('#3b82f6')
const toolGradientTo = ref('#8b5cf6')
const toolGradientAngle = ref(135)
const toolStrokeColor = ref('#000000')
const toolOpacity = ref(100)
const toolCornerRadius = ref(0)
const { locale } = useLocale()

const totalPages = computed(() => pages.value.length)

// ---------------------------------------------------------------------------
// Gradient & color helpers
// ---------------------------------------------------------------------------
const guideLines: fabric.Line[] = []
const { isTransparent, parseLinearGradient, angleToCoordsPercent, makeFabricGradient, resolveBackground, loadPageToCanvas, resolveBlockGeometry, resolveStroke, addIconFallback, addChartPlaceholder, addImagePlaceholder, renderBlockContainer, drawSideBorders, addBlockToCanvas } = createPresentationRenderer({ getCanvas: () => fc, pages, props, guideLines })

// Fabric → Blueprint (save back)
// ---------------------------------------------------------------------------

// Working copy of the blueprint that accumulates edits across page switches
const workingBlueprint = ref<any>(null)

const { getWorkingBlueprint, canvasToBlueprint, findBlockById } = createPresentationBlueprintAdapter({ getCanvas: () => fc, workingBlueprint, props, currentPageIndex, resolveBlockGeometry })

// Actions
// ---------------------------------------------------------------------------
function goToPage(index: number) {
  if (index < 0 || index >= pages.value.length) return
  // Save current page changes before switching
  saveCurrentPageToBlueprint()
  currentPageIndex.value = index
  loadPageToCanvas(index)
}

function saveCurrentPageToBlueprint() {
  if (!fc) return
  canvasToBlueprint() // updates workingBlueprint
  pages.value = getWorkingBlueprint().pages || []
}

const saveMessage = ref('')

async function doSave(): Promise<any> {
  const bp = canvasToBlueprint()
  const blueprintPath = props.blueprintObjectPath
  if (!blueprintPath) throw new Error('Blueprint path not found')

  await saveBlueprint({
    user_id: props.userId || 'anonymous',
    blueprint_object_path: blueprintPath,
    blueprint: bp,
  })
  emit('saved', bp)
  return bp
}

async function handleSave() {
  saving.value = true
  saveMessage.value = ''
  try {
    await doSave()
    saveMessage.value = t('ppt.saved')
    setTimeout(() => { saveMessage.value = '' }, 2000)
  } catch (err: any) {
    console.error('Save failed:', err)
    saveMessage.value = t('ppt.save_failed')
  } finally {
    saving.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    // Save first, then export from the saved blueprint
    const bp = await doSave()

    const result = await renderPresentationPptx({
      user_id: props.userId || 'anonymous',
      blueprint_object_path: props.blueprintObjectPath,
      filename: `${bp.deck_goal || 'presentation'}.pptx`,
      title: bp.deck_goal || 'PPT',
    })

    if (result?.url) {
      window.open(result.url, '_blank')
    }
    emit('exported', result)
  } catch (err: any) {
    console.error('Export failed:', err)
    alert(t('ppt.export_failed', { message: err.message || err }))
  } finally {
    exporting.value = false
  }
}

// ---------------------------------------------------------------------------
// Toolbar: listen to selection
// ---------------------------------------------------------------------------
const { syncToolbarFromSelection, onSelectionCreated, onSelectionCleared, startAngleDrag } = createPresentationToolbar({ getCanvas: () => fc, angleToCoordsPercent, selectedObj, selectedIsText, selectedIsShape, toolFontSize, toolColor, toolBold, toolAlign, toolFillMode, toolFillColor, toolGradientFrom, toolGradientTo, toolGradientAngle, toolStrokeColor, toolOpacity, toolCornerRadius })

// Add / Delete elements
// ---------------------------------------------------------------------------
let blockCounter = 1000

function addText() {
  if (!fc) return
  const id = `user_text_${blockCounter++}`
  const tb = new fabric.Textbox(t('ppt.new_text'), {
    left: 100, top: 100, width: 300,
    fontSize: 24,
    fill: '#222222',
    fontFamily: "'PingFang SC', 'Microsoft YaHei', sans-serif",
    editable: true,
    selectable: true,
  })
  ;(tb as any)._blockId = id
  ;(tb as any)._blockType = 'text_box'
  fc.add(tb)
  fc.setActiveObject(tb)
  fc.renderAll()
}

function addRect() {
  if (!fc) return
  const id = `user_rect_${blockCounter++}`
  const rect = new fabric.Rect({
    left: 100, top: 100, width: 200, height: 120,
    fill: '#ffffff',
    stroke: '#e2e8f0',
    strokeWidth: 1,
    rx: 8, ry: 8,
    selectable: true,
  })
  ;(rect as any)._blockId = id
  ;(rect as any)._blockType = 'rectangle'
  fc.add(rect)
  fc.setActiveObject(rect)
  fc.renderAll()
}

function deleteSelected() {
  if (!fc) return
  const obj = fc.getActiveObject()
  if (!obj) return
  // Don't delete if the user is actively editing text
  if (obj instanceof fabric.Textbox && obj.isEditing) return
  fc.remove(obj)
  selectedObj.value = null
  fc.renderAll()
}

// ---------------------------------------------------------------------------
// Undo / Redo
// ---------------------------------------------------------------------------
const undoStack: string[] = []
const redoStack: string[] = []
let _undoLock = false

function saveUndoState() {
  if (!fc || _undoLock) return
  const json = JSON.stringify(fc.toJSON())
  // Don't push duplicates
  if (undoStack.length > 0 && undoStack[undoStack.length - 1] === json) return
  undoStack.push(json)
  if (undoStack.length > 50) undoStack.shift()
  redoStack.length = 0
}

async function undo() {
  if (!fc || undoStack.length === 0) return
  const current = JSON.stringify(fc.toJSON())
  redoStack.push(current)
  const prev = undoStack.pop()!
  _undoLock = true
  await fc.loadFromJSON(prev)
  fc.renderAll()
  _undoLock = false
}

async function redo() {
  if (!fc || redoStack.length === 0) return
  const current = JSON.stringify(fc.toJSON())
  undoStack.push(current)
  const next = redoStack.pop()!
  _undoLock = true
  await fc.loadFromJSON(next)
  fc.renderAll()
  _undoLock = false
}

function onKeyDown(e: KeyboardEvent) {
  if (!fc || isFullscreen.value) return
  const active = fc.getActiveObject()
  if (active instanceof fabric.Textbox && active.isEditing) return

  const isCtrlOrCmd = e.ctrlKey || e.metaKey
  const step = e.shiftKey ? 10 : 1

  // Undo: Ctrl+Z / Cmd+Z
  if (isCtrlOrCmd && e.key === 'z' && !e.shiftKey) {
    e.preventDefault()
    undo()
    return
  }
  // Redo: Ctrl+Shift+Z / Cmd+Shift+Z or Ctrl+Y
  if ((isCtrlOrCmd && e.key === 'z' && e.shiftKey) || (isCtrlOrCmd && e.key === 'y')) {
    e.preventDefault()
    redo()
    return
  }

  // Delete
  if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault()
    saveUndoState()
    deleteSelected()
    return
  }

  // Arrow keys: move selected object
  if (!active) return
  if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
    e.preventDefault()
    saveUndoState()
    switch (e.key) {
      case 'ArrowLeft':  active.set('left', (active.left || 0) - step); break
      case 'ArrowRight': active.set('left', (active.left || 0) + step); break
      case 'ArrowUp':    active.set('top', (active.top || 0) - step); break
      case 'ArrowDown':  active.set('top', (active.top || 0) + step); break
    }
    active.setCoords()
    fc.renderAll()
  }
}

// ---------------------------------------------------------------------------
// Smart alignment guides
// ---------------------------------------------------------------------------
const { clearGuides, addGuideLine, onObjectMoving, onObjectModified } = createPresentationGuides(() => fc, guideLines)

// Fullscreen preview
// ---------------------------------------------------------------------------
const isFullscreen = ref(false)
const fsPageIndex = ref(0)
const fsCanvasEl = ref<HTMLCanvasElement | null>(null)
let fsFc: fabric.StaticCanvas | null = null

const fsOverlayEl = ref<HTMLDivElement | null>(null)

function enterFullscreen() {
  saveCurrentPageToBlueprint()
  isFullscreen.value = true
  fsPageIndex.value = currentPageIndex.value
  nextTick(() => {
    // Request native fullscreen on the overlay element
    fsOverlayEl.value?.requestFullscreen?.().catch(() => {})
    renderFsPage(fsPageIndex.value)
  })
}

function exitFullscreen() {
  isFullscreen.value = false
  if (fsFc) { fsFc.dispose(); fsFc = null }
  // Exit native fullscreen if active
  if (document.fullscreenElement) {
    document.exitFullscreen?.().catch(() => {})
  }
}

function renderFsPage(idx: number) {
  if (!fsCanvasEl.value) return
  if (fsFc) { fsFc.dispose(); fsFc = null }

  const vw = window.innerWidth
  const vh = window.innerHeight
  const scale = Math.min(vw / CANVAS_W, vh / CANVAS_H)
  const dpr = window.devicePixelRatio || 1

  fsFc = new fabric.StaticCanvas(fsCanvasEl.value, {
    width: CANVAS_W,
    height: CANVAS_H,
    enableRetinaScaling: false,
  })
  fsFc.setDimensions({ width: Math.floor(CANVAS_W * scale), height: Math.floor(CANVAS_H * scale) }, { cssOnly: true } as any)
  fsFc.setDimensions({ width: Math.floor(CANVAS_W * scale * dpr), height: Math.floor(CANVAS_H * scale * dpr) }, { backstoreOnly: true } as any)
  fsFc.setZoom(scale * dpr)

  // Re-render the page onto the static canvas
  const bp = getWorkingBlueprint()
  const page = bp.pages?.[idx]
  if (!page) return

  const pageBg = page.style?.background || page.style?.background_color || bp.theme?.page_background || '#ffffff'
  const bgParsed = parseLinearGradient(pageBg)
  if (bgParsed) {
    const bgRect = new fabric.Rect({
      left: 0, top: 0, width: CANVAS_W, height: CANVAS_H,
      fill: makeFabricGradient(pageBg, CANVAS_W, CANVAS_H),
      selectable: false, evented: false,
    })
    fsFc.add(bgRect)
  } else {
    fsFc.backgroundColor = isTransparent(pageBg) ? '#ffffff' : pageBg
  }

  // Temporarily swap fc so addBlockToCanvas works on the fullscreen canvas
  const origFc = fc
  fc = fsFc as any
  const blocks = [...(page.blocks || [])].sort((a: any, b: any) => (a.z_index || 0) - (b.z_index || 0))
  for (const block of blocks) {
    addBlockToCanvas(block, { x: 0, y: 0, w: 1, h: 1 })
  }
  fc = origFc
  fsFc.renderAll()
}

function fsNext() {
  const bp = getWorkingBlueprint()
  if (fsPageIndex.value < (bp.pages?.length || 0) - 1) {
    fsPageIndex.value++
    renderFsPage(fsPageIndex.value)
  }
}

function fsPrev() {
  if (fsPageIndex.value > 0) {
    fsPageIndex.value--
    renderFsPage(fsPageIndex.value)
  }
}

function onFsKeyDown(e: KeyboardEvent) {
  if (!isFullscreen.value) return
  if (e.key === 'Escape') { e.preventDefault(); exitFullscreen() }
  else if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') { e.preventDefault(); fsNext() }
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); fsPrev() }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
function recalcScale() {
  if (!canvasWrapperEl.value || !fc) return
  const padding = 32
  const w = canvasWrapperEl.value.clientWidth - padding
  const h = canvasWrapperEl.value.clientHeight - padding
  if (w <= 0 || h <= 0) return
  const newScale = Math.min(w / CANVAS_W, h / CANVAS_H, 1)
  displayScale.value = newScale

  const dpr = window.devicePixelRatio || 1
  const cssW = Math.floor(CANVAS_W * newScale)
  const cssH = Math.floor(CANVAS_H * newScale)

  // Set CSS display size
  fc.setDimensions({ width: cssW, height: cssH }, { cssOnly: true } as any)
  // Set backing store at full retina resolution
  fc.setDimensions({ width: cssW * dpr, height: cssH * dpr }, { backstoreOnly: true } as any)
  // Zoom accounts for both the layout scale and the retina multiplier
  fc.setZoom(newScale * dpr)
}

function onGlobalMouseUp(_ev: MouseEvent) {
  // If fabric is still in drag state when a global mouseup fires, force-end it.
  // This rescues objects that got dragged past the canvas edge where the real
  // mouseup is never delivered to the canvas DOM element.
  if (!fc) return
  const f: any = fc as any
  const stuckDragging =
    f._currentTransform != null ||
    f._isCurrentlyDrawing === true ||
    f.__isDragging === true
  if (!stuckDragging) return
  try {
    // Fabric v6: __onMouseUp handles pointer release; fall back to private setter for v5.
    if (typeof f.__onMouseUp === 'function') {
      f.__onMouseUp(_ev)
    } else {
      f._currentTransform = null
      f.setCursor(f.defaultCursor || 'default')
      const active = f.getActiveObject()
      if (active) active.setCoords()
      f.requestRenderAll?.()
    }
  } catch {
    // Ignore — this is a best-effort rescue.
    try { (fc as any)._currentTransform = null } catch {}
    try { fc?.requestRenderAll?.() } catch {}
  }
}

onMounted(async () => {
  await nextTick()
  if (!canvasEl.value) return

  fc = new fabric.Canvas(canvasEl.value, {
    width: CANVAS_W,
    height: CANVAS_H,
    selection: true,
    preserveObjectStacking: true,
    enableRetinaScaling: false, // we handle DPI manually in recalcScale
  })
  fc.on('selection:created', onSelectionCreated)
  fc.on('selection:updated', onSelectionCreated)
  fc.on('selection:cleared', onSelectionCleared)
  fc.on('object:moving', onObjectMoving)
  fc.on('object:modified', () => { saveUndoState(); onObjectModified() })
  fc.on('mouse:up', () => { clearGuides(); fc?.renderAll() })
  fc.on('text:changed', saveUndoState)

  // Fallback: forward any global mouseup to fabric so dragging terminates even
  // when the user releases the button outside the canvas element (e.g. after
  // dragging an object past the canvas edge). Without this fabric's drag state
  // can get stuck and the object keeps following the cursor.
  document.addEventListener('mouseup', onGlobalMouseUp, true)
  document.addEventListener('mouseleave', onGlobalMouseUp, true)

  workingBlueprint.value = JSON.parse(JSON.stringify(props.blueprint))
  // Fix corrupted coordinate_space: children inside groups must be 'parent',
  // not 'page'. Previous versions of the editor incorrectly forced 'page'.
  for (const page of (workingBlueprint.value?.pages || [])) {
    for (const block of (page.blocks || [])) {
      if (block.children?.length) {
        for (const child of block.children) {
          if (child.coordinate_space === 'page') {
            child.coordinate_space = 'parent'
          }
        }
      }
    }
  }
  pages.value = workingBlueprint.value?.pages || []
  if (pages.value.length > 0) {
    loadPageToCanvas(0)
    nextTick(() => saveUndoState())
  }

  // Auto-fit canvas to container
  if (canvasWrapperEl.value) {
    resizeOb = new ResizeObserver(recalcScale)
    resizeOb.observe(canvasWrapperEl.value)
  }
  recalcScale()
  document.addEventListener('keydown', onKeyDown)
  document.addEventListener('keydown', onFsKeyDown)
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

function onFullscreenChange() {
  // If user exited native fullscreen (e.g. via browser ESC), close our overlay too
  if (!document.fullscreenElement && isFullscreen.value) {
    isFullscreen.value = false
    if (fsFc) { fsFc.dispose(); fsFc = null }
  }
}

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('keydown', onFsKeyDown)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('mouseup', onGlobalMouseUp, true)
  document.removeEventListener('mouseleave', onGlobalMouseUp, true)
  if (fsFc) { fsFc.dispose(); fsFc = null }
  resizeOb?.disconnect()
  resizeOb = null
  if (fc) {
    fc.dispose()
    fc = null
  }
})
</script>

<template>
  <div class="pe-overlay">
    <!-- Left sidebar: slide list -->
    <aside class="pe-sidebar">
      <div class="pe-sidebar-header">
        <span>{{ t('ppt.pages') }}</span>
        <span class="pe-badge">{{ totalPages }}</span>
      </div>
      <div class="pe-slide-list">
        <div
          v-for="(page, idx) in pages"
          :key="page.page_id || idx"
          class="pe-slide-item"
          :class="{ 'pe-slide-active': idx === currentPageIndex }"
          @click="goToPage(idx)"
        >
          <div class="pe-slide-num">{{ idx + 1 }}</div>
          <div class="pe-slide-info">
            <div class="pe-slide-title">{{ page.page_title || t('ppt.page', { index: idx + 1 }) }}</div>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main area -->
    <div class="pe-main">
      <!-- Toolbar -->
      <div class="pe-toolbar">
        <!-- Property tools -->
        <div class="pe-tool-group">
          <!-- Text tools -->
          <template v-if="selectedIsText">
            <div class="pe-tool-item">
              <span class="pe-tool-label">{{ t('ppt.size') }}</span>
              <input v-model.number="toolFontSize" type="number" min="8" max="120" class="pe-input-num w-14" />
            </div>
            <div class="pe-tool-item">
              <span class="pe-tool-label">{{ t('ppt.color') }}</span>
              <label class="pe-color-swatch" :style="{ background: toolColor }">
                <input v-model="toolColor" type="color" class="sr-only" />
              </label>
            </div>
            <div class="pe-tool-item">
              <button class="pe-btn-icon" :class="{ 'pe-btn-active': toolBold }" @click="toolBold = !toolBold" :title="t('ppt.bold')">
                <b>B</b>
              </button>
            </div>
            <div class="pe-tool-item">
              <div class="pe-btn-group">
                <button v-for="a in ['left', 'center', 'right']" :key="a"
                  class="pe-btn-icon" :class="{ 'pe-btn-active': toolAlign === a }" @click="toolAlign = a" :title="t('ppt.align.' + a)">
                  <svg v-if="a==='left'" width="14" height="14" viewBox="0 0 14 14"><path d="M2 3h10M2 6h6M2 9h8M2 12h4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
                  <svg v-else-if="a==='center'" width="14" height="14" viewBox="0 0 14 14"><path d="M2 3h10M4 6h6M3 9h8M5 12h4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
                  <svg v-else width="14" height="14" viewBox="0 0 14 14"><path d="M2 3h10M6 6h6M4 9h8M8 12h4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
                </button>
              </div>
            </div>
          </template>
          <!-- Shape tools -->
          <template v-else-if="selectedIsShape">
            <div class="pe-tool-item">
              <div class="pe-btn-group">
                <button class="pe-btn-sm" :class="{ 'pe-btn-active': toolFillMode === 'solid' }" @click="toolFillMode = 'solid'">{{ t('ppt.fill.solid') }}</button>
                <button class="pe-btn-sm" :class="{ 'pe-btn-active': toolFillMode === 'gradient' }" @click="toolFillMode = 'gradient'">{{ t('ppt.fill.gradient') }}</button>
              </div>
            </div>
            <template v-if="toolFillMode === 'solid'">
              <div class="pe-tool-item">
                <span class="pe-tool-label">{{ t('ppt.fill') }}</span>
                <label class="pe-color-swatch" :style="{ background: toolFillColor }">
                  <input v-model="toolFillColor" type="color" class="sr-only" />
                </label>
              </div>
            </template>
            <template v-else>
              <div class="pe-tool-item">
                <label class="pe-color-swatch" :style="{ background: toolGradientFrom }" :title="t('ppt.gradient.start')">
                  <input v-model="toolGradientFrom" type="color" class="sr-only" />
                </label>
                <span class="text-gray-300 text-xs px-0.5">&#8594;</span>
                <label class="pe-color-swatch" :style="{ background: toolGradientTo }" :title="t('ppt.gradient.end')">
                  <input v-model="toolGradientTo" type="color" class="sr-only" />
                </label>
              </div>
              <div class="pe-tool-item">
                <div class="pe-angle-dial" :title="t('ppt.gradient.drag_angle')" @mousedown="startAngleDrag">
                  <div class="pe-angle-needle" :style="{ transform: `rotate(${toolGradientAngle}deg)` }" />
                  <div class="pe-angle-dot" />
                </div>
                <span class="pe-tool-label">{{ toolGradientAngle }}°</span>
              </div>
            </template>
            <div class="pe-tool-item">
              <span class="pe-tool-label">{{ t('ppt.border') }}</span>
              <label class="pe-color-swatch" :style="{ background: toolStrokeColor }">
                <input v-model="toolStrokeColor" type="color" class="sr-only" />
              </label>
            </div>
            <div class="pe-tool-item">
              <span class="pe-tool-label">{{ t('ppt.opacity') }}</span>
              <input v-model.number="toolOpacity" type="range" min="0" max="100" class="pe-range" />
              <span class="pe-tool-value">{{ toolOpacity }}%</span>
            </div>
            <div class="pe-tool-item">
              <span class="pe-tool-label">{{ t('ppt.radius') }}</span>
              <input v-model.number="toolCornerRadius" type="number" min="0" max="100" class="pe-input-num w-12" />
            </div>
          </template>
          <span v-else class="text-xs text-gray-400 italic">{{ t('ppt.select_element') }}</span>
        </div>

        <div class="pe-toolbar-sep" />

        <!-- Add / Delete -->
        <div class="pe-tool-group">
          <button class="pe-btn pe-btn-outline" @click="addText">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 3h8M7 3v8"/></svg>
            {{ t('ppt.add_text') }}
          </button>
          <button class="pe-btn pe-btn-outline" @click="addRect">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="3" width="10" height="8" rx="1.5"/></svg>
            {{ t('ppt.rect') }}
          </button>
          <button class="pe-btn pe-btn-danger" :disabled="!selectedObj" @click="deleteSelected">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 4h8M5.5 4V3h3v1M4.5 4v7.5h5V4"/></svg>
          </button>
        </div>

        <div class="flex-1" />

        <!-- Page nav -->
        <div class="pe-tool-group">
          <button class="pe-btn pe-btn-ghost" :disabled="currentPageIndex === 0" @click="goToPage(currentPageIndex - 1)">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 3l-4 4 4 4"/></svg>
          </button>
          <span class="pe-page-label">{{ currentPageIndex + 1 }}<span class="text-gray-300"> / </span>{{ totalPages }}</span>
          <button class="pe-btn pe-btn-ghost" :disabled="currentPageIndex >= totalPages - 1" @click="goToPage(currentPageIndex + 1)">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 3l4 4-4 4"/></svg>
          </button>
        </div>

        <div class="pe-toolbar-sep" />

        <!-- Actions -->
        <div class="pe-tool-group">
          <button class="pe-btn pe-btn-secondary" :disabled="saving" @click="handleSave">
            {{ saving ? t('ppt.saving') : t('ui.save') }}
          </button>
          <span v-if="saveMessage" class="text-xs text-emerald-500 font-medium">{{ saveMessage }}</span>
          <button class="pe-btn pe-btn-outline" @click="enterFullscreen" :title="t('ppt.fullscreen_preview')">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 5V2h3M9 2h3v3M12 9v3h-3M5 12H2V9"/></svg>
            {{ t('ui.preview') }}
          </button>
          <button class="pe-btn pe-btn-primary" :disabled="exporting" @click="handleExport">
            {{ exporting ? t('ppt.exporting') : t('ppt.export_ppt') }}
          </button>
          <button class="pe-btn pe-btn-ghost" @click="emit('close')" :title="t('ppt.close_editor')">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>
          </button>
        </div>
      </div>

      <!-- Canvas area -->
      <div ref="canvasWrapperEl" class="pe-canvas-area">
        <div class="pe-canvas-frame">
          <canvas ref="canvasEl" style="display:block" />
        </div>
      </div>
    </div>

    <!-- Fullscreen preview overlay -->
    <div v-if="isFullscreen" ref="fsOverlayEl" class="pe-fs-overlay" @click="exitFullscreen">
      <div class="pe-fs-canvas" @click.stop>
        <canvas ref="fsCanvasEl" style="display:block" />
      </div>
      <!-- Page indicator -->
      <div class="pe-fs-indicator">
        {{ fsPageIndex + 1 }} / {{ totalPages }}
      </div>
      <!-- Nav arrows -->
      <button v-if="fsPageIndex > 0" class="pe-fs-nav pe-fs-nav-left" @click.stop="fsPrev">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round"><path d="M20 8l-8 8 8 8"/></svg>
      </button>
      <button v-if="fsPageIndex < totalPages - 1" class="pe-fs-nav pe-fs-nav-right" @click.stop="fsNext">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round"><path d="M12 8l8 8-8 8"/></svg>
      </button>
      <!-- ESC hint -->
      <div class="pe-fs-hint">{{ t('ppt.press_esc') }}</div>
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ────────────────────────────────────── */
.pe-overlay {
  position: fixed; inset: 0; z-index: 50;
  display: flex;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(8px);
}
.pe-sidebar {
  width: 200px; flex-shrink: 0;
  background: #f8fafc;
  border-right: 1px solid #e2e8f0;
  display: flex; flex-direction: column;
}
.pe-sidebar-header {
  padding: 14px 16px; font-size: 13px; font-weight: 600; color: #334155;
  border-bottom: 1px solid #e2e8f0;
  display: flex; align-items: center; gap: 8px;
}
.pe-badge {
  font-size: 11px; font-weight: 500;
  background: #e2e8f0; color: #64748b;
  padding: 1px 7px; border-radius: 10px;
}
.pe-slide-list {
  flex: 1; overflow-y: auto; padding: 8px;
}
.pe-slide-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; margin-bottom: 4px;
  border-radius: 8px; cursor: pointer;
  transition: all 0.15s;
  border: 2px solid transparent;
}
.pe-slide-item:hover { background: #f1f5f9; }
.pe-slide-active {
  background: #eff6ff !important;
  border-color: #3b82f6;
}
.pe-slide-num {
  width: 24px; height: 24px; border-radius: 6px;
  background: #e2e8f0; color: #64748b;
  font-size: 11px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.pe-slide-active .pe-slide-num {
  background: #3b82f6; color: #fff;
}
.pe-slide-info { min-width: 0; }
.pe-slide-title {
  font-size: 12px; font-weight: 500; color: #475569;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pe-slide-active .pe-slide-title { color: #1e40af; font-weight: 600; }

.pe-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }

/* ── Toolbar ───────────────────────────────────── */
.pe-toolbar {
  height: 48px; flex-shrink: 0;
  background: #fff; border-bottom: 1px solid #e2e8f0;
  display: flex; align-items: center;
  padding: 0 12px; gap: 6px;
}
.pe-toolbar-sep {
  width: 1px; height: 24px; background: #e2e8f0; margin: 0 4px;
}
.pe-tool-group {
  display: flex; align-items: center; gap: 6px;
}
.pe-tool-item {
  display: flex; align-items: center; gap: 4px;
}
.pe-tool-label {
  font-size: 11px; color: #94a3b8; font-weight: 500; user-select: none;
}
.pe-tool-value {
  font-size: 11px; color: #64748b; min-width: 28px;
}

/* ── Inputs ────────────────────────────────────── */
.pe-input-num {
  height: 28px; font-size: 12px;
  border: 1px solid #e2e8f0; border-radius: 6px;
  padding: 0 6px; text-align: center;
  outline: none; transition: border 0.15s;
}
.pe-input-num:focus { border-color: #3b82f6; }

.pe-color-swatch {
  width: 26px; height: 26px; border-radius: 6px;
  border: 2px solid #e2e8f0; cursor: pointer;
  display: block; transition: border-color 0.15s;
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}
.pe-color-swatch:hover { border-color: #94a3b8; }

.pe-range {
  width: 72px; height: 28px;
  accent-color: #3b82f6;
}

/* ── Buttons ───────────────────────────────────── */
.pe-btn {
  display: inline-flex; align-items: center; gap: 4px;
  height: 30px; padding: 0 10px;
  font-size: 12px; font-weight: 500;
  border-radius: 7px; border: none; cursor: pointer;
  transition: all 0.15s; white-space: nowrap;
}
.pe-btn:disabled { opacity: 0.35; cursor: default; }

.pe-btn-primary {
  background: #10b981; color: #fff;
}
.pe-btn-primary:hover:not(:disabled) { background: #059669; }

.pe-btn-secondary {
  background: #3b82f6; color: #fff;
}
.pe-btn-secondary:hover:not(:disabled) { background: #2563eb; }

.pe-btn-outline {
  background: #fff; color: #475569;
  border: 1px solid #e2e8f0;
}
.pe-btn-outline:hover:not(:disabled) { background: #f8fafc; border-color: #cbd5e1; }

.pe-btn-danger {
  background: #fff; color: #ef4444;
  border: 1px solid #fecaca;
  padding: 0 8px;
}
.pe-btn-danger:hover:not(:disabled) { background: #fef2f2; }

.pe-btn-ghost {
  background: transparent; color: #64748b;
  padding: 0 6px;
}
.pe-btn-ghost:hover:not(:disabled) { background: #f1f5f9; color: #334155; }

.pe-btn-icon {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 6px; border: 1px solid #e2e8f0;
  background: #fff; color: #64748b; cursor: pointer;
  transition: all 0.15s; font-size: 13px;
}
.pe-btn-icon:hover { background: #f1f5f9; }
.pe-btn-active {
  background: #1e293b !important; color: #fff !important;
  border-color: #1e293b !important;
}

.pe-btn-sm {
  height: 26px; padding: 0 8px;
  font-size: 11px; font-weight: 500;
  border-radius: 5px; border: 1px solid #e2e8f0;
  background: #fff; color: #64748b; cursor: pointer;
  transition: all 0.15s;
}
.pe-btn-sm:hover { background: #f1f5f9; }
.pe-btn-sm.pe-btn-active {
  background: #1e293b; color: #fff; border-color: #1e293b;
}

.pe-btn-group {
  display: flex; gap: 1px;
  background: #e2e8f0; border-radius: 6px; overflow: hidden;
}
.pe-btn-group > .pe-btn-icon,
.pe-btn-group > .pe-btn-sm { border-radius: 0; border: none; }

/* ── Angle dial ────────────────────────────────── */
.pe-angle-dial {
  width: 26px; height: 26px; border-radius: 50%;
  border: 2px solid #e2e8f0; background: #fff;
  position: relative; cursor: pointer;
  transition: border-color 0.15s;
}
.pe-angle-dial:hover { border-color: #94a3b8; }
.pe-angle-needle {
  position: absolute; width: 2px; height: 9px;
  background: #3b82f6; border-radius: 2px;
  left: 50%; top: 2px;
  transform-origin: bottom center;
  margin-left: -1px;
}
.pe-angle-dot {
  position: absolute; width: 4px; height: 4px;
  background: #3b82f6; border-radius: 50%;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
}

/* ── Page nav ──────────────────────────────────── */
.pe-page-label {
  font-size: 12px; font-weight: 600; color: #475569;
  padding: 0 4px; min-width: 40px; text-align: center;
}

/* ── Canvas ────────────────────────────────────── */
.pe-canvas-area {
  flex: 1; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  background: #e5e7eb;
  background-image: radial-gradient(#d1d5db 1px, transparent 1px);
  background-size: 20px 20px;
}
.pe-canvas-frame {
  border-radius: 8px; overflow: hidden;
  box-shadow:
    0 20px 60px rgba(0, 0, 0, 0.2),
    0 0 0 1px rgba(0, 0, 0, 0.05);
}

/* ── Custom scrollbar ──────────────────────────── */
.pe-slide-list::-webkit-scrollbar { width: 5px; }
.pe-slide-list::-webkit-scrollbar-track { background: transparent; }
.pe-slide-list::-webkit-scrollbar-thumb {
  background: #cbd5e1; border-radius: 10px;
}
.pe-slide-list::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

/* ── Fullscreen preview ────────────────────────── */
.pe-fs-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: #000;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.pe-fs-canvas {
  cursor: default;
}
.pe-fs-indicator {
  position: absolute; bottom: 24px; left: 50%;
  transform: translateX(-50%);
  font-size: 14px; font-weight: 500; color: rgba(255,255,255,0.6);
  background: rgba(0,0,0,0.5); padding: 6px 16px;
  border-radius: 20px; backdrop-filter: blur(4px);
  user-select: none;
}
.pe-fs-hint {
  position: absolute; top: 20px; right: 24px;
  font-size: 12px; color: rgba(255,255,255,0.35);
  user-select: none;
}
.pe-fs-nav {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 48px; height: 48px;
  border-radius: 50%; border: none;
  background: rgba(255,255,255,0.1);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: background 0.2s;
  backdrop-filter: blur(4px);
}
.pe-fs-nav:hover { background: rgba(255,255,255,0.2); }
.pe-fs-nav-left { left: 20px; }
.pe-fs-nav-right { right: 20px; }

/* ── sr-only for color inputs ──────────────────── */
.sr-only {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0, 0, 0, 0); border: 0;
}
</style>
