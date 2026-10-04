import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.auth import Principal, require
from app.db import get_db
from app.services.admin_service import AdminService, ConflictError, NotFoundError

router = APIRouter()


class CreateKeyRequest(BaseModel):
    name: str


def get_service(db: sqlite3.Connection = Depends(get_db)) -> AdminService:
    return AdminService(db)


@router.post("/tenants/{tenant_id}/keys")
def create_key(
    tenant_id: str,
    body: CreateKeyRequest,
    principal: Principal = Depends(require("create", "admin")),
    svc: AdminService = Depends(get_service),
):
    try:
        return svc.create_key(tenant_id, body.name, principal.uid)
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/tenants/{tenant_id}/keys/{key_id}/revoke", status_code=204, dependencies=[Depends(require("revoke", "admin"))])
def revoke_key(tenant_id: str, key_id: str, svc: AdminService = Depends(get_service)):
    try:
        svc.revoke_key(tenant_id, key_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    return Response(status_code=204)


@router.post("/tenants/{tenant_id}/keys/{key_id}/rotate", dependencies=[Depends(require("rotate", "admin"))])
def rotate_key(tenant_id: str, key_id: str, svc: AdminService = Depends(get_service)):
    try:
        return svc.rotate_key(tenant_id, key_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ConflictError as e:
        raise HTTPException(409, str(e))
