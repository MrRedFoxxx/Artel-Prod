#!/usr/bin/env python3
"""
Скрипт для миграции базы данных с добавлением OAuth полей
"""

import sqlite3
import os

def migrate_database():
    """Добавляет OAuth поля в таблицу users"""
    
    # Путь к базе данных
    db_path = "api/sql_app.db"
    
    if not os.path.exists(db_path):
        print("База данных не найдена. Создайте её сначала.")
        return
    
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем, существуют ли уже OAuth поля
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Добавляем OAuth поля, если их нет
        if 'oauth_provider' not in columns:
            print("Добавляем поле oauth_provider...")
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_provider TEXT")
        
        if 'oauth_id' not in columns:
            print("Добавляем поле oauth_id...")
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_id TEXT")
        
        if 'oauth_email' not in columns:
            print("Добавляем поле oauth_email...")
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_email TEXT")
        
        # Сохраняем изменения
        conn.commit()
        print("Миграция завершена успешно!")
        
    except Exception as e:
        print(f"Ошибка при миграции: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database() 