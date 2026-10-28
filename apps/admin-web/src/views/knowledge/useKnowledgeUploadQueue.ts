import type { Ref } from 'vue';
import { useMessage } from 'naive-ui';
import { t } from '@/composables/i18n';
import { fileQueueKey, getFileRelativePath, isSupportedUploadFile, readDroppedUploadCandidates, type UploadFileCandidate, type UploadQueueItem, type UploadStatus } from './knowledgeUploadFiles';

interface UploadQueueContext {
  uploadQueue: Ref<UploadQueueItem[]>;
  showFloatPanel: Ref<boolean>;
  fileInputRef: Ref<HTMLInputElement | null>;
  uploadDirectoryId: Ref<string>;
  selectedDirKeys: Ref<string[]>;
  uploadVisible: Ref<boolean>;
  uploadDragging: Ref<boolean>;
  uploading: Ref<boolean>;
  message: ReturnType<typeof useMessage>;
}

export function useKnowledgeUploadQueue(context: UploadQueueContext) {
  const { uploadQueue, showFloatPanel, fileInputRef, uploadDirectoryId, selectedDirKeys, uploadVisible, uploadDragging, uploading, message } = context;

function openUpload() {
  uploadQueue.value = [];
  showFloatPanel.value = false;
  if (fileInputRef.value) {
    fileInputRef.value.value = '';
  }
  uploadDirectoryId.value = selectedDirKeys.value[0] || 'root';
  uploadVisible.value = true;
}

function triggerFilePicker() {
  fileInputRef.value?.click();
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  if (!files.length) {
    return;
  }
  appendUploadFiles(files);
  input.value = '';
}

function appendUploadFiles(files: File[]) {
  appendUploadCandidates(files.map((file) => ({
    file,
    relativePath: getFileRelativePath(file),
  })));
}

function appendUploadCandidates(candidates: UploadFileCandidate[]) {
  const validCandidates = candidates.filter((item) => isSupportedUploadFile(item.file));
  const skippedCount = candidates.length - validCandidates.length;
  const queuedFileKeys = new Set(uploadQueue.value.map((item) => fileQueueKey(item.file, item.relativePath)));
  const nextItems = validCandidates
    .filter((item) => !queuedFileKeys.has(fileQueueKey(item.file, item.relativePath)))
    .map((file) => ({
      id: `${fileQueueKey(file.file, file.relativePath)}-${Math.random().toString(16).slice(2)}`,
      file: file.file,
      relativePath: file.relativePath,
      status: 'pending' as UploadStatus,
      progress: 0,
      error: '',
    }));
  if (!nextItems.length) {
    message.info(skippedCount ? t('additional.no_supported_document_types_found') : t('additional.the_selected_file_is_already_in_the_list'));
    return;
  }
  uploadQueue.value = [...uploadQueue.value, ...nextItems];
  if (skippedCount) {
    message.warning(t('additional.skipped_unsupported_files', { count: skippedCount }));
  }
}

function handleUploadDragEnter() {
  uploadDragging.value = true;
}

function handleUploadDragOver() {
  uploadDragging.value = true;
}

function handleUploadDragLeave(event: DragEvent) {
  const current = event.currentTarget as HTMLElement | null;
  const related = event.relatedTarget as Node | null;
  if (!current || !related || !current.contains(related)) {
    uploadDragging.value = false;
  }
}

async function handleUploadDrop(event: DragEvent) {
  uploadDragging.value = false;
  const candidates = await readDroppedUploadCandidates(event.dataTransfer);
  if (!candidates.length) {
    return;
  }
  appendUploadCandidates(candidates);
}

function removeUploadItem(id: string) {
  if (uploading.value) {
    return;
  }
  uploadQueue.value = uploadQueue.value.filter((item) => item.id !== id);
}

function clearUploadQueue() {
  if (uploading.value) {
    return;
  }
  uploadQueue.value = [];
  if (fileInputRef.value) {
    fileInputRef.value.value = '';
  }
}

  return { openUpload, triggerFilePicker, handleFileChange, appendUploadFiles, appendUploadCandidates, handleUploadDragEnter, handleUploadDragOver, handleUploadDragLeave, handleUploadDrop, removeUploadItem, clearUploadQueue };
}
