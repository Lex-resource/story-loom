from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from database import get_db
from services.novel_constants import API_STATUS_OK
from services.system_configs_service import (
    create_prompt_template,
    delete_prompt_template,
    list_pipeline_configs,
    update_pipeline_config,
    list_prompt_templates,
    update_prompt_template,
    list_available_nodes,
)
from services.workflow_admin_service import (
    create_node,
    create_workflow,
    default_graph_json,
    delete_node,
    delete_workflow,
    graph_vocabulary,
    list_nodes,
    update_node,
)

router = APIRouter()


class PipelineConfigUpdate(BaseModel):
    name_zh: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[List[str]] = None
    enable_editor_loop: Optional[bool] = None
    max_rewrite: Optional[int] = None
    enable_force_correction: Optional[bool] = None
    validation_before_editor: Optional[bool] = None
    # 有序阶段列表，每项 {"agent": ..., "role": ...}。语义校验在 service 层，
    # 归一化后回写（补齐必需阶段、剔除依赖不满足的阶段）。
    stages: Optional[List[Dict[str, Any]]] = None
    # 拓扑图：{"entry", "steps": [...], "budgets": {...}}。执行权威，校验最严
    # （环守卫、悬空目标、必需角色与裁决、节点引用一致性）—— 见 services/chapter_graph。
    graph: Optional[Dict[str, Any]] = None
    policy: Optional[Dict[str, Any]] = None
    surface_strategy: Optional[str] = None
    prompt_category: Optional[str] = None


class PipelineConfigCreate(BaseModel):
    name: str
    name_zh: Optional[str] = None
    description: Optional[str] = None
    # 从既有工作流克隆；留空则从零新建（必须指定 prompt_category 复用一套提示词）。
    clone_from: Optional[str] = None
    # copy = 复制一套独立提示词；share = 指向来源的提示词分类。
    prompt_mode: Optional[str] = None
    prompt_category: Optional[str] = None
    surface_strategy: Optional[str] = None


class PromptTemplateUpdate(BaseModel):
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None


class PromptTemplateCreate(BaseModel):
    name: str
    category: str
    name_zh: Optional[str] = None
    type: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None


class WorkflowNodeCreate(BaseModel):
    id: str
    name_zh: str
    role: str
    prompt_name: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


class WorkflowNodeUpdate(BaseModel):
    name_zh: Optional[str] = None
    role: Optional[str] = None
    prompt_name: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# 工作流
# ---------------------------------------------------------------------------

@router.get("/pipeline", response_model=List[Dict[str, Any]])
async def get_all_pipelines(db=Depends(get_db)):
    return await list_pipeline_configs(db)


@router.post("/pipeline")
async def create_pipeline(payload: PipelineConfigCreate, db=Depends(get_db)):
    return await create_workflow(db, payload.model_dump(exclude_unset=True))


@router.put("/pipeline/{name}")
async def update_pipeline(
    name: str, payload: PipelineConfigUpdate, db=Depends(get_db)
):
    await update_pipeline_config(db, name, payload.model_dump(exclude_unset=True))
    return {"status": API_STATUS_OK}


@router.delete("/pipeline/{name}")
async def delete_pipeline(name: str, db=Depends(get_db)):
    return await delete_workflow(db, name)


# ---------------------------------------------------------------------------
# 拓扑词表与默认图
# ---------------------------------------------------------------------------

@router.get("/graph-vocabulary", response_model=Dict[str, Any])
async def get_graph_vocabulary():
    """角色、裁决、特殊目标、预算的词表。

    前端的拓扑编辑器据此渲染，不在前端重写一份 —— 后端加一个角色，界面自动跟上。
    """
    return graph_vocabulary()


@router.get("/default-graph", response_model=Dict[str, Any])
async def get_default_graph(
    has_editor: bool = True,
    has_style_repair: bool = True,
    validation_before_editor: bool = False,
):
    """默认拓扑。前端「重置为默认」用。"""
    return default_graph_json(
        has_editor=has_editor,
        has_style_repair=has_style_repair,
        validation_before_editor=validation_before_editor,
    )


# ---------------------------------------------------------------------------
# 节点库
# ---------------------------------------------------------------------------

@router.get("/nodes", response_model=List[Dict[str, Any]])
async def get_workflow_nodes(db=Depends(get_db)):
    return await list_nodes(db)


@router.post("/nodes")
async def post_workflow_node(payload: WorkflowNodeCreate, db=Depends(get_db)):
    return await create_node(db, payload.model_dump(exclude_unset=True))


@router.put("/nodes/{node_id}")
async def put_workflow_node(
    node_id: str, payload: WorkflowNodeUpdate, db=Depends(get_db)
):
    return await update_node(db, node_id, payload.model_dump(exclude_unset=True))


@router.delete("/nodes/{node_id}")
async def remove_workflow_node(node_id: str, db=Depends(get_db)):
    return await delete_node(db, node_id)


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

@router.get("/prompts", response_model=List[Dict[str, Any]])
async def get_prompts(
    category: Optional[str] = None, db=Depends(get_db)
):
    return await list_prompt_templates(db, category=category)


@router.post("/prompts")
async def post_prompt(payload: PromptTemplateCreate, db=Depends(get_db)):
    return await create_prompt_template(db, payload.model_dump(exclude_unset=True))


@router.put("/prompts/{prompt_id}")
async def update_prompt(
    prompt_id: str, payload: PromptTemplateUpdate, db=Depends(get_db)
):
    await update_prompt_template(
        db, prompt_id, payload.model_dump(exclude_unset=True)
    )
    return {"status": API_STATUS_OK}


@router.delete("/prompts/{prompt_id}")
async def remove_prompt(prompt_id: str, db=Depends(get_db)):
    return await delete_prompt_template(db, prompt_id)


@router.get("/available-nodes", response_model=List[Dict[str, str]])
async def get_available_nodes(db=Depends(get_db)):
    return await list_available_nodes(db)


# ---------------------------------------------------------------------------
# 运行参数(runtime_tunables):元数据 / 当前值 / 修改
# ---------------------------------------------------------------------------

class RuntimeTunablesUpdate(BaseModel):
    values: Dict[str, Any]


@router.get("/runtime-tunables/vocabulary", response_model=List[Dict[str, Any]])
async def get_runtime_tunables_vocabulary():
    """运行参数的元数据(类型/范围/默认/说明/生效时机),按组下发。

    与 graph-vocabulary 同一模式:前端不写死任何参数,后端加参数界面自动跟上。
    """
    from services.runtime_tunables_service import vocabulary

    return vocabulary()


@router.get("/runtime-tunables", response_model=Dict[str, Any])
async def get_runtime_tunables():
    from services.runtime_tunables_service import current_values, ensure_fresh

    await ensure_fresh()
    return {"values": current_values()}


@router.put("/runtime-tunables", response_model=Dict[str, Any])
async def put_runtime_tunables(payload: RuntimeTunablesUpdate):
    """批量修改运行参数。逐项校验(未知 key/类型/范围),全部通过才落库。"""
    from fastapi import HTTPException

    from services.runtime_tunables_service import update_values, validate_value

    # 分项错误拼成带 · 前缀的多行字符串,与 _validate_pipeline_update 的
    # detail 约定一致,前端 asErrorList 直接拆行展示。
    errors: List[str] = []
    for key, value in payload.values.items():
        try:
            validate_value(key, value)
        except ValueError as exc:
            errors.append(f"· {key}: {exc}")
    if errors:
        raise HTTPException(status_code=400, detail="\n".join(errors))
    values = await update_values(payload.values)
    return {"status": API_STATUS_OK, "values": values}
