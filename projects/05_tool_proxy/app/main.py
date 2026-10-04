from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.controllers import admin_controller, member_controller
from app.exceptions import BadRequestError, NotFoundError

app = FastAPI()

app.include_router(admin_controller.router)
app.include_router(member_controller.router)


@app.exception_handler(NotFoundError)
def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(BadRequestError)
def bad_request_handler(request: Request, exc: BadRequestError):
    return JSONResponse(status_code=400, content={"detail": exc.message})
