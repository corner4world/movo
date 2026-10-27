// Exact Chinese and English phrases used for workflow node inference.
export const workflowTextInferenceRules = [
    { type: 'extract_resources', keywords: ['提取资源', '资源提取', '提取图片', '提取链接', '提取url', '提取附件', '图片资源', '内嵌图片'] },
    { type: 'understand_image', keywords: ['图片理解', '图像理解', '多模态', '识图', '图片识别', '图表识别', '截图理解', '视觉理解'] },
    { type: 'read_material', keywords: ['读取', '阅读', '上传', '材料', '文档', '原始', 'word', 'pdf', '附件'] },
    { type: 'extract_info', keywords: ['抽取', '提取', '识别', '字段', '指标', '关键信息', '口径'] },
    { type: 'compute_metric', keywords: ['统计', '计算', '汇总', '求和', '占比', '排序', '排名', '异常', '波动', '总量'] },
    { type: 'data_collect', keywords: ['采集', '抓取', '爬取', '网页链接', '链接', 'url', '正文', '页面内容', 'firecrawl'] },
    { type: 'internal_search', keywords: ['内部', '知识库', '制度', '历史', '过往', '内部口径'] },
    { type: 'external_search', keywords: ['外部', '搜索', '检索', '公开', '新闻', '网页', '行业', '联网'] },
    { type: 'call_tool', keywords: ['mcp', '工具', '接口', '调用', '查询系统', '业务系统', 'api'] },
    { type: 'translate_rewrite', keywords: ['文档翻译', '翻译', '改写', '润色', '压缩', '扩写', '转写', '多语言'] },
    { type: 'fill_table', keywords: ['填表', '制表', '表格', 'excel', 'sheet', '明细表', '模板'] },
    { type: 'export_delivery', keywords: ['导出', '交付', '下载', '归档', 'word', 'pdf', 'ppt', '文件'] },
    { type: 'generate_content', keywords: ['生成', '撰写', '写作', '成稿', '草稿', '报告', '专报', '复盘稿', '内容'] },
  ] as const;
