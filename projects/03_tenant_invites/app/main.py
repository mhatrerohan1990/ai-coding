from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (register tables)
from app.auth import get_secret
from app.db import Base, engine
from app.errors import AlreadyMemberError, InvalidInviteError, InviteUsedError
from app.routers import invites, members

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_secret()  # fail fast if JWT_SECRET is missing
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="gudgeon", lifespan=lifespan)
app.include_router(invites.router)
app.include_router(members.router)


@app.exception_handler(InvalidInviteError)
def invalid_invite_handler(_: Request, __: InvalidInviteError) -> JSONResponse:
    return JSONResponse(
        {"detail": "Invalid or expired invite."}, status_code=status.HTTP_400_BAD_REQUEST
    )


@app.exception_handler(InviteUsedError)
def invite_used_handler(_: Request, __: InviteUsedError) -> JSONResponse:
    return JSONResponse(
        {"detail": "This invite has already been used."}, status_code=status.HTTP_409_CONFLICT
    )


@app.exception_handler(AlreadyMemberError)
def already_member_handler(_: Request, __: AlreadyMemberError) -> JSONResponse:
    return JSONResponse(
        {"detail": "You are already a member of this tenant."},
        status_code=status.HTTP_409_CONFLICT,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
