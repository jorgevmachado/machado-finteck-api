import redis.asyncio as redis

from app.core.settings import Settings

settings = Settings()

redis_connection_kwargs = {
    "decode_responses": True,
    "socket_timeout": 1,
    "socket_connect_timeout": 1,
    "health_check_interval": 30,
}

redis_client = (
    redis.from_url(settings.REDIS_URL, **redis_connection_kwargs)
    if settings.REDIS_URL
    else redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        **redis_connection_kwargs,
    )
)
