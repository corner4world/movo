export type UploadStatus = 'pending' | 'uploading' | 'success' | 'failed';

export interface UploadQueueItem {
  id: string;
  file: File;
  relativePath: string;
  status: UploadStatus;
  progress: number;
  error: string;
}

export interface UploadFileCandidate {
  file: File;
  relativePath: string;
}

export const acceptTypes = '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,.png,.jpg,.jpeg,.webp';
const supportedUploadExtensions = new Set(acceptTypes.split(',').map((item) => item.trim().toLowerCase()));

export function fileQueueKey(file: File, relativePath = '') {
  return `${relativePath || file.name}-${file.size}-${file.lastModified}`;
}

export function getFileRelativePath(file: File) {
  return String((file as File & { webkitRelativePath?: string }).webkitRelativePath || '');
}

export function isSupportedUploadFile(file: File) {
  const index = file.name.lastIndexOf('.');
  if (index < 0) return false;
  return supportedUploadExtensions.has(file.name.slice(index).toLowerCase());
}

export async function readDroppedUploadCandidates(dataTransfer: DataTransfer | null): Promise<UploadFileCandidate[]> {
  if (!dataTransfer) return [];
  const items = Array.from(dataTransfer.items || []);
  const entries = items
    .map((item) => {
      const getter = (item as DataTransferItem & { webkitGetAsEntry?: () => unknown }).webkitGetAsEntry;
      return getter ? getter.call(item) : null;
    })
    .filter(Boolean);
  if (!entries.length) {
    return Array.from(dataTransfer.files || []).map((file) => ({
      file,
      relativePath: getFileRelativePath(file),
    }));
  }
  const results = await Promise.all(entries.map((entry) => readEntryUploadCandidates(entry)));
  return results.flat();
}

function readEntryUploadCandidates(entry: unknown, parentPath = ''): Promise<UploadFileCandidate[]> {
  const item = entry as {
    isFile?: boolean;
    isDirectory?: boolean;
    name?: string;
    file?: (callback: (file: File) => void, errorCallback?: () => void) => void;
    createReader?: () => { readEntries: (callback: (entries: unknown[]) => void, errorCallback?: () => void) => void };
  };
  const entryName = item.name || '';
  const relativePath = parentPath ? `${parentPath}/${entryName}` : entryName;
  if (item.isFile && item.file) {
    return new Promise((resolve) => {
      item.file?.(
        (file) => resolve([{ file, relativePath }]),
        () => resolve([]),
      );
    });
  }
  if (item.isDirectory && item.createReader) {
    const reader = item.createReader();
    return new Promise((resolve) => {
      const entries: unknown[] = [];
      const readBatch = () => {
        reader.readEntries(
          (batch) => {
            if (!batch.length) {
              Promise.all(entries.map((child) => readEntryUploadCandidates(child, relativePath)))
                .then((groups) => resolve(groups.flat()));
              return;
            }
            entries.push(...batch);
            readBatch();
          },
          () => resolve([]),
        );
      };
      readBatch();
    });
  }
  return Promise.resolve([]);
}
