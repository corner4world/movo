from __future__ import annotations


DEFAULT_SHORTCUT_ENTRIES = [
    ("content.wechat", "content", "内容生成", "微信/小红书", "newspaper", "Create a post suitable for WeChat or Xiaohongshu about {topic}. Give it an engaging title; include a scenario, pain points, and a solution in the body; provide three alternative titles."),
    ("content.report", "content", "内容生成", "报告方案", "document", "Create a report plan about {topic}, covering background, current situation, core problems, root-cause analysis, proposed solutions, and an execution plan."),
    ("content.ppt", "content", "内容生成", "PPT生成", "easel", "Create a presentation outline about {topic} for management. Use no more than 12 slides, each with a title, key points, and visualization suggestions."),
    ("content.image_prd", "content", "内容生成", "图片转PRD", "image", "I will upload product screenshots. Use the interface content to draft a PRD covering page goals, feature descriptions, interaction rules, field definitions, and acceptance criteria."),
    ("content.translate", "content", "内容生成", "文档翻译", "language", "I will upload a document. Translate it into Chinese while preserving its structure, heading hierarchy, tables, and key terminology."),
    ("content.fill_form", "content", "内容生成", "文档填表", "grid", "I will upload a document and a spreadsheet template. Extract information from the document and fill the template; mark missing fields as pending completion."),
    ("external.web", "external", "外部搜索", "联网查资料", "search", "Search the web for the latest public information about {topic}. Summarize sources, core views, key figures, and risks."),
    ("external.industry", "external", "外部搜索", "行业研究", "earth", "Research {industry/topic}, covering market trends, major players, key figures, opportunities, and risks."),
    ("external.competitor", "external", "外部搜索", "竞品分析", "analytics", "Research {competitor/field} and compare positioning, core features, pricing strategy, strengths, weaknesses, and transferable lessons."),
    ("external.policy_news", "external", "外部搜索", "政策/新闻", "shield", "Search for the latest policies or news about {topic}, arrange them as a timeline, and explain potential business effects."),
    ("external.overview", "external", "外部搜索", "资料综述", "albums", "Collect and review public information about {topic}, group it by viewpoint, cite sources, and summarize the conclusions."),
    ("external.fact_check", "external", "外部搜索", "事实核查", "stats", "Verify this claim online: {claim to check}. Provide evidence, confidence, and remaining uncertainties."),
    ("internal.search", "internal", "内部知识", "搜知识库", "qa", "Search the internal knowledge base for {topic}. Organize findings into background, key facts, citable views, and open questions."),
    ("internal.history", "internal", "内部知识", "查历史文档", "files", "Find historical documents about {topic} and organize them by source, main conclusions, and reusable material."),
    ("internal.policy", "internal", "内部知识", "查企业制度", "briefcase", "Find company policies about {topic}. Summarize scope, key requirements, precautions, and implementation advice."),
    ("internal.project", "internal", "内部知识", "查项目资料", "albums", "Search project materials about {project/customer/topic}. Summarize background, progress, issues, and recommended next steps."),
    ("internal.customer", "internal", "内部知识", "查客户资料", "people", "Find information about {customer/customer segment}. Summarize customer background, past communications, needs, and risks."),
    ("internal.training", "internal", "内部知识", "查培训材料", "document", "Find training materials about {topic}. Organize them into a learning outline, key concepts, and practical takeaways."),
    ("systems.sales", "systems", "连接系统", "查销售", "cart", "Query this week's sales by store and category. Summarize revenue, order volume, and conversion rate, and flag unusual changes."),
    ("systems.root_cause", "systems", "连接系统", "找根因", "analytics", "Analyze the main reasons for declining sales using the last 30 days of data. Separate traffic, conversion rate, average order value, inventory, promotions, and pricing factors."),
    ("systems.inventory", "systems", "连接系统", "查库存", "files", "Query current inventory and sales over the last seven days. Identify products at risk of stockout, excess stock, or needing replenishment."),
    ("systems.customer", "systems", "连接系统", "查客户", "people", "Query customer growth, repeat purchases, and churn over the last 30 days, and identify segments needing focused attention."),
    ("systems.daily", "systems", "连接系统", "经营日报", "document", "Generate today's daily operations report covering sales, orders, customers, inventory, exceptions, and recommendations for tomorrow."),
    ("systems.mcp", "systems", "连接系统", "调用MCP", "build", "Use the configured MCP tools to complete this task: {task goal}. First explain which tools you will use, then execute and summarize the results."),
]

CATEGORY_ICON_KEYS = {
    "content": "create",
    "external": "globe",
    "internal": "library",
    "systems": "server",
}


def default_entries() -> list[dict[str, object]]:
    return [
        {
            "id": entry_id,
            "type": "prompt",
            "categoryKey": category_key,
            "categoryLabel": category_label,
            "label": label,
            "iconKey": icon_key,
            "categoryIconKey": CATEGORY_ICON_KEYS.get(category_key, "grid"),
            "iconSvg": "",
            "categoryIconSvg": "",
            "prompt": prompt,
            "resourceId": "",
            "enabled": True,
            "locked": False,
        }
        for entry_id, category_key, category_label, label, icon_key, prompt in DEFAULT_SHORTCUT_ENTRIES
    ]
