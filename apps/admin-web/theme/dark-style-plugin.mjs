import { darkColorValue } from './dark-colors.mjs';

/** Add dark variants next to legacy custom rules; Naive UI handles its own widgets. */
export function adminDarkStyles() {
  return {
    postcssPlugin: 'movo-admin-dark-custom-styles',
    Once(root, { result }) {
      const source = result.opts.from?.replaceAll('\\', '/') ?? '';
      // The Docker build copies admin-web to /app, so its styles live under /app/src.
      if (!/(?:^|\/)src\//.test(source) || source.includes('/node_modules/')) return;
      const rules = [];
      root.walkRules((rule) => rules.push(rule));
      for (const rule of rules) {
        if (rule.parent?.type === 'atrule' && rule.parent.name === 'keyframes') continue;
        if (/\bhtml\.dark\b|\[data-theme\s*=\s*['"]?dark/i.test(rule.selector)) continue;
        if (rule.selector.includes(':root')) continue;
        // The document image itself keeps its original paper color.
        if (rule.selector.includes('.pdf-page canvas')) continue;
        const declarations = [];
        rule.walkDecls((declaration) => {
          const value = darkColorValue(declaration.prop, declaration.value);
          if (value !== declaration.value) declarations.push(declaration.clone({ value }));
        });
        if (!declarations.length) continue;
        const darkRule = rule.clone({ selector: rule.selectors.map((selector) => {
          const deep = selector.match(/^:deep\((.+)\)$/);
          // A leading :deep() has no local anchor. Prefixing it directly makes
          // Vue scope html.dark itself, which can never match the document root.
          return deep ? `:global(html.dark ${deep[1]})` : `html.dark ${selector}`;
        }).join(', ') });
        darkRule.removeAll();
        declarations.forEach((declaration) => darkRule.append(declaration));
        rule.after(darkRule);
      }
    },
  };
}
