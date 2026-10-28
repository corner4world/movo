import type { Ref } from 'vue'
import * as fabric from 'fabric'
import { linePageEndpoints } from '../../utils/presentationLineGeometry'
import { CANVAS_W, CANVAS_H } from './presentationConstants'

export function createPresentationBlueprintAdapter(context: { getCanvas: () => fabric.Canvas | null; workingBlueprint: Ref<any>; props: { blueprint: any }; currentPageIndex: Ref<number>; resolveBlockGeometry: (block: any, parentRect: { x: number; y: number; w: number; h: number }) => any }) {
  const { getCanvas, workingBlueprint, props, currentPageIndex, resolveBlockGeometry } = context

function getWorkingBlueprint(): any {
  if (!workingBlueprint.value) {
    workingBlueprint.value = JSON.parse(JSON.stringify(props.blueprint))
  }
  return workingBlueprint.value
}

function canvasToBlueprint(): any {
  const fc = getCanvas()
  if (!fc) return getWorkingBlueprint()
  const bp = JSON.parse(JSON.stringify(getWorkingBlueprint()))
  const page = bp.pages[currentPageIndex.value]
  if (!page) return bp

  // Serialize a Fabric fill (string or Gradient) back to CSS for blueprint
  function serializeFill(fill: any): string {
    if (!fill) return 'transparent'
    if (typeof fill === 'string') return fill
    // Fabric Gradient object → CSS linear-gradient
    if (fill.type === 'linear' && fill.colorStops?.length >= 2) {
      const coords = fill.coords || {}
      const dx = (coords.x2 ?? 1) - (coords.x1 ?? 0)
      const dy = (coords.y2 ?? 0) - (coords.y1 ?? 0)
      const angle = Math.round((Math.atan2(dy, dx) * 180 / Math.PI + 90 + 360) % 360)
      const stops = fill.colorStops
        .map((s: any) => `${s.color} ${Math.round(s.offset * 100)}%`)
        .join(', ')
      return `linear-gradient(${angle}deg, ${stops})`
    }
    return 'transparent'
  }

  const objects = fc.getObjects()
  const canvasBlockIds = new Set<string>()

  // Only map TOP-LEVEL blocks — children inside groups are preserved as-is
  // from blueprint. Canvas objects for children (created by addBlockToCanvas
  // recursion) should not write back to nested children blocks.
  const blockMap = new Map<string, any>()
  for (const b of page.blocks) {
    if (b.id) blockMap.set(b.id, b)
  }

  // Build a flat id → { block, parentRect } map, where parentRect is the
  // normalized (0-1) rectangle of the block's parent container. This lets us
  // convert absolute fabric pixel coordinates back to parent-relative
  // normalized coordinates when saving children of a group/rectangle.
  type FlatEntry = { block: any; parentRect: { x: number; y: number; w: number; h: number }; parentBlock: any | null }
  const flatMap = new Map<string, FlatEntry>()
  const childIds = new Set<string>()
  function collectBlocksRecursive(
    blocks: any[],
    parentBlock: any | null,
    parentRect: { x: number; y: number; w: number; h: number },
  ) {
    for (const b of blocks) {
      if (!b || !b.id) continue
      if (parentBlock !== null) childIds.add(b.id)
      flatMap.set(b.id, { block: b, parentRect, parentBlock })
      if (b.children?.length) {
        // Resolve this block's own normalized rect to use as parentRect for its children.
        const geom = resolveBlockGeometry(b, parentRect)
        const selfRect = { x: geom.bx, y: geom.by, w: geom.bw, h: geom.bh }
        collectBlocksRecursive(b.children, b, selfRect)
      }
    }
  }
  collectBlocksRecursive(page.blocks, null, { x: 0, y: 0, w: 1, h: 1 })

  // Helpers: write normalized coordinates back to a block, respecting its
  // coordinate_space (children use parent-relative coordinates).
  function writeBlockXY(block: any, entry: FlatEntry, absPxLeft: number, absPxTop: number) {
    const space = (block.coordinate_space || (entry.parentBlock ? 'parent' : 'page')).toLowerCase()
    const nx = absPxLeft / CANVAS_W
    const ny = absPxTop / CANVAS_H
    if (space === 'parent' && entry.parentRect.w > 0 && entry.parentRect.h > 0) {
      block.x = (nx - entry.parentRect.x) / entry.parentRect.w
      block.y = (ny - entry.parentRect.y) / entry.parentRect.h
    } else {
      block.x = nx
      block.y = ny
    }
  }
  function writeBlockSize(block: any, entry: FlatEntry, absPxW: number, absPxH: number) {
    const space = (block.coordinate_space || (entry.parentBlock ? 'parent' : 'page')).toLowerCase()
    const nw = absPxW / CANVAS_W
    const nh = absPxH / CANVAS_H
    if (space === 'parent' && entry.parentRect.w > 0 && entry.parentRect.h > 0) {
      block.w = nw / entry.parentRect.w
      block.h = nh / entry.parentRect.h
    } else {
      block.w = nw
      block.h = nh
    }
  }

  for (const obj of objects) {
    if ((obj as any)._isGuide) continue
    const blockId = (obj as any)._blockId as string
    const blockType = (obj as any)._blockType as string
    // Skip helper objects
    if (!blockId || blockType === 'text_bg' || blockType === 'container') continue
    if (blockType === 'icon') { canvasBlockIds.add(blockId); continue }
    canvasBlockIds.add(blockId)

    // Prefer the flat map (covers both top-level and nested children); fall
    // back to the top-level blockMap for edge cases.
    const entry = flatMap.get(blockId)
    const block = entry?.block || blockMap.get(blockId)
    if (block) {
      if (blockType === 'line') {
        const line = obj as fabric.Line
        const endpoints = linePageEndpoints(line)
        if (entry) {
          writeBlockXY(block, entry, endpoints.start.x, endpoints.start.y)
          const endX = endpoints.end.x / CANVAS_W
          const endY = endpoints.end.y / CANVAS_H
          const space = (block.coordinate_space || (entry.parentBlock ? 'parent' : 'page')).toLowerCase()
          if (space === 'parent' && entry.parentRect.w > 0 && entry.parentRect.h > 0) {
            block.x2 = (endX - entry.parentRect.x) / entry.parentRect.w
            block.y2 = (endY - entry.parentRect.y) / entry.parentRect.h
          } else {
            block.x2 = endX
            block.y2 = endY
          }
        } else {
          block.x = endpoints.start.x / CANVAS_W
          block.y = endpoints.start.y / CANVAS_H
          block.x2 = endpoints.end.x / CANVAS_W
          block.y2 = endpoints.end.y / CANVAS_H
        }
      } else if (blockType === 'text_box' && obj instanceof fabric.Textbox) {
        const layoutBox = (obj as any)._layoutBox
        const scaleX = obj.scaleX || 1
        const boxLeft = layoutBox
          ? layoutBox.left + (Number(obj.left || 0) - layoutBox.textLeft)
          : Number(obj.left || 0)
        const boxTop = layoutBox
          ? layoutBox.top + (Number(obj.top || 0) - layoutBox.textTop)
          : Number(obj.top || 0)
        const boxWidth = layoutBox
          ? Math.max(1, layoutBox.width + ((Number(obj.width || 0) * scaleX) - layoutBox.textWidth))
          : Number(obj.width || 0) * scaleX
        if (entry) {
          writeBlockXY(block, entry, boxLeft, boxTop)
          writeBlockSize(block, entry, boxWidth, layoutBox?.height || Number(obj.height || 0))
        } else {
          block.x = boxLeft / CANVAS_W
          block.y = boxTop / CANVAS_H
          block.w = boxWidth / CANVAS_W
        }
        // Textbox height: only save if user scaled, otherwise keep blueprint value
        const sy = obj.scaleY || 1
        if (Math.abs(sy - 1) > 0.001) {
          const absH = (obj as any).height * sy
          if (entry) {
            block.h = entry.parentRect.h > 0
              ? (absH / CANVAS_H) / entry.parentRect.h
              : absH / CANVAS_H
          } else {
            block.h = absH / CANVAS_H
          }
        }
        block.content = obj.text || ''
        if (!block.style) block.style = {}
        block.style.font_size = obj.fontSize
        block.style.font_weight = obj.fontWeight === 'bold' ? 'bold' : undefined
        block.style.color = obj.fill as string
        block.style.text_align = obj.textAlign
        if (obj.opacity != null && obj.opacity < 1) {
          block.style.opacity = obj.opacity
        }
      } else {
        if (entry) {
          writeBlockXY(block, entry, obj.left || 0, obj.top || 0)
        } else {
          block.x = (obj.left || 0) / CANVAS_W
          block.y = (obj.top || 0) / CANVAS_H
        }
        const sx = obj.scaleX || 1
        const sy = obj.scaleY || 1
        if (Math.abs(sx - 1) > 0.001 || Math.abs(sy - 1) > 0.001) {
          const absW = (obj as any).width * sx
          const absH = (obj as any).height * sy
          if (entry) {
            writeBlockSize(block, entry, absW, absH)
          } else {
            block.w = absW / CANVAS_W
            block.h = absH / CANVAS_H
          }
        }
        // Save shape visual properties
        if (!block.style) block.style = {}
        block.style.background = serializeFill((obj as any).fill)
        const stroke = (obj as any).stroke
        if (stroke && stroke !== 'transparent') {
          block.style.border_color = stroke
        }
        if (obj.opacity != null && obj.opacity < 1) {
          block.style.opacity = obj.opacity
        }
        if ((obj as any).rx) {
          block.style.border_radius = (obj as any).rx
        }
      }
    } else {
      // New element added by user
      const newBlock: any = {
        id: blockId,
        type: blockType || 'text_box',
        coordinate_space: 'page',
        x: (obj.left || 0) / CANVAS_W,
        y: (obj.top || 0) / CANVAS_H,
        w: ((obj as any).width * (obj.scaleX || 1)) / CANVAS_W,
        h: ((obj as any).height * (obj.scaleY || 1)) / CANVAS_H,
        style: {},
        content: '',
        z_index: 5,
      }
      if (blockType === 'text_box' && obj instanceof fabric.Textbox) {
        newBlock.content = obj.text || ''
        newBlock.style.font_size = obj.fontSize
        newBlock.style.font_weight = obj.fontWeight === 'bold' ? 'bold' : undefined
        newBlock.style.color = obj.fill as string
        newBlock.style.text_align = obj.textAlign
        if (obj.opacity != null && obj.opacity < 1) {
          newBlock.style.opacity = obj.opacity
        }
      }
      if (blockType === 'rectangle' || blockType === 'circle' || blockType === 'group') {
        newBlock.style.background = serializeFill((obj as any).fill)
        if ((obj as any).stroke && (obj as any).stroke !== 'transparent') {
          newBlock.style.border_color = (obj as any).stroke
        }
        if (obj.opacity != null && obj.opacity < 1) {
          newBlock.style.opacity = obj.opacity
        }
        newBlock.style.border_radius = (obj as any).rx || 0
      }
      page.blocks.push(newBlock)
    }
  }

  // Remove deleted top-level blocks — keep blocks that:
  // - have a canvas object (canvasBlockIds)
  // - have children (group containers)
  // - are parents of known children
  page.blocks = page.blocks.filter((b: any) => {
    return canvasBlockIds.has(b.id) || b.children?.length
  })

  // Never modify children arrays — they stay as blueprint authored them

  // Persist to working copy so page switches preserve edits
  workingBlueprint.value = bp
  return bp
}

function findBlockById(blocks: any[], id: string): any | null {
  for (const b of blocks) {
    if (b.id === id) return b
    if (b.children?.length) {
      const found = findBlockById(b.children, id)
      if (found) return found
    }
  }
  return null
}

// ---------------------------------------------------------------------------
  return { getWorkingBlueprint, canvasToBlueprint, findBlockById }
}
