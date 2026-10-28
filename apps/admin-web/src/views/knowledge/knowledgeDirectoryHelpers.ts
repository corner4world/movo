import type { SelectOption, TreeOption } from 'naive-ui';
import type { KnowledgeDirectoryNode } from '@/api/knowledge-directories';
import { t } from '@/composables/i18n';

export function toTreeOptions(nodes: KnowledgeDirectoryNode[]): TreeOption[] {
  return nodes.map((node) => ({
    key: node.id,
    label: `${node.name} (${node.totalDocumentCount})`,
    rawName: node.name,
    totalDocumentCount: node.totalDocumentCount,
    children: toTreeOptions(node.children || []),
  }));
}

export function flattenDirectoryOptions(nodes: KnowledgeDirectoryNode[], includeRoot: boolean, excludeIds: Set<string> = new Set()): SelectOption[] {
  const result: SelectOption[] = includeRoot ? [{ label: t('legacy.root_folder'), value: 'root' }] : [];
  const dfs = (items: KnowledgeDirectoryNode[], lineage: string[] = []) => {
    for (const item of items) {
      if (excludeIds.has(item.id)) {
        continue;
      }
      const nextLineage = [...lineage, item.name];
      result.push({ label: nextLineage.join(' / '), value: item.id });
      dfs(item.children || [], nextLineage);
    }
  };
  dfs(nodes);
  return result;
}

export function collectDirectoryIds(nodes: KnowledgeDirectoryNode[]): string[] {
  const ids: string[] = [];
  const dfs = (items: KnowledgeDirectoryNode[]) => {
    for (const item of items) {
      ids.push(item.id);
      dfs(item.children || []);
    }
  };
  dfs(nodes);
  return ids;
}

export function findDirectoryById(nodes: KnowledgeDirectoryNode[], id: string): KnowledgeDirectoryNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const sub = findDirectoryById(node.children || [], id);
    if (sub) return sub;
  }
  return null;
}

export function collectDirIds(nodes: KnowledgeDirectoryNode[]): string[] {
  const ids: string[] = [];
  const dfs = (items: KnowledgeDirectoryNode[]) => {
    for (const item of items) {
      ids.push(item.id);
      if (item.children?.length) {
        dfs(item.children);
      }
    }
  };
  dfs(nodes);
  return ids;
}
