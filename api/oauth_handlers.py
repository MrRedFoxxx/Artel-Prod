import httpx
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import models
from oauth_config import (
    YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, YANDEX_TOKEN_URL, YANDEX_USER_INFO_URL
)

logger = logging.getLogger(__name__)

async def handle_yandex_oauth(code: str, db: Session) -> Optional[models.User]:
    """Обрабатывает OAuth авторизацию через Яндекс"""
    try:
        # Получаем access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(YANDEX_TOKEN_URL, data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": YANDEX_CLIENT_ID,
                "client_secret": YANDEX_CLIENT_SECRET
            })
            
            if token_response.status_code != 200:
                logger.error(f"Yandex token error: {token_response.text}")
                return None
                
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                logger.error("Yandex token response missing access_token")
                return None
            
            # Получаем информацию о пользователе
            headers = {"Authorization": f"OAuth {access_token}"}
            user_response = await client.get(YANDEX_USER_INFO_URL, headers=headers)
            
            if user_response.status_code != 200:
                logger.error(f"Yandex user info error: {user_response.text}")
                return None
                
            user_data = user_response.json()
            
            # Проверяем, существует ли пользователь
            existing_user = db.query(models.User).filter(
                models.User.oauth_provider == "yandex",
                models.User.oauth_id == user_data.get("id")
            ).first()
            
            if existing_user:
                return existing_user
            
            # Создаем нового пользователя
            username = f"yandex_{user_data.get('id')}"
            email = user_data.get("default_email")
            
            if email:
                # Проверяем, не занят ли email
                email_user = db.query(models.User).filter(
                    models.User.oauth_email == email
                ).first()
                if email_user:
                    return email_user
            
            new_user = models.User(
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name", ""),
                username=username,
                oauth_provider="yandex",
                oauth_id=user_data.get("id"),
                oauth_email=email,
                is_admin=0,
                date_reg=datetime.now().strftime("%d.%m.%Y")
            )
            
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            return new_user
            
    except Exception as e:
        logger.error(f"Error in Yandex OAuth: {str(e)}")
        return None 