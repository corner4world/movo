import * as fabric from 'fabric'
import { CANVAS_W, CANVAS_H } from './presentationConstants'

export function createPresentationGuides(getCanvas: () => fabric.Canvas | null, guideLines: fabric.Line[]) {
const SNAP_THRESHOLD = 8 // px in logical coords — how close before snapping
function clearGuides() {
  const fc = getCanvas()
  if (!fc) return
  for (const line of guideLines) {
    fc.remove(line)
  }
  guideLines.length = 0
}

function addGuideLine(x1: number, y1: number, x2: number, y2: number) {
  const fc = getCanvas()
  if (!fc) return
  const line = new fabric.Line([x1, y1, x2, y2], {
    stroke: '#f43f5e',
    strokeWidth: 1,
    strokeDashArray: [4, 3],
    selectable: false,
    evented: false,
    excludeFromExport: true,
  })
  ;(line as any)._isGuide = true
  guideLines.push(line)
  fc.add(line)
}

function onObjectMoving(e: any) {
  const fc = getCanvas()
  if (!fc) return
  const target = e.target as fabric.FabricObject
  if (!target || (target as any)._isGuide) return

  clearGuides()

  const tl = target.left || 0
  const tt = target.top || 0
  const tw = (target.width || 0) * (target.scaleX || 1)
  const th = (target.height || 0) * (target.scaleY || 1)
  const tCx = tl + tw / 2
  const tCy = tt + th / 2
  const tRight = tl + tw
  const tBottom = tt + th

  // Canvas center guides
  const cCx = CANVAS_W / 2
  const cCy = CANVAS_H / 2

  let snappedX = false
  let snappedY = false

  // Snap to canvas center horizontal
  if (Math.abs(tCx - cCx) < SNAP_THRESHOLD) {
    target.set('left', cCx - tw / 2)
    addGuideLine(cCx, 0, cCx, CANVAS_H)
    snappedX = true
  }
  // Snap to canvas center vertical
  if (Math.abs(tCy - cCy) < SNAP_THRESHOLD) {
    target.set('top', cCy - th / 2)
    addGuideLine(0, cCy, CANVAS_W, cCy)
    snappedY = true
  }

  // Collect edges/centers of other objects for alignment and spacing.
  // Only include selectable, meaningful shapes — skip guides, text-bg helpers,
  // non-selectable decorations, full-page backgrounds, and small child labels.
  const canvasArea = CANVAS_W * CANVAS_H
  const targetType = (target as any)._blockType || ''
  const others: { left: number; top: number; right: number; bottom: number; cx: number; cy: number }[] = []
  for (const obj of fc.getObjects()) {
    if (obj === target) continue
    if ((obj as any)._isGuide) continue
    if ((obj as any)._blockType === 'text_bg') continue
    if (!obj.selectable) continue
    const ol = obj.left || 0
    const ot = obj.top || 0
    const ow = (obj.width || 0) * (obj.scaleX || 1)
    const oh = (obj.height || 0) * (obj.scaleY || 1)
    if (ow < 1 || oh < 1) continue
    // Skip full-page background rectangles
    if (ow * oh >= canvasArea * 0.8) continue
    others.push({ left: ol, top: ot, right: ol + ow, bottom: ot + oh, cx: ol + ow / 2, cy: ot + oh / 2 })
  }

  // For spacing detection, use only selectable objects that aren't tiny
  // (at least 20px in both dimensions) — avoids icons/labels interfering.
  const spacingPeers = others.filter(o => {
    const ow = o.right - o.left
    const oh = o.bottom - o.top
    return ow >= 20 && oh >= 20
  })

  const updatedLeft = target.left || 0
  const updatedTop = target.top || 0
  const updatedCx = updatedLeft + tw / 2
  const updatedCy = updatedTop + th / 2
  const updatedRight = updatedLeft + tw
  const updatedBottom = updatedTop + th

  for (const o of others) {
    if (!snappedX) {
      // Left ↔ Left
      if (Math.abs(updatedLeft - o.left) < SNAP_THRESHOLD) {
        target.set('left', o.left)
        addGuideLine(o.left, 0, o.left, CANVAS_H)
        snappedX = true
      }
      // Right ↔ Right
      else if (Math.abs(updatedRight - o.right) < SNAP_THRESHOLD) {
        target.set('left', o.right - tw)
        addGuideLine(o.right, 0, o.right, CANVAS_H)
        snappedX = true
      }
      // Left ↔ Right
      else if (Math.abs(updatedLeft - o.right) < SNAP_THRESHOLD) {
        target.set('left', o.right)
        addGuideLine(o.right, 0, o.right, CANVAS_H)
        snappedX = true
      }
      // Right ↔ Left
      else if (Math.abs(updatedRight - o.left) < SNAP_THRESHOLD) {
        target.set('left', o.left - tw)
        addGuideLine(o.left, 0, o.left, CANVAS_H)
        snappedX = true
      }
      // Center ↔ Center X
      else if (Math.abs(updatedCx - o.cx) < SNAP_THRESHOLD) {
        target.set('left', o.cx - tw / 2)
        addGuideLine(o.cx, 0, o.cx, CANVAS_H)
        snappedX = true
      }
    }

    if (!snappedY) {
      // Top ↔ Top
      if (Math.abs(updatedTop - o.top) < SNAP_THRESHOLD) {
        target.set('top', o.top)
        addGuideLine(0, o.top, CANVAS_W, o.top)
        snappedY = true
      }
      // Bottom ↔ Bottom
      else if (Math.abs(updatedBottom - o.bottom) < SNAP_THRESHOLD) {
        target.set('top', o.bottom - th)
        addGuideLine(0, o.bottom, CANVAS_W, o.bottom)
        snappedY = true
      }
      // Top ↔ Bottom
      else if (Math.abs(updatedTop - o.bottom) < SNAP_THRESHOLD) {
        target.set('top', o.bottom)
        addGuideLine(0, o.bottom, CANVAS_W, o.bottom)
        snappedY = true
      }
      // Bottom ↔ Top
      else if (Math.abs(updatedBottom - o.top) < SNAP_THRESHOLD) {
        target.set('top', o.top - th)
        addGuideLine(0, o.top, CANVAS_W, o.top)
        snappedY = true
      }
      // Center ↔ Center Y
      else if (Math.abs(updatedCy - o.cy) < SNAP_THRESHOLD) {
        target.set('top', o.cy - th / 2)
        addGuideLine(0, o.cy, CANVAS_W, o.cy)
        snappedY = true
      }
    }

    if (snappedX && snappedY) break
  }

  // --- Equal spacing guides (runs independently from edge snapping) ---
  const curLeft = target.left || 0
  const curTop = target.top || 0
  const curRight = curLeft + tw
  const curBottom = curTop + th
  let spacingSnappedX = false
  let spacingSnappedY = false

  const curCx = curLeft + tw / 2
  const curCy = curTop + th / 2
  const yOverlap = (o: typeof others[0]) => o.bottom > curTop + 5 && o.top < curBottom - 5
  const toLeft = spacingPeers.filter(o => o.cx < curCx && yOverlap(o)).sort((a, b) => b.right - a.right)
  const toRight = spacingPeers.filter(o => o.cx > curCx && yOverlap(o)).sort((a, b) => a.left - b.left)

  // Between two neighbors: snap to equal gap
  if (toLeft.length > 0 && toRight.length > 0 && !spacingSnappedX) {
    const nearL = toLeft[0]
    const nearR = toRight[0]
    const gapL = curLeft - nearL.right
    const gapR = nearR.left - curRight
    if (gapL > 2 && gapR > 2 && Math.abs(gapL - gapR) < SNAP_THRESHOLD) {
      const avgGap = (nearL.right + nearR.left - tw) / 2
      target.set('left', avgGap)
      spacingSnappedX = true
      const markY = Math.max(nearL.top, curTop, nearR.top) +
        Math.min(nearL.bottom - nearL.top, th, nearR.bottom - nearR.top) / 2
      const snapLeft = avgGap
      const snapRight = avgGap + tw
      addGuideLine(nearL.right, markY, snapLeft, markY)
      addGuideLine(nearL.right, markY - 6, nearL.right, markY + 6)
      addGuideLine(snapLeft, markY - 6, snapLeft, markY + 6)
      addGuideLine(snapRight, markY, nearR.left, markY)
      addGuideLine(snapRight, markY - 6, snapRight, markY + 6)
      addGuideLine(nearR.left, markY - 6, nearR.left, markY + 6)
    }
  }

  // End-position: match the gap between two left neighbors
  if (toLeft.length >= 2 && !spacingSnappedX) {
    const a = toLeft[1]
    const b = toLeft[0]
    const existingGap = b.left - a.right
    const myGap = curLeft - b.right
    if (existingGap > 2 && Math.abs(myGap - existingGap) < SNAP_THRESHOLD) {
      target.set('left', b.right + existingGap)
      spacingSnappedX = true
      const markY = Math.max(a.top, b.top, curTop) + Math.min(a.bottom - a.top, b.bottom - b.top, th) / 2
      addGuideLine(a.right, markY, b.left, markY)
      addGuideLine(a.right, markY - 6, a.right, markY + 6)
      addGuideLine(b.left, markY - 6, b.left, markY + 6)
      addGuideLine(b.right, markY, b.right + existingGap, markY)
      addGuideLine(b.right, markY - 6, b.right, markY + 6)
      addGuideLine(b.right + existingGap, markY - 6, b.right + existingGap, markY + 6)
    }
  }
  // Start-position: match the gap between two right neighbors
  if (toRight.length >= 2 && !spacingSnappedX) {
    const a = toRight[0]
    const b = toRight[1]
    const existingGap = b.left - a.right
    const myGap = a.left - curRight
    if (existingGap > 2 && Math.abs(myGap - existingGap) < SNAP_THRESHOLD) {
      target.set('left', a.left - existingGap - tw)
      spacingSnappedX = true
      const markY = Math.max(a.top, b.top, curTop) + Math.min(a.bottom - a.top, b.bottom - b.top, th) / 2
      addGuideLine(a.right, markY, b.left, markY)
      addGuideLine(a.right, markY - 6, a.right, markY + 6)
      addGuideLine(b.left, markY - 6, b.left, markY + 6)
      const snapRight = a.left - existingGap
      addGuideLine(snapRight, markY, a.left, markY)
      addGuideLine(snapRight, markY - 6, snapRight, markY + 6)
      addGuideLine(a.left, markY - 6, a.left, markY + 6)
    }
  }

  // Vertical equal spacing
  const xOverlap = (o: typeof others[0]) => o.right > curLeft + 5 && o.left < curRight - 5
  const above = spacingPeers.filter(o => o.cy < curTop && xOverlap(o)).sort((a, b) => b.bottom - a.bottom)
  const below = spacingPeers.filter(o => o.cy > curBottom && xOverlap(o)).sort((a, b) => a.top - b.top)

  if (above.length > 0 && below.length > 0 && !spacingSnappedY) {
    const nearA = above[0]
    const nearB = below[0]
    const gapA = curTop - nearA.bottom
    const gapB = nearB.top - curBottom
    if (gapA > 2 && gapB > 2 && Math.abs(gapA - gapB) < SNAP_THRESHOLD) {
      const avgTop = (nearA.bottom + nearB.top - th) / 2
      target.set('top', avgTop)
      spacingSnappedY = true
      const markX = Math.max(nearA.left, curLeft, nearB.left) +
        Math.min(nearA.right - nearA.left, tw, nearB.right - nearB.left) / 2
      const snapTop = avgTop
      const snapBottom = avgTop + th
      addGuideLine(markX, nearA.bottom, markX, snapTop)
      addGuideLine(markX - 6, nearA.bottom, markX + 6, nearA.bottom)
      addGuideLine(markX - 6, snapTop, markX + 6, snapTop)
      addGuideLine(markX, snapBottom, markX, nearB.top)
      addGuideLine(markX - 6, snapBottom, markX + 6, snapBottom)
      addGuideLine(markX - 6, nearB.top, markX + 6, nearB.top)
    }
  }

  if (above.length >= 2 && !spacingSnappedY) {
    const a = above[1]; const b = above[0]
    const existingGap = b.top - a.bottom
    const myGap = curTop - b.bottom
    if (existingGap > 2 && Math.abs(myGap - existingGap) < SNAP_THRESHOLD) {
      target.set('top', b.bottom + existingGap)
      spacingSnappedY = true
      const markX = Math.max(a.left, b.left, curLeft) + Math.min(a.right - a.left, b.right - b.left, tw) / 2
      addGuideLine(markX, a.bottom, markX, b.top)
      addGuideLine(markX - 6, a.bottom, markX + 6, a.bottom)
      addGuideLine(markX - 6, b.top, markX + 6, b.top)
      addGuideLine(markX, b.bottom, markX, b.bottom + existingGap)
      addGuideLine(markX - 6, b.bottom, markX + 6, b.bottom)
      addGuideLine(markX - 6, b.bottom + existingGap, markX + 6, b.bottom + existingGap)
    }
  }
  if (below.length >= 2 && !spacingSnappedY) {
    const a = below[0]; const b = below[1]
    const existingGap = b.top - a.bottom
    const myGap = a.top - curBottom
    if (existingGap > 2 && Math.abs(myGap - existingGap) < SNAP_THRESHOLD) {
      target.set('top', a.top - existingGap - th)
      spacingSnappedY = true
      const markX = Math.max(a.left, b.left, curLeft) + Math.min(a.right - a.left, b.right - b.left, tw) / 2
      addGuideLine(markX, a.bottom, markX, b.top)
      addGuideLine(markX - 6, a.bottom, markX + 6, a.bottom)
      addGuideLine(markX - 6, b.top, markX + 6, b.top)
      const snapBottom = a.top - existingGap
      addGuideLine(markX, snapBottom, markX, a.top)
      addGuideLine(markX - 6, snapBottom, markX + 6, snapBottom)
      addGuideLine(markX - 6, a.top, markX + 6, a.top)
    }
  }

  target.setCoords()
  fc.renderAll()
}

function onObjectModified() {
  const fc = getCanvas()
  clearGuides()
  fc?.renderAll()
}

// ---------------------------------------------------------------------------
  return { clearGuides, addGuideLine, onObjectMoving, onObjectModified }
}
