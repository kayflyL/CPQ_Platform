"""API endpoints for solutions (解决方案)。"""
from fastapi import APIRouter, HTTPException
from app.repository.solution_repo import SolutionRepository
from app.services.solution_seed import SCENES

router = APIRouter(prefix="/api/solutions", tags=["solutions"])

_REQUIRED = ("key", "scene_key", "scene", "title")


@router.get("/scenes")
def list_scenes():
    return {"scenes": SCENES}


@router.get("/")
def list_solutions(scene_key: str = None):
    repo = SolutionRepository()
    try:
        return {"solutions": repo.list(scene_key=scene_key)}
    finally:
        repo.close()


@router.get("/{key}")
def get_solution(key: str):
    repo = SolutionRepository()
    try:
        sol = repo.get_by_key(key)
        if not sol:
            raise HTTPException(404, f"Solution {key} not found")
        return sol
    finally:
        repo.close()


@router.post("/")
def create_solution(data: dict):
    for k in _REQUIRED:
        if not data.get(k):
            raise HTTPException(400, f"Missing field: {k}")
    repo = SolutionRepository()
    try:
        existing = repo.get_by_key(data["key"])
        if existing:
            raise HTTPException(400, f"Solution key already exists: {data['key']}")
        return repo.create(data, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.put("/{key}")
def update_solution(key: str, data: dict):
    repo = SolutionRepository()
    try:
        sol = repo.update(key, data, operator=data.get("operator", "system"))
        if not sol:
            raise HTTPException(404, f"Solution {key} not found")
        return sol
    finally:
        repo.close()


@router.delete("/{key}")
def delete_solution(key: str):
    repo = SolutionRepository()
    try:
        if not repo.delete(key):
            raise HTTPException(404, f"Solution {key} not found")
        return {"success": True}
    finally:
        repo.close()