"""
评论 API 端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.repository.comment_repo import comment_repo


router = APIRouter(prefix="/api/comments", tags=["comments"])


class CommentCreate(BaseModel):
    opportunity_id: str
    content: str
    user_name: Optional[str] = "匿名"


class CommentResponse(BaseModel):
    id: int
    opportunity_id: str
    user_name: str
    content: str
    created_at: str


@router.post("/", response_model=CommentResponse)
async def create_comment(comment: CommentCreate):
    """添加评论"""
    if not comment.content.strip():
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    
    comment_id = comment_repo.add_comment(
        opportunity_id=comment.opportunity_id,
        content=comment.content,
        user_name=comment.user_name
    )
    
    return {
        "id": comment_id,
        "opportunity_id": comment.opportunity_id,
        "user_name": comment.user_name,
        "content": comment.content,
        "created_at": "刚刚"
    }


@router.get("/{opportunity_id}", response_model=List[CommentResponse])
async def get_comments(opportunity_id: str):
    """获取商机的所有评论"""
    comments = comment_repo.get_comments(opportunity_id)
    return comments


@router.get("/{opportunity_id}/count")
async def get_comment_count(opportunity_id: str):
    """获取商机评论数"""
    count = comment_repo.get_comment_count(opportunity_id)
    return {"count": count}


@router.delete("/{comment_id}")
async def delete_comment(comment_id: int):
    """删除评论"""
    success = comment_repo.delete_comment(comment_id)
    if not success:
        raise HTTPException(status_code=404, detail="评论不存在")
    return {"message": "删除成功"}
