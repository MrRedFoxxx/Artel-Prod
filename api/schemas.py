from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    username: str
    password: str

class UserProgressUpdate(BaseModel):
    lesson_id: int
    is_completed: bool

class AlbumImageBase(BaseModel):
    url: str
    order: int = 0

class AlbumImageCreate(AlbumImageBase):
    pass

class AlbumImage(AlbumImageBase):
    id: int
    album_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class PhotoAlbumBase(BaseModel):
    title: str
    artist: str
    type: str
    preview_url: str
    order: int = 0

class PhotoAlbumCreate(PhotoAlbumBase):
    image_urls: List[str] = []

class PhotoAlbum(PhotoAlbumBase):
    id: int
    created_at: datetime
    images: List[AlbumImage] = []
    
    class Config:
        from_attributes = True

class PhotoAlbumList(BaseModel):
    id: int
    title: str
    artist: str
    type: str
    preview_url: str
    order: int
    created_at: datetime
    images: List[AlbumImage] = []
    
    class Config:
        from_attributes = True