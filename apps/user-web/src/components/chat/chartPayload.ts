export function parseChartPayload(raw: string): any | null {
  const text = String(raw || '').trim()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    // fallthrough
  }
  const typeMatch = text.match(/^type:\s*([^\n]+)$/m)
  const titleMatch = text.match(/^title:\s*([^\n]+)$/m)
  const baseType = typeMatch ? typeMatch[1].trim() : 'line'
  const baseTitle = titleMatch ? titleMatch[1].trim() : 'Chart'

  const labelsMatch = text.match(/^labels:\s*(\[[^\]]*\])$/m)
  const valuesMatch = text.match(/^values:\s*(\[[^\]]*\])$/m)
  if (labelsMatch && valuesMatch) {
    try {
      return {
        type: baseType,
        title: baseTitle,
        labels: JSON.parse(labelsMatch[1]),
        series: [{ name: 'Series', data: JSON.parse(valuesMatch[1]) }],
      }
    } catch {
      // continue
    }
  }

  const xMatch = text.match(/^x:\s*(\[[^\]]*\])$/m)
  const yMatch = text.match(/^y:\s*(\[[^\]]*\])$/m)
  if (xMatch && yMatch) {
    try {
      return {
        type: baseType,
        title: baseTitle,
        labels: JSON.parse(xMatch[1]),
        series: [{ name: 'Series', data: JSON.parse(yMatch[1]) }],
      }
    } catch {
      // continue
    }
  }

  const dataLabelsMatch = text.match(/labels:\s*(\[[^\]]*\])/)
  const datasetMatches = Array.from(text.matchAll(/-\s*label:\s*([^\n]+)\s*(?:\n|\r\n)\s*data:\s*(\[[^\]]*\])/g))
  if (dataLabelsMatch && datasetMatches.length) {
    try {
      const labels = JSON.parse(dataLabelsMatch[1])
      const series = datasetMatches.map((m) => ({
        name: m[1].trim(),
        data: JSON.parse(m[2]),
      }))
      return { type: baseType, title: baseTitle, labels, series }
    } catch {
      // continue
    }
  }

  const pieMatches = Array.from(text.matchAll(/-\s*label:\s*([^\n]+)\s*(?:\n|\r\n)\s*value:\s*([0-9.]+)/g))
  if (pieMatches.length) {
    const labels = pieMatches.map((m) => m[1].trim())
    const data = pieMatches.map((m) => Number(m[2]))
    return { type: baseType, title: baseTitle, labels, series: [{ name: 'Series', data }] }
  }
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  const obj: any = {}
  let currentKey: string | null = null

  const parseScalar = (val: string): any => {
    const v = val.trim()
    if (!v) return ''
    if (v.startsWith('[') && v.endsWith(']')) {
      try {
        return JSON.parse(v)
      } catch {
        return v
      }
    }
    if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v)
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      return v.slice(1, -1)
    }
    return v
  }

  for (const line of lines) {
    if (line.startsWith('- ') && currentKey) {
      const item = line.slice(2)
      const parts = item.split(':')
      if (parts.length >= 2) {
        const key = parts[0].trim()
        const val = parseScalar(parts.slice(1).join(':'))
        obj[currentKey] = obj[currentKey] || []
        obj[currentKey].push({ label: key, value: val })
      } else {
        obj[currentKey] = obj[currentKey] || []
        obj[currentKey].push(parseScalar(item))
      }
      continue
    }
    const idx = line.indexOf(':')
    if (idx === -1) continue
    const key = line.slice(0, idx).trim()
    const val = line.slice(idx + 1).trim()
    if (!val) {
      currentKey = key
      if (!obj[currentKey]) obj[currentKey] = []
      continue
    }
    currentKey = key
    obj[key] = parseScalar(val)
  }

  const payload: any = { type: obj.type || 'line', title: obj.title || 'Chart' }
  if (Array.isArray(obj.labels) && (Array.isArray(obj.values) || Array.isArray(obj.y))) {
    payload.labels = obj.labels
    payload.series = [
      { name: obj.seriesName || 'Series', data: Array.isArray(obj.values) ? obj.values : obj.y },
    ]
    return payload
  }
  if (Array.isArray(obj.x) && Array.isArray(obj.y)) {
    payload.labels = obj.x
    payload.series = [{ name: obj.seriesName || 'Series', data: obj.y }]
    return payload
  }
  if (Array.isArray(obj.values) && obj.values.length && typeof obj.values[0] === 'object') {
    const labels = obj.values.map((v: any) => v.label)
    const data = obj.values.map((v: any) => v.value)
    payload.labels = labels
    payload.series = [{ name: obj.seriesName || 'Series', data }]
    return payload
  }
  return null
}
