import os
from typing import Optional
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# OAuth настройки для Яндекс
YANDEX_CLIENT_ID = os.getenv("YANDEX_CLIENT_ID", "your_yandex_client_id")
YANDEX_CLIENT_SECRET = os.getenv("YANDEX_CLIENT_SECRET", "your_yandex_client_secret")
YANDEX_REDIRECT_URI = os.getenv("YANDEX_REDIRECT_URI", "http://localhost:8000/auth/yandex/callback")

# URL для OAuth авторизации
YANDEX_AUTH_URL = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"
YANDEX_USER_INFO_URL = "https://login.yandex.ru/info"

def get_yandex_auth_url() -> str:
    """Генерирует URL для авторизации через Яндекс"""
    params = {
        "response_type": "code",
        "client_id": YANDEX_CLIENT_ID,
        "redirect_uri": YANDEX_REDIRECT_URI
    }
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{YANDEX_AUTH_URL}?{query_string}" 