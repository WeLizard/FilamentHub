#!/usr/bin/env python3
"""
Скрипт для скачивания книг и ресурсов по 3D-печати.
Использует requests для прямого скачивания PDF файлов.
"""

import os
import requests
from pathlib import Path
from urllib.parse import urlparse

# Базовая директория для сохранения
BASE_DIR = Path(__file__).parent.parent

# Книги для скачивания
BOOKS = [
    {
        "name": "Доступная_3D_печать_для_науки_Канесса",
        "url": "https://studia3d.com/files/3dprintbook.pdf",
        "folder": "books",
        "description": "Доступная 3D печать для науки, образования и устойчивого развития (Канесса, Фонда, Дзеннаро, 2013)"
    },
    {
        "name": "Технологии_и_материалы_3D-печати_УГЛТУ",
        "url": "https://elar.usfeu.ru/bitstream/123456789/6617/1/Shkuro.pdf",
        "folder": "books",
        "description": "Технологии и материалы 3D-печати (Шкуро, Кривоногов, УГЛТУ, 2017)"
    },
    # СПбПУ книга требует авторизации - не скачивается напрямую
    # {
    #     "name": "Инновационные_строительные_материалы_и_3D-принтинг_СПбПУ",
    #     "url": "https://elib.spbstu.ru/dl/5/tr/2023/tr23-10.pdf/en/info",
    #     "folder": "books",
    #     "description": "Инновационные строительные материалы и 3D-принтинг (СПбПУ, 2023)"
    # },
]

def download_file(url: str, filepath: Path, description: str = "") -> bool:
    """Скачать файл по URL и сохранить в указанный путь."""
    try:
        print(f"Скачиваю: {description or url}")
        print(f"  URL: {url}")
        print(f"  Путь: {filepath}")
        
        # Создаём директорию если её нет
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Загружаем файл
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Проверяем Content-Type (должен быть PDF)
        content_type = response.headers.get('Content-Type', '')
        if 'pdf' not in content_type.lower() and not url.endswith('.pdf'):
            print(f"  ⚠️  Предупреждение: Content-Type = {content_type}, может быть не PDF")
        
        # Сохраняем файл
        total_size = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r  Прогресс: {percent:.1f}% ({downloaded // 1024} KB / {total_size // 1024} KB)", end='')
        
        print(f"\n  ✅ Успешно скачано: {filepath.stat().st_size // 1024} KB")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n  ❌ Ошибка при скачивании: {e}")
        return False
    except Exception as e:
        print(f"\n  ❌ Неожиданная ошибка: {e}")
        return False

def main():
    """Основная функция для скачивания всех книг."""
    print("=" * 60)
    print("Скачивание книг и ресурсов по 3D-печати")
    print("=" * 60)
    print()
    
    success_count = 0
    fail_count = 0
    
    for book in BOOKS:
        folder_path = BASE_DIR / book["folder"]
        filepath = folder_path / f"{book['name']}.pdf"
        
        # Пропускаем если файл уже существует
        if filepath.exists():
            print(f"⏭️  Пропускаю (уже существует): {book['name']}")
            print(f"   Путь: {filepath}\n")
            continue
        
        print(f"\n📚 {book['description']}")
        if download_file(book["url"], filepath, book["description"]):
            success_count += 1
        else:
            fail_count += 1
        print()
    
    print("=" * 60)
    print(f"Итого: ✅ {success_count} успешно, ❌ {fail_count} ошибок")
    print("=" * 60)

if __name__ == "__main__":
    main()

