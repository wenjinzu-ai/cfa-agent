"""CFA-Agent 技能管理 API"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from src.api.schemas.response import ApiResponse
from src.skills.registry import get_skill_registry

router = APIRouter(prefix="/skills", tags=["skills"])
logger = logging.getLogger("cfa-agent.skills")


@router.get("")
async def list_skills():
    """获取技能列表"""
    try:
        registry = get_skill_registry()
        skills = registry.list_all()
        result = []
        for s in skills:
            result.append({
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "triggers": s.get("triggers", []),
            })
        return ApiResponse(success=True, data=result)
    except Exception as e:
        logger.warning(f"Failed to list skills: {e}")
        return ApiResponse(success=True, data=[])


@router.get("/{skill_name}")
async def get_skill(skill_name: str):
    """获取技能详情"""
    try:
        registry = get_skill_registry()
        skill = registry.get(skill_name)
        if skill is None:
            return ApiResponse(success=False, error=f"Skill '{skill_name}' not found")
        return ApiResponse(success=True, data=skill)
    except Exception as e:
        logger.warning(f"Failed to get skill {skill_name}: {e}")
        return ApiResponse(success=False, error=str(e))