from fastapi import FastAPI, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
import models
import schemas
from database import engine, SessionLocal, get_db
import logging
import re
import os
import shutil
from sqlalchemy import func

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация FastAPI
app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Настройка CORS с более строгими параметрами
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)

# Middleware для обработки ошибок
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

# Настройки JWT
SECRET_KEY = "5f4dcc3b5aa765d61d8327deb882cf99b0b1a6d8a1e2b3c4d5e6f7a8b9c0d1e2"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Настройка хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Создаем таблицы в БД (если их нет)
models.Base.metadata.create_all(bind=engine)

# --- Pydantic-схемы ---
class UserCreate(BaseModel):
    first_name: str
    last_name: str
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserProgressUpdate(BaseModel):
    lesson_id: int
    is_completed: bool

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int

# --- Вспомогательные функции ---
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверные учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# Добавляем функцию проверки прав администратора
async def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if not current_user.is_admin:  # Проверяем на 0/1
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для доступа"
        )
    return current_user

# --- Роуты API ---
@app.post("/register/", response_model=Token)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    # Проверяем, не занят ли логин
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Логин уже занят")
    
    # Создаем пользователя
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        hashed_password=hashed_password,
        is_admin=0  # Явно указываем, что это не админ
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Создаем токен для автоматического входа
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": db_user.id
    }

@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id
    }

@app.post("/progress/")
async def update_progress(
    progress: UserProgressUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Обновляем или создаем запись о прогрессе
        db_progress = db.query(models.UserProgress).filter(
            models.UserProgress.user_id == current_user.id,
            models.UserProgress.lesson_id == progress.lesson_id
        ).first()

        if db_progress:
            db_progress.is_completed = progress.is_completed
        else:
            db_progress = models.UserProgress(
                user_id=current_user.id,
                lesson_id=progress.lesson_id,
                is_completed=progress.is_completed
            )
            db.add(db_progress)
        
        db.commit()
        return {"status": "Прогресс обновлен"}
    except Exception as e:
        logger.error(f"Error updating progress: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Ошибка при обновлении прогресса"
        )

@app.get("/progress/")
async def get_user_progress(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        progress = db.query(models.UserProgress).filter(
            models.UserProgress.user_id == current_user.id
        ).all()
        return {"progress": progress}
    except Exception as e:
        logger.error(f"Error getting progress: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Ошибка при получении прогресса"
        )

@app.get("/users/me/")
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "is_admin": current_user.is_admin  # Возвращаем числовое значение
    }

@app.get("/admin/users/")
async def get_users(current_user: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    try:
        # Получаем всех пользователей
        users = db.query(models.User).all()
        
        # Преобразуем в список словарей
        result = []
        for user in users:
            # Вычисляем прогресс
            total_lessons = 12  # Фиксированное количество уроков
            completed_lessons = db.query(models.UserProgress).filter(
                models.UserProgress.user_id == user.id,
                models.UserProgress.is_completed == True
            ).count()
            
            progress = int((completed_lessons / total_lessons * 100) if total_lessons > 0 else 0)
            
            # Форматируем дату регистрации
            date_reg = user.date_reg
            if isinstance(date_reg, str):
                try:
                    # Если дата в формате DD.MM.YYYY, оставляем как есть
                    if re.match(r'\d{2}\.\d{2}\.\d{4}', date_reg):
                        pass
                    else:
                        # Пробуем другие форматы
                        date_obj = datetime.strptime(date_reg, "%Y-%m-%d")
                        date_reg = date_obj.strftime("%d.%m.%Y")
                except Exception as e:
                    logger.error(f"Ошибка форматирования даты: {str(e)}")
                    date_reg = "Не указана"
            
            user_dict = {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "progress": progress,
                "date_reg": date_reg,
                "is_admin": bool(user.is_admin)  # Преобразуем в булево значение
            }
            
            # Отладочный вывод
            logger.info(f"Пользователь {user.username}: is_admin = {user.is_admin}, type = {type(user.is_admin)}")
            
            result.append(user_dict)
        
        return {"users": result}
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Добавляем эндпоинт для создания администратора
@app.post("/admin/create/")
async def create_admin(
    user: UserCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    try:
        # Проверяем, не занят ли логин
        if db.query(models.User).filter(models.User.username == user.username).first():
            raise HTTPException(status_code=400, detail="Логин уже занят")
        
        # Создаем пользователя с правами администратора
        hashed_password = get_password_hash(user.password)
        db_user = models.User(
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            hashed_password=hashed_password,
            is_admin=1  # Устанавливаем 1 вместо True
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        return {"status": "Администратор успешно создан"}
    except Exception as e:
        logger.error(f"Error creating admin: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Ошибка при создании администратора"
        )

@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение информации о пользователе"""
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        return {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_admin": user.is_admin
        }
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Обновление информации о пользователе"""
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Проверяем, не занят ли username другим пользователем
        if user_data.username != user.username:
            existing_user = db.query(models.User).filter(models.User.username == user_data.username).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")
        
        # Обновляем данные пользователя
        user.username = user_data.username
        user.first_name = user_data.first_name
        user.last_name = user_data.last_name
        
        # Обновляем пароль только если он указан
        if user_data.password:
            user.hashed_password = get_password_hash(user_data.password)
        
        db.commit()
        return {"message": "Пользователь успешно обновлен"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обновлении пользователя: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Удаление пользователя"""
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Нельзя удалить самого себя
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Нельзя удалить свой аккаунт")
        
        db.delete(user)
        db.commit()
        return {"message": "Пользователь успешно удален"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: int,
    admin_data: dict,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    try:
        # Получаем пользователя
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Нельзя изменить права самому себе
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Нельзя изменить свои права администратора")
        
        # Обновляем права администратора
        user.is_admin = admin_data.get("is_admin", False)
        db.commit()
        
        return {"message": "Права администратора успешно обновлены"}
    except Exception as e:
        logger.error(f"Ошибка при изменении прав администратора: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при изменении прав администратора")

@app.get("/admin/stats/")
async def get_stats(current_user: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    try:
        # Общее количество пользователей
        total_users = db.query(models.User).count()
        
        # Количество администраторов
        admin_count = db.query(models.User).filter(models.User.is_admin == True).count()
        
        # Количество обычных пользователей
        regular_users = total_users - admin_count
        
        # Средний прогресс по всем пользователям
        avg_progress = db.query(
            func.avg(models.User.progress)
        ).scalar() or 0
        
        return {
            "total_users": total_users,
            "admin_count": admin_count,
            "regular_users": regular_users,
            "avg_progress": round(float(avg_progress), 1)
        }
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/videos/{video_id}")
async def get_video(video_id: int, current_user: models.User = Depends(get_current_user)):
    try:
        db = SessionLocal()
        video = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {
            "id": video.id,
            "title": video.title,
            "artist": video.artist,
            "type": video.type,
            "youtube_url": video.youtube_url,
            "thumbnail_url": video.thumbnail_url,
            "order": video.order
        }
    except Exception as e:
        print(f"Error getting video: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()

@app.get("/videos/")
async def get_videos():
    try:
        db = SessionLocal()
        videos = db.query(models.Video).order_by(models.Video.order).all()
        return {"videos": [
            {
                "id": video.id,
                "title": video.title,
                "artist": video.artist,
                "type": video.type,
                "youtube_url": video.youtube_url,
                "thumbnail_url": video.thumbnail_url,
                "order": video.order
            } for video in videos
        ]}
    except Exception as e:
        print(f"Error getting videos: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()

# --- API для фотоальбомов ---
@app.get("/photo-albums/", response_model=List[schemas.PhotoAlbumList])
async def get_photo_albums(
    limit: int = 10, 
    offset: int = 0, 
    db: Session = Depends(get_db)
):
    """Получение списка фотоальбомов с пагинацией"""
    try:
        albums = db.query(models.PhotoAlbum).order_by(models.PhotoAlbum.order).offset(offset).limit(limit).all()
        return albums
    except Exception as e:
        logger.error(f"Ошибка при получении фотоальбомов: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при получении фотоальбомов")

@app.get("/photo-albums/count/")
async def get_photo_albums_count(db: Session = Depends(get_db)):
    """Получение общего количества фотоальбомов"""
    try:
        count = db.query(models.PhotoAlbum).count()
        return {"total": count}
    except Exception as e:
        logger.error(f"Ошибка при получении количества альбомов: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при получении количества альбомов")

@app.get("/photo-albums/{album_id}", response_model=schemas.PhotoAlbum)
async def get_photo_album(album_id: int, db: Session = Depends(get_db)):
    """Получение конкретного фотоальбома с изображениями"""
    try:
        album = db.query(models.PhotoAlbum).filter(models.PhotoAlbum.id == album_id).first()
        if not album:
            raise HTTPException(status_code=404, detail="Фотоальбом не найден")
        return album
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении фотоальбома: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при получении фотоальбома")

@app.post("/photo-albums/", response_model=schemas.PhotoAlbum)
async def create_photo_album(
    album: schemas.PhotoAlbumCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Создание нового фотоальбома (только для администраторов)"""
    try:
        db_album = models.PhotoAlbum(
            title=album.title,
            artist=album.artist,
            type=album.type,
            preview_url=album.preview_url,
            order=album.order
        )
        db.add(db_album)
        db.commit()
        db.refresh(db_album)
        
        # Добавляем изображения
        for i, image_url in enumerate(album.image_urls):
            db_image = models.AlbumImage(
                album_id=db_album.id,
                url=image_url,
                order=i
            )
            db.add(db_image)
        
        db.commit()
        db.refresh(db_album)
        return db_album
    except Exception as e:
        logger.error(f"Ошибка при создании фотоальбома: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка при создании фотоальбома")

@app.put("/photo-albums/{album_id}", response_model=schemas.PhotoAlbum)
async def update_photo_album(
    album_id: int,
    album: schemas.PhotoAlbumCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Обновление фотоальбома (только для администраторов)"""
    try:
        db_album = db.query(models.PhotoAlbum).filter(models.PhotoAlbum.id == album_id).first()
        if not db_album:
            raise HTTPException(status_code=404, detail="Фотоальбом не найден")
        
        # Обновляем данные альбома
        db_album.title = album.title
        db_album.artist = album.artist
        db_album.type = album.type
        db_album.preview_url = album.preview_url
        db_album.order = album.order
        
        # Удаляем старые изображения
        db.query(models.AlbumImage).filter(models.AlbumImage.album_id == album_id).delete()
        
        # Добавляем новые изображения
        for i, image_url in enumerate(album.image_urls):
            db_image = models.AlbumImage(
                album_id=album_id,
                url=image_url,
                order=i
            )
            db.add(db_image)
        
        db.commit()
        db.refresh(db_album)
        return db_album
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обновлении фотоальбома: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка при обновлении фотоальбома")

@app.delete("/photo-albums/{album_id}")
async def delete_photo_album(
    album_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Удаление фотоальбома (только для администраторов)"""
    try:
        db_album = db.query(models.PhotoAlbum).filter(models.PhotoAlbum.id == album_id).first()
        if not db_album:
            raise HTTPException(status_code=404, detail="Фотоальбом не найден")
        
        db.delete(db_album)
        db.commit()
        return {"message": "Фотоальбом успешно удален"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении фотоальбома: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка при удалении фотоальбома")

# --- Эндпоинты для загрузки файлов ---
@app.post("/upload-preview/")
async def upload_preview(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_admin)
):
    """Загрузка превью изображения для фотоальбома"""
    try:
        # Проверяем тип файла
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")
        
        # Создаем папку для загрузок, если её нет
        upload_dir = os.path.join(BASE_DIR, "static", "uploads", "previews")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Генерируем уникальное имя файла
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{current_user.id}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Возвращаем URL для доступа к файлу
        file_url = f"/static/uploads/previews/{unique_filename}"
        
        return {"url": file_url, "filename": unique_filename}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при загрузке превью: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при загрузке файла")

@app.post("/upload-image/")
async def upload_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_admin)
):
    """Загрузка изображения для фотоальбома"""
    try:
        # Проверяем тип файла
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")
        
        # Создаем папку для загрузок, если её нет
        upload_dir = os.path.join(BASE_DIR, "static", "uploads", "images")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Генерируем уникальное имя файла
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{current_user.id}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Возвращаем URL для доступа к файлу
        file_url = f"/static/uploads/images/{unique_filename}"
        
        return {"url": file_url, "filename": unique_filename}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при загрузке изображения: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при загрузке файла")

@app.post("/upload-thumbnail/")
async def upload_thumbnail(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_admin)
):
    """Загрузка превью для видео"""
    try:
        # Проверяем тип файла
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")
        
        # Создаем папку для загрузок, если её нет
        upload_dir = os.path.join(BASE_DIR, "static", "uploads", "thumbnails")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Генерируем уникальное имя файла
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"thumbnail_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{current_user.id}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Возвращаем URL для доступа к файлу
        file_url = f"/static/uploads/thumbnails/{unique_filename}"
        
        return {"url": file_url, "filename": unique_filename}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при загрузке превью: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при загрузке файла")

app.mount("/", StaticFiles(directory=TEMPLATES_DIR, html=True), name="static")
# Запуск сервера
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1)