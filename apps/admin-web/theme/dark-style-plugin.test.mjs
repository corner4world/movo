import assert from 'node:assert/strict';
import test from 'node:test';
import postcss from 'postcss';
import { compileStyle } from '@vue/compiler-sfc';

import { adminDarkStyles } from './dark-style-plugin.mjs';

const from = '/workspace/apps/admin-web/src/views/auth/SetupPage.vue';

test('converts light custom surfaces and text while retaining light rules', async () => {
  const source = '.card { background: #fff; color: #17233d; border: 1px solid #e2e8f0; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from });
  assert.match(css, /\.card \{ background: #fff; color: #17233d;/);
  assert.match(css, /html\.dark \.card \{ background: #192333; color: #e7edf7; border: 1px solid #354359;/);
});

test('preserves accent buttons and existing dark variants', async () => {
  const source = '.primary { background: #366aff; color: #fff; } html.dark .primary { background: #2757e6; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from });
  assert.equal((css.match(/html\.dark \.primary/g) ?? []).length, 1);
  assert.match(css, /background: #2757e6/);
});

test('does not rewrite dependency styles', async () => {
  const source = '.card { background: #fff; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from: '/workspace/node_modules/library/style.css' });
  assert.equal(css, source);
});

test('supports Windows source paths and named colors', async () => {
  const source = '.item { background: white; color: black; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from: 'C:\\work\\apps\\admin-web\\src\\SetupPage.vue' });
  assert.match(css, /html\.dark \.item \{ background: #192333; color: #e7edf7;/);
});

test('transforms styles from the Docker build working directory', async () => {
  const source = '.card { background: #fff; color: #17233d; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from: '/app/src/views/dashboard/DashboardPage.vue' });
  assert.match(css, /html\.dark \.card \{ background: #192333; color: #e7edf7;/);
});

test('does not transform another package in a monorepo dependency path', async () => {
  const source = '.card { background: #fff; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from: '/app/node_modules/package/src/card.css' });
  assert.equal(css, source);
});

test('keeps PDF canvas white', async () => {
  const source = '.pdf-page canvas { background: #fff; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from });
  assert.equal(css, source);
});

test('darkens pale translucent surfaces but preserves colored highlights', async () => {
  const source = '.panel { background: rgba(247, 250, 255, .8); } .hero { background: rgba(255,255,255,.12); }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from });
  assert.match(css, /html\.dark \.panel \{ background: rgba\(25, 35, 51, .8\);/);
  assert.doesNotMatch(css, /html\.dark \.hero/);
});

test('converts local Naive UI color overrides in workflow controls', async () => {
  const source = '.button { --n-color: #eef4ff; --n-text-color: #2f60d9; --n-border: 1px solid #b8cdfd; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from: '/app/src/views/skills/SkillConfigPageShell.css' });
  assert.match(css, /html\.dark \.button \{ --n-color: #1e2b3d; --n-text-color: #9ab9ff; --n-border: 1px solid #354359;/);
});

test('keeps leading deep selectors active after Vue scopes the stylesheet', async () => {
  const source = ':deep(.doc-title-link) { color: #17233d; }';
  const { css } = await postcss([adminDarkStyles()]).process(source, { from: '/app/src/views/knowledge/KnowledgeDocumentsPageStyles1.css' });
  const compiled = compileStyle({ source: css, filename: 'KnowledgeDocumentsPage.vue', id: 'data-v-test', scoped: true });
  assert.match(compiled.code, /html\.dark \.doc-title-link\s*\{\s*color: #e7edf7;/);
  assert.doesNotMatch(compiled.code, /html\.dark\[data-v-test\]/);
});
