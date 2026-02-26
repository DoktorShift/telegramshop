from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer

telegramshop_generic_router = APIRouter()


def telegramshop_renderer():
    return template_renderer(["telegramshop/templates"])


@telegramshop_generic_router.get(
    "/", response_class=HTMLResponse
)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return telegramshop_renderer().TemplateResponse(
        "telegramshop/index.html",
        {"request": request, "user": user.json()},
    )
