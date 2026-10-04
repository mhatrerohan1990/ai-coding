from fastapi import FastAPI

from app.controllers import admin_controller, member_controller

app = FastAPI(title="API Key Vault")
app.include_router(admin_controller.router)
app.include_router(member_controller.router)


@app.get("/health")
def health():
    return {"status": "ok"}
