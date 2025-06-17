from pydantic import BaseModel

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    username: str
    password: str

class UserProgressUpdate(BaseModel):
    lesson_id: int
    is_completed: bool