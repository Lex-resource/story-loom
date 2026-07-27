from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from database import get_db
from services.novel_constants import API_STATUS_OK
from services.system_configs_service import (
    list_pipeline_configs,
    update_pipeline_config,
    list_prompt_templates,
    update_prompt_template,
    list_available_nodes,
    list_available_docs,
)

router = APIRouter()


class PipelineConfigUpdate(BaseModel):
    name_zh: Optional[str] = None
    nodes: Optional[List[str]] = None
    enable_living_docs_update: Optional[bool] = None
    enable_editor_loop: Optional[bool] = None
    max_rewrite: Optional[int] = None
    readonly_docs: Optional[List[str]] = None
    required_docs: Optional[List[str]] = None
    enable_force_correction: Optional[bool] = None
    validation_before_editor: Optional[bool] = None


class PromptTemplateUpdate(BaseModel):
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None


@router.get("/pipeline", response_model=List[Dict[str, Any]])
async def get_all_pipelines(db=Depends(get_db)):
    return await list_pipeline_configs(db)


@router.put("/pipeline/{name}")
async def update_pipeline(
    name: str, payload: PipelineConfigUpdate, db=Depends(get_db)
):
    await update_pipeline_config(db, name, payload.model_dump(exclude_unset=True))
    return {"status": API_STATUS_OK}


@router.get("/prompts", response_model=List[Dict[str, Any]])
async def get_prompts(
    category: Optional[str] = None, db=Depends(get_db)
):
    return await list_prompt_templates(db, category=category)


@router.put("/prompts/{prompt_id}")
async def update_prompt(
    prompt_id: str, payload: PromptTemplateUpdate, db=Depends(get_db)
):
    await update_prompt_template(
        db, prompt_id, payload.model_dump(exclude_unset=True)
    )
    return {"status": API_STATUS_OK}


@router.get("/available-nodes", response_model=List[Dict[str, str]])
async def get_available_nodes(db=Depends(get_db)):
    return await list_available_nodes(db)


@router.get("/available-docs", response_model=List[Dict[str, str]])
async def get_available_docs(db=Depends(get_db)):
    return await list_available_docs(db)
