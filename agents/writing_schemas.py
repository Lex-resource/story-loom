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
    emotional_arc: str
    related_foreshadowing: List[str] = Field(default_factory=list)
    characters_involved: List[str] = Field(default_factory=list)
    narrative_stage: str = Field(default="平稳过渡", description="如: 铺垫, 冲突升级, 高潮, 余波, 平稳过渡等")
    start_state: str = Field(default="", description="本章开始时的关键状态")
    end_state: str = Field(default="", description="本章结束时必须形成的关键状态")
    required_changes: List[str] = Field(default_factory=list)
    forbidden_changes: List[str] = Field(default_factory=list)
    beats: List[Any] = Field(
        default_factory=list,
        description="本章按顺序的场景节拍分解，每个元素可为字符串或 {beat, purpose} 对象",
    )

    @field_validator("required_changes", "forbidden_changes", mode="before")
    @classmethod
    def coerce_optional_change_lists(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [str(item) for item in v if item]
        if v:
            return [str(v)]
        return []

    @field_validator("beats", mode="before")
    @classmethod
    def coerce_beats(cls, v: Any) -> Any:
        if isinstance(v, list):
            return v
        if v:
            return [v]
        return []
