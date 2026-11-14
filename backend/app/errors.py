"""Error contract from docs/api.md: {"error":{"code","message","retryable","requestId"}}."""
import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status, code, message, retryable=False, headers=None, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.headers = headers or {}
        self.details = details


def _body(code, message, retryable=False, details=None):
    err = {"code": code, "message": message, "retryable": retryable, "requestId": uuid.uuid4().hex}
    if details is not None:
        err["details"] = details
    return {"error": err}


def install(app):
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(_body(exc.code, exc.message, exc.retryable, exc.details), status_code=exc.status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()][:10]
        return JSONResponse(_body("INVALID_INPUT", "Some fields are missing or invalid.", False, details), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        codes = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return JSONResponse(_body(codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail)), status_code=exc.status_code)
