from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import jwt_secret
from app.controllers import admin_controller, member_controller


@asynccontextmanager
async def lifespan(_):
    jwt_secret()  # refuse to start without JWT_SECRET
    yield


app = FastAPI(title="API Key Vault", lifespan=lifespan)
app.include_router(admin_controller.router)
app.include_router(member_controller.router)


@app.get("/health")
def health():
    return {"status": "ok"}
