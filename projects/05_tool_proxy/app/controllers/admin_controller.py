from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import CreateGrantRequest
from app.services.admin_service import AdminService

router = APIRouter(tags=["admin"])


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


@router.get("/tenants/{tenant_id}/tool-calls")
def list_tool_calls(tenant_id: str, service: AdminService = Depends(get_admin_service)):
    return service.list_tool_calls(tenant_id)
