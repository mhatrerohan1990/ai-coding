from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.schemas import CreateGrantRequest, ToolCallResponse
from app.services.admin_service import AdminService

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


def get_admin_service(db: Session = Depends(get_db)) -> AdminService:
    return AdminService(db)


@router.post("/tenants/{tenant_id}/grants", status_code=status.HTTP_204_NO_CONTENT)
def create_grant(
    tenant_id: str,
    request: CreateGrantRequest,
    service: AdminService = Depends(get_admin_service),
):
    service.create_grant(tenant_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tenants/{tenant_id}/tool-calls", response_model=list[ToolCallResponse])
def list_tool_calls(
    tenant_id: str,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    service: AdminService = Depends(get_admin_service),
):
    return service.list_tool_calls(tenant_id, limit, offset)
