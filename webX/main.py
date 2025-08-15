from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from loguru import logger

from webX.playwright_manager import playwright_manager

from webX.api_router import search_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    try:
        await playwright_manager.start()
        logger.info("playwright started successfully")
    except Exception as e:
        logger.error(f"Failed to start playwright in lifespan: {e}")
        # 不要让应用完全崩溃，让 run_in_page 中的懒加载处理这个问题
    yield
    try:
        await playwright_manager.stop()
    except Exception as e:
        logger.error(f"Error stopping playwright: {e}")


app = FastAPI(lifespan=lifespan, default_response_class=ORJSONResponse)

app.add_middleware(GZipMiddleware, minimum_size=2048)

app.include_router(search_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("webX.main:app", host="0.0.0.0", port=8000, reload=True)
