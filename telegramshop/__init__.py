import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices, start_all_bots, stop_all_bots, run_commercial_engine, cleanup_expired_orders
from .views import telegramshop_generic_router
from .views_api import telegramshop_api_router
from .views_api_tma import tma_api_router
from .views_api_tma_admin import tma_admin_api_router

scheduled_tasks: list[asyncio.Task] = []

telegramshop_static_files = [
    {
        "path": "/telegramshop/static",
        "name": "telegramshop_static",
    }
]

telegramshop_ext: APIRouter = APIRouter(
    prefix="/telegramshop", tags=["telegramshop"]
)
telegramshop_ext.include_router(telegramshop_generic_router)
telegramshop_ext.include_router(telegramshop_api_router)
telegramshop_ext.include_router(tma_api_router)
telegramshop_ext.include_router(tma_admin_api_router)


def telegramshop_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)
    asyncio.create_task(stop_all_bots())


def telegramshop_start():
    from lnbits.tasks import create_permanent_unique_task

    task = create_permanent_unique_task(
        "ext_telegramshop", wait_for_paid_invoices
    )
    scheduled_tasks.append(task)
    task2 = create_permanent_unique_task(
        "ext_telegramshop_bots", start_all_bots
    )
    scheduled_tasks.append(task2)
    task3 = create_permanent_unique_task(
        "ext_telegramshop_commercials", run_commercial_engine
    )
    scheduled_tasks.append(task3)
    task4 = create_permanent_unique_task(
        "ext_telegramshop_order_cleanup", cleanup_expired_orders
    )
    scheduled_tasks.append(task4)


__all__ = [
    "db",
    "telegramshop_ext",
    "telegramshop_start",
    "telegramshop_stop",
    "telegramshop_static_files",
]
