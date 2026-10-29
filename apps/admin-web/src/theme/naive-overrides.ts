import type { GlobalThemeOverrides } from 'naive-ui';

const baseOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#366AFF',
    primaryColorHover: '#5a84ff',
    primaryColorPressed: '#2757e6',
    borderRadius: '14px',
  },
  Card: { borderRadius: '18px' },
};

const darkTableOverrides: GlobalThemeOverrides['DataTable'] = {
  tdColor: '#192333',
  thColor: '#26364a',
  tdColorHover: '#26364a',
  thColorHover: '#30435b',
  tdColorSorting: '#26364a',
  thColorSorting: '#30435b',
  tdColorStriped: '#1e2b3d',
  borderColor: '#354359',
  tdTextColor: '#e7edf7',
  thTextColor: '#d5e0f0',
  tdColorModal: '#1e2b3d',
  thColorModal: '#26364a',
  tdColorHoverModal: '#30435b',
  thColorHoverModal: '#30435b',
  tdColorStripedModal: '#223147',
  borderColorModal: '#354359',
  tdColorPopover: '#1e2b3d',
  thColorPopover: '#26364a',
  tdColorHoverPopover: '#30435b',
  thColorHoverPopover: '#30435b',
  tdColorStripedPopover: '#223147',
  borderColorPopover: '#354359',
};

export function adminThemeOverrides(mode: 'light' | 'dark'): GlobalThemeOverrides {
  return mode === 'dark'
    ? {
        ...baseOverrides,
        Card: { ...baseOverrides.Card, color: '#192333', colorModal: '#1e2b3d' },
        DataTable: darkTableOverrides,
      }
    : baseOverrides;
}
