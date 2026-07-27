from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
from agents.constants import COMMUNITY_SUMMARIZER_TEMPERATURE, PROMPT_COMMUNITY_SUMMARIZER

class CommunitySummarizerAgent(AgentBase):
    def __init__(self):
        super().__init__()

    async def summarize_community(self, community_entities: list[dict], community_edges: list[dict], novel_format: str) -> dict:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_COMMUNITY_SUMMARIZER,
            category=novel_format
        )

        entities_text = "\n".join([f"- {e.get('name')} ({e.get('category')})" for e in community_entities])
        edges_text = "\n".join([f"- {e.get('source')} -[{e.get('label')}]-> {e.get('target', '无')} : {e.get('attributes', '')}" for e in community_edges])

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            entities=sanitize_untrusted_content(entities_text),
            edges=sanitize_untrusted_content(edges_text),
        )

        return await self.call_llm_json(sys_prompt, user_prompt, temperature=COMMUNITY_SUMMARIZER_TEMPERATURE)
