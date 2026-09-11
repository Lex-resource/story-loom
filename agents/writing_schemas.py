import json
from typing import Any, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EditorDimensionScore(BaseModel):
    score: int
    reason: str


class EditorEvaluations(BaseModel):
    plot_progression: EditorDimensionScore
    character_portrayal: EditorDimensionScore
    world_consistency: EditorDimensionScore
    writing_quality: EditorDimensionScore
    logical_coherence: EditorDimensionScore
    chapter_continuity: EditorDimensionScore | None = None
    foreshadowing_payoff: EditorDimensionScore | None = None
    hook_strength: EditorDimensionScore | None = None
    emotional_landing: EditorDimensionScore | None = None


class EditorResearchEvaluations(EditorEvaluations):
    """Seven required dimensions for long-form continuity experiments."""

    chapter_continuity: EditorDimensionScore
    foreshadowing_payoff: EditorDimensionScore


class EditorShortFormEvaluations(EditorEvaluations):
    """Seven required dimensions for the short-story workflow.

    Symmetric to :class:`EditorResearchEvaluations`: five craft dimensions plus
    two workflow-specific ones. Long-form adds cross-chapter dimensions
    (continuity, foreshadowing payoff); short-form adds per-section ones, since
    a three-section story has no cross-chapter drift to police but every section
    must carry a hook and land an emotional beat.

    Declaring them is load-bearing, not decorative: pydantic ignores undeclared
    keys, so without this class a model that correctly emitted ``hook_strength``
    would have it silently dropped before ``quality_summary`` ever saw it.
    """

    hook_strength: EditorDimensionScore
    emotional_landing: EditorDimensionScore


class EditorRawIssue(BaseModel):
    category: str = Field(default="other")
    description: str = Field(default="")
    severity: str = Field(default="medium")


class EditorResponse(BaseModel):
    decision: str = Field(default="revise", description="accept|revise|rewrite/proceed")
    evaluations: EditorEvaluations
    edited_content: str
    rewrite_reason: Optional[str] = None
    rewrite_instructions: Optional[str] = None
    raw_issues: List[EditorRawIssue] = Field(default_factory=list)

    @field_validator("raw_issues", mode="before")
    @classmethod
    def filter_invalid_raw_issues(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [item for item in v if isinstance(item, dict)]
        return v

    @field_validator("rewrite_reason", "rewrite_instructions", mode="before")
    @classmethod
    def coerce_rewrite_text_fields(cls, v: Union[str, list, None]) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, list):
            if not v:
                return ""
            return "\n".join(str(item) for item in v)
        return str(v)


class EditorResearchResponse(EditorResponse):
    """Editor response schema that cannot silently produce five-dimension scores."""

    evaluations: EditorResearchEvaluations


class EditorShortFormResponse(EditorResponse):
    """Short-story editor response: five craft dimensions plus the two per-section ones."""

    evaluations: EditorShortFormEvaluations


class ValidatorIssue(BaseModel):
    category: str = Field(default="consistency")
    error_type: str = Field(default="其他", description="人物特征矛盾|时间线矛盾|物品状态矛盾|地点矛盾|因果颠倒|其他")
    description: str = Field(default="")
    evidence: str = Field(default="", description="引用触发矛盾的具体原文片段")
    conflicts_with: str = Field(default="", description="指向图里具体哪条线哪个事实产生了冲突")
    severity: str = Field(default="warning")
    fix_suggestion: str = Field(default="")


class ValidatorResponse(BaseModel):
    passed: bool
    issues: List[ValidatorIssue] = Field(default_factory=list)

    @field_validator("issues", mode="before")
    @classmethod
    def filter_invalid_issues(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [item for item in v if isinstance(item, dict)]
        return v


class ExtractorChangeCandidates(BaseModel):
    new_facts: List[str] = Field(default_factory=list)
    state_changes: List[str] = Field(default_factory=list)
    foreshadowing_updates: List[str] = Field(default_factory=list)
    plot_thread_updates: List[str] = Field(default_factory=list)
    exclude_from_knowledge: List[str] = Field(default_factory=list)
    risk_notes: List[str] = Field(default_factory=list)

    @field_validator(
        "new_facts",
        "state_changes",
        "foreshadowing_updates",
        "plot_thread_updates",
        "exclude_from_knowledge",
        "risk_notes",
        mode="before",
    )
    @classmethod
    def coerce_candidate_lists(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [str(item) for item in v if item]
        if v:
            return [str(v)]
        return []


class CharacterGraphNode(BaseModel):
    id: str
    label: str
    group: str


class CharacterGraphEdge(BaseModel):
    from_name: str = Field(..., alias="from")
    to: str
    label: str

    model_config = ConfigDict(populate_by_name=True)


class CharacterGraphResponse(BaseModel):
    nodes: List[CharacterGraphNode] = Field(default_factory=list)
    edges: List[CharacterGraphEdge] = Field(default_factory=list)


class PlannerChapterOutlineResponse(BaseModel):
    chapter_index: int
    title: str
    summary: str
    key_events: List[str] = Field(default_factory=list)
    required_events: List[str] = Field(
        default_factory=list,
        description="本章必须执行的可验证动作或场面，不得把未知线索写成已确认结论",
    )
    emotional_arc: str
    related_foreshadowing: List[str] = Field(default_factory=list)
    characters_involved: List[str] = Field(default_factory=list)
    character_goals: List[dict[str, Any]] = Field(
        default_factory=list,
        description="本章涉及角色的章节目标、冲突职责与状态推进",
    )
    narrative_stage: str = Field(default="平稳过渡", description="如: 铺垫, 冲突升级, 高潮, 余波, 平稳过渡等")
    start_state: str = Field(default="", description="本章开始时的关键状态")
    end_state: str = Field(default="", description="本章结束时必须形成的关键状态")
    required_changes: List[str] = Field(default_factory=list)
    forbidden_changes: List[str] = Field(default_factory=list)
    continuity_from_previous: List[str] = Field(default_factory=list)
    new_stage_delta: List[str] = Field(
        default_factory=list,
        description="相对上一章已完成终态，本章必须新增的阶段、入口、关系、位置或风险变化",
    )
    unique_action_ledger: List[Any] = Field(
        default_factory=list,
        description="本章每个设备、查询、验证或进入动作最多执行一次，并记录对应响应与变化",
    )
    primary_action: dict[str, Any] = Field(
        default_factory=dict,
        description="本章唯一核心动作、可观察回应、角色决策及代价/风险",
    )
    character_turn: dict[str, Any] = Field(
        default_factory=dict,
        description="本章角色目标、现实压力、选择依据、个人代价与选择后的状态变化",
    )
    state_changes: List[str] = Field(default_factory=list)
    foreshadowing_actions: List[str] = Field(default_factory=list)
    forbidden_deviations: List[str] = Field(default_factory=list)
    unknown_boundary: List[str] = Field(default_factory=list)
    uncertain_events: List[str] = Field(default_factory=list)
    continuity_contract: dict[str, Any] = Field(default_factory=dict)
    beats: List[Any] = Field(
        default_factory=list,
        description="本章按顺序的场景节拍分解，每个元素可为字符串或 {beat, purpose} 对象",
    )

    @field_validator(
        "key_events",
        "required_events",
        "related_foreshadowing",
        "characters_involved",
        "continuity_from_previous",
        "new_stage_delta",
        "unique_action_ledger",
        "state_changes",
        "foreshadowing_actions",
        "forbidden_deviations",
        "unknown_boundary",
        mode="before",
    )
    @classmethod
    def coerce_string_lists(cls, v: Any) -> Any:
        """Accept providers that serialize a one-item JSON list as a string."""
        return [str(item) for item in _coerce_list(v) if item not in (None, "")]

    @field_validator("character_goals", mode="before")
    @classmethod
    def coerce_character_goals(cls, v: Any) -> Any:
        items = _coerce_list(v)
        return [item if isinstance(item, dict) else {"goal": str(item)} for item in items if item]

    @field_validator("continuity_contract", mode="before")
    @classmethod
    def coerce_continuity_contract(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                return parsed
            if v.strip():
                return {"statement": v.strip()}
        return {}

    @field_validator("required_changes", "forbidden_changes", mode="before")
    @classmethod
    def coerce_optional_change_lists(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [str(item) for item in v if item]
        if v:
            return [str(v)]
        return []

    @field_validator("uncertain_events", mode="before")
    @classmethod
    def coerce_uncertain_events(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [str(item) for item in v if item]
        if v:
            return [str(v)]
        return []

    @field_validator("beats", mode="before")
    @classmethod
    def coerce_beats(cls, v: Any) -> Any:
        return _coerce_list(v)


def _coerce_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            return parsed
        return [value]
    return [value]


class SceneBlockConsolidation(BaseModel):
    """整合模型的场景块压缩输出：只允许一个摘要字段，失败回退确定性来源。"""

    summary: str = Field(default="", description="压缩后的剧情线场景块摘要")
