"""Middleware for maintenance mode."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import status

from app.services.maintenance_service import get_maintenance_mode, get_maintenance_info


class MaintenanceMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки режима технических работ."""
    
    async def dispatch(self, request: Request, call_next):
        """
        Блокирует все запросы кроме:
        - /health
        - /api/v1/admin/maintenance/* (для управления режимом)
        - /api/v1/auth/login (для входа админа)
        """
        # Проверяем режим технических работ
        if get_maintenance_mode():
            # Разрешаем доступ к служебным эндпоинтам
            path = request.url.path
            
            # Разрешенные пути (не блокируются)
            # Админы должны иметь возможность войти и управлять сайтом!
            allowed_paths = [
                "/health",
                "/api/v1/admin",        # Вся админка
                "/api/v1/auth",         # Вся авторизация (login, me, refresh)
                "/api/v1/users/me",     # Проверка текущего пользователя
            ]
            
            # Проверяем, является ли путь разрешенным
            is_allowed = any(path.startswith(allowed) for allowed in allowed_paths)
            
            if not is_allowed:
                # Возвращаем ответ о технических работах
                maintenance_info = get_maintenance_info()
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "detail": "Сайт временно недоступен. Ведутся технические работы.",
                        "message": maintenance_info["message"],
                        "maintenance_mode": True,
                    },
                )
        
        # Продолжаем обработку запроса
        response = await call_next(request)
        return response

