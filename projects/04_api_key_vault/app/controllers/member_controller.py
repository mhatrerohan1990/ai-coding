import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.auth import require
from app.db import get_db
from app.services.admin_service import NotFoundError
from app.services.member_service import MemberService

router = APIRouter()


class IntrospectRequest(BaseModel):
    secret: str


def get_service(db: sqlite3.Connection = Depends(get_db)) -> MemberService:
    return MemberService(db)


@router.post("/keys/introspect")
def introspect(body: IntrospectRequest, svc: MemberService = Depends(get_service)):
    try:
        return svc.introspect(body.secret)
    except NotFoundError:
        return Response(status_code=404)  # no body, no message


@router.get("/tenants/{tenant_id}/keys", dependencies=[Depends(require("list", "admin", "member"))])
def list_keys(tenant_id: str, svc: MemberService = Depends(get_service)):
    try:
        return svc.list_keys(tenant_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
