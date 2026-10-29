/** Convert legacy light-only custom CSS to the admin dark palette. */
const HEX = /#[\da-f]{3,8}\b/gi;
const RGB = /rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([\d.]+))?\s*\)/gi;

function channels(hex) {
  const raw = hex.slice(1);
  const value = raw.length === 3 ? [...raw].map((part) => part + part).join('') : raw;
  if (value.length !== 6) return null;
  return [0, 2, 4].map((index) => Number.parseInt(value.slice(index, index + 2), 16));
}

function brightness([red, green, blue]) {
  return (red * 0.2126 + green * 0.7152 + blue * 0.0722) / 255;
}

function darkHex(hex, role) {
  const rgb = channels(hex);
  if (!rgb) return hex;
  const light = brightness(rgb);
  const spread = Math.max(...rgb) - Math.min(...rgb);

  if (role === 'background') {
    if (light < 0.72 || Math.min(...rgb) < 175) return hex;
    if (spread > 75 && light < 0.9) return hex;
    return light > 0.96 ? '#192333' : light > 0.87 ? '#1e2b3d' : '#26364a';
  }
  if (role === 'border') return light > 0.58 ? '#354359' : hex;
  if (light > 0.83) return hex; // White text on primary buttons remains white.
  if (rgb[2] > 100 && spread > 45 && rgb[2] > rgb[0] * 1.25 && rgb[2] > rgb[1] * 1.08) return '#9ab9ff';
  if (rgb[1] > 100 && spread > 45 && rgb[1] > rgb[0] * 1.2 && rgb[1] > rgb[2] * 1.08) return '#75d6ae';
  if (rgb[0] > 100 && spread > 45 && rgb[0] > rgb[1] * 1.25 && rgb[0] > rgb[2] * 1.15) return '#ff9ba8';
  return light < 0.31 ? '#e7edf7' : '#aebdd1';
}

export function darkColorValue(property, value) {
  const name = property.toLowerCase();
  const role = name.startsWith('background') || /^--n-color(?:-|$)/.test(name) ? 'background'
    : name.startsWith('border') || name === 'outline' || /^--n-border(?:-|$)/.test(name) ? 'border'
      : name === 'color' || name.endsWith('-color') || /^--n-text-color(?:-|$)/.test(name) ? 'color' : null;
  if (!role) return value;
  let changed = value.replace(HEX, (hex) => darkHex(hex, role));
  if (role === 'background') {
    changed = changed.replace(/\bwhite\b/gi, '#192333');
    changed = changed.replace(RGB, (match, red, green, blue, alpha) => {
      const channels = [red, green, blue].map(Number);
      // Keep translucent highlights over colored surfaces, such as the setup hero.
      if (Math.min(...channels) < 230 || (alpha !== undefined && Number(alpha) < 0.5)) return match;
      return alpha === undefined ? '#192333' : `rgba(25, 35, 51, ${alpha})`;
    });
  }
  if (role === 'color') changed = changed.replace(/\bblack\b/gi, '#e7edf7');
  return changed;
}
