export type LocalizedSelectOption = {
  value: string;
  zh: string;
  en: string;
  aliases?: string[];
};

export const publishChannelSuggestions: LocalizedSelectOption[] = [
  { value: 'generic', zh: '通用', en: 'Generic' },
  { value: 'website', zh: '官网', en: 'Website' },
  { value: 'docs', zh: '产品文档', en: 'Docs' },
  { value: 'knowledge_base', zh: '知识库', en: 'Knowledge Base' },
  { value: 'email', zh: '邮件', en: 'Email' },
  { value: 'wechat_official', zh: '微信公众号', en: 'WeChat Official Account' },
  { value: 'zhihu', zh: '知乎', en: 'Zhihu' },
  { value: 'xiaohongshu', zh: '小红书', en: 'Xiaohongshu' },
];

export const contentFormSuggestions: LocalizedSelectOption[] = [
  { value: 'article', zh: '文章', en: 'Article' },
  { value: 'report', zh: '报告', en: 'Report' },
  { value: 'brief', zh: '简报', en: 'Brief' },
  { value: 'memo', zh: '备忘录', en: 'Memo' },
  { value: 'guide', zh: '指南', en: 'Guide' },
  { value: 'faq', zh: '问答', en: 'FAQ' },
  { value: 'presentation_outline', zh: '演示大纲', en: 'Presentation Outline' },
];

export const targetAudienceSuggestions: LocalizedSelectOption[] = [
  { value: 'general_public', zh: '大众读者', en: 'General Public' },
  { value: 'professionals', zh: '专业人士', en: 'Professionals' },
  { value: 'decision_makers', zh: '决策者', en: 'Decision Makers' },
  { value: 'developers', zh: '开发者', en: 'Developers' },
  { value: 'students', zh: '学生', en: 'Students' },
  { value: 'internal_team', zh: '内部团队', en: 'Internal Team' },
];

export const preferredStyleSuggestions: LocalizedSelectOption[] = [
  { value: 'professional', zh: '专业', en: 'Professional' },
  { value: 'formal', zh: '正式', en: 'Formal' },
  { value: 'concise', zh: '简洁', en: 'Concise' },
  { value: 'analytical', zh: '分析型', en: 'Analytical' },
  { value: 'objective', zh: '客观', en: 'Objective' },
  { value: 'authoritative', zh: '权威', en: 'Authoritative' },
  { value: 'practical', zh: '实用', en: 'Practical' },
  { value: 'storytelling', zh: '故事化', en: 'Storytelling' },
];
