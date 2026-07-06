"""主路由"""
from fastapi import APIRouter

from src.api import auth, dashboard, runtime_env, site_branding, sys_config, sys_log, user, video, video_comment, video_taxonomy

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(dashboard.router)
api_router.include_router(video.router)
api_router.include_router(video_comment.router)
api_router.include_router(video_taxonomy.router)
api_router.include_router(site_branding.router)
api_router.include_router(sys_config.router)
api_router.include_router(runtime_env.router)
api_router.include_router(sys_log.router)
