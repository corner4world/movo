export interface SectionNode {
  id: string;
  title: string;
  mustIncludeText: string;
  avoidText: string;
  notes: string;
  children: SectionNode[];
}

export interface SectionPreviewItem {
  key: string;
  title: string;
  level: number;
  mustInclude: string[];
}

export function createSectionNode(seed: Partial<SectionNode> = {}): SectionNode {
  return {
    id: seed.id || `section_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`,
    title: seed.title || '',
    mustIncludeText: seed.mustIncludeText || '',
    avoidText: seed.avoidText || '',
    notes: seed.notes || '',
    children: Array.isArray(seed.children) ? seed.children : [],
  };
}

export function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  value.forEach((item) => {
    const text = String(item || '').trim();
    if (!text) return;
    const key = text.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(text);
  });
  return out;
}

function splitLegacyBulletLine(value: string): string[] {
  const normalized = String(value || '')
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!normalized) return [];
  const matches = normalized.match(/(?:^|(?:\s+-\s+))[^-][^-]*(?=(?:\s+-\s+)|$)/g);
  if (!matches || matches.length <= 1) {
    return [normalized];
  }
  return matches.map((item) => item.replace(/^\s*-\s*/, '').trim()).filter(Boolean);
}

export function parseMultilineItems(value: unknown): string[] {
  const parts = Array.isArray(value) ? value : [value];
  const out: string[] = [];
  const seen = new Set<string>();
  parts.forEach((part) => {
    const text = String(part || '');
    text
      .split(/\r?\n/)
      .flatMap((line) => splitLegacyBulletLine(line))
      .map((item) => item.replace(/^[\-\u2022\u00b7\s]+/, '').trim())
      .filter(Boolean)
      .forEach((item) => {
        const key = item.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        out.push(item);
      });
  });
  return out;
}

function normalizeSectionNode(value: any): SectionNode | null {
  if (typeof value === 'string') {
    const title = value.trim();
    return title ? createSectionNode({ title }) : null;
  }
  if (!value || typeof value !== 'object') return null;
  const title = String(value.title || value.name || value.heading || '').trim();
  if (!title) return null;
  const mustInclude = parseMultilineItems(value.must_include || value.mustInclude || value.required_elements || value.requiredElements);
  const avoid = parseMultilineItems(value.avoid || value.must_avoid || value.mustAvoid || value.forbidden_elements || value.forbiddenElements);
  const children = Array.isArray(value.children)
    ? value.children.map((item: any) => normalizeSectionNode(item)).filter(Boolean) as SectionNode[]
    : [];
  return createSectionNode({
    title,
    mustIncludeText: mustInclude.join('\n'),
    avoidText: avoid.join('\n'),
    notes: String(value.notes || value.description || '').trim(),
    children,
  });
}

export function hydrateSectionStructure(value: unknown, fallbackSections: unknown = []): SectionNode[] {
  const source = Array.isArray(value) && value.length ? value : fallbackSections;
  if (!Array.isArray(source)) return [];
  return source.map((item) => normalizeSectionNode(item)).filter(Boolean) as SectionNode[];
}

export function serializeSectionStructure(nodes: SectionNode[], level = 1): Array<Record<string, any>> {
  return nodes
    .map((node) => {
      const title = node.title.trim();
      if (!title) return null;
      const item: Record<string, any> = {
        title,
        level,
        must_include: parseMultilineItems(node.mustIncludeText),
        avoid: parseMultilineItems(node.avoidText),
        notes: node.notes.trim(),
        children: serializeSectionStructure(node.children || [], level + 1),
      };
      return item;
    })
    .filter(Boolean) as Array<Record<string, any>>;
}

export function flattenSectionTitles(nodes: SectionNode[]): string[] {
  const out: string[] = [];
  const walk = (items: SectionNode[]) => {
    items.forEach((item) => {
      const title = item.title.trim();
      if (title) out.push(title);
      if (item.children?.length) walk(item.children);
    });
  };
  walk(nodes);
  return out;
}

export function flattenSectionPreview(nodes: SectionNode[]): SectionPreviewItem[] {
  const out: SectionPreviewItem[] = [];
  const walk = (items: SectionNode[], level: number) => {
    items.forEach((item) => {
      const title = item.title.trim();
      if (title) {
        out.push({
          key: `${item.id}_${level}`,
          title,
          level,
          mustInclude: parseMultilineItems(item.mustIncludeText),
        });
      }
      if (item.children?.length) walk(item.children, level + 1);
    });
  };
  walk(nodes, 1);
  return out;
}
