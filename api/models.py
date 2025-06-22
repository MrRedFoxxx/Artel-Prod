from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Integer, default=0)  # 0 = False, 1 = True
    date_reg = Column(String)  # Храним как строку в формате DD.MM.YYYY
    progress = relationship("UserProgress", back_populates="user")

class UserProgress(Base):
    __tablename__ = "user_progress"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lesson_id = Column(Integer)  # ID урока (1-12)
    is_completed = Column(Integer, default=0)  # 0 = False, 1 = True
    user = relationship("User", back_populates="progress")

class Video(Base):
    __tablename__ = "video"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    type = Column(String, nullable=False)  # тип видео (Муд-видео, Сниппет и т.д.)
    youtube_url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=False)
    order = Column(Integer, default=0)  # для сортировки видео
    created_at = Column(DateTime, default=datetime.utcnow)

class PhotoAlbum(Base):
    __tablename__ = "photo_albums"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)  # Название альбома
    artist = Column(String, nullable=False)  # Автор/Бренд
    type = Column(String, nullable=False)  # Тип (Кампейн, Каталог, Промо к релизу)
    preview_url = Column(String, nullable=False)  # URL превью изображения
    order = Column(Integer, default=0)  # Для сортировки альбомов
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с изображениями
    images = relationship("AlbumImage", back_populates="album", cascade="all, delete-orphan")

class AlbumImage(Base):
    __tablename__ = "album_images"
    
    id = Column(Integer, primary_key=True, index=True)
    album_id = Column(Integer, ForeignKey("photo_albums.id"), nullable=False)
    url = Column(String, nullable=False)  # URL изображения
    order = Column(Integer, default=0)  # Порядок изображения в альбоме
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с альбомом
    album = relationship("PhotoAlbum", back_populates="images")