from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
from agents.constants import ISSUE_CLASSIFIER_TEMPERATURE, PROMPT_ISSUE_CLASSIFIER_CLASSIFY_ISSUES


class IssueClassifierAgent(AgentBase):
    def __init__(self):
        super().__init__()  # 使用 config 中的模型

    async def classify_issues(self, raw_issues: list[dict], novel_format: str) -> list[dict]:
        if not raw_issues:
            return []

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_ISSUE_CLASSIFIER_CLASSIFY_ISSUES,
            category=novel_format
        )

        issues_text = "\n".join([
            f"- [{i.get('category')}] 第{i.get('chapter_index')}章: {i.get('description')} "
            f"(类型: {i.get('error_type', '未知')}, 证据: {i.get('evidence', '无')}, 冲突项: {i.get('conflicts_with', '无')}, 严重程度: {i.get('severity')})"
            for i in raw_issues
        ])

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(user_tmpl, issues_text=sanitize_untrusted_content(issues_text))

        return await self.call_llm_json(sys_prompt, user_prompt, temperature=ISSUE_CLASSIFIER_TEMPERATURE)
