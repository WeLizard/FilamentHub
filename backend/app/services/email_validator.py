"""Email validation utilities for brand verification."""

import re
from pathlib import Path
from urllib.parse import urlparse


# Путь к файлу с белым списком личных почтовых доменов
PERSONAL_EMAIL_DOMAINS_FILE = Path(__file__).parent.parent / "core" / "personal_email_domains.txt"

# Кэш для списка личных доменов
_personal_email_domains_cache: list[str] | None = None


def load_personal_email_domains() -> list[str]:
    """Загрузить список личных почтовых доменов из файла."""
    global _personal_email_domains_cache
    
    if _personal_email_domains_cache is not None:
        return _personal_email_domains_cache
    
    domains: list[str] = []
    
    if not PERSONAL_EMAIL_DOMAINS_FILE.exists():
        # Если файла нет, возвращаем дефолтный список
        return [
            "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
            "yandex.ru", "mail.ru", "icloud.com", "protonmail.com",
        ]
    
    try:
        with open(PERSONAL_EMAIL_DOMAINS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Пропускаем пустые строки и комментарии
                if line and not line.startswith("#"):
                    domains.append(line.lower())
    except Exception:
        # В случае ошибки возвращаем дефолтный список
        return [
            "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
            "yandex.ru", "mail.ru", "icloud.com", "protonmail.com",
        ]
    
    _personal_email_domains_cache = domains
    return domains


def normalize_website_url(website: str) -> str | None:
    """
    Нормализовать URL сайта: убрать http/https/www., оставить только домен.
    
    Args:
        website: URL сайта (может быть с или без протокола)
    
    Returns:
        Нормализованный домен или None если не удалось распарсить
    
    Examples:
        "https://www.thermplast.ru" -> "thermplast.ru"
        "thermplast.ru" -> "thermplast.ru"
        "http://thermplast.ru/" -> "thermplast.ru"
        "lizardtech.ru" -> "lizardtech.ru"
    """
    if not website:
        return None
    
    try:
        # Убираем пробелы
        website = website.strip()
        
        # Если нет протокола, добавляем http:// для парсинга
        if not website.startswith(("http://", "https://")):
            website = f"http://{website}"
        
        parsed = urlparse(website)
        # Сначала пытаемся получить домен из netloc
        domain = parsed.netloc
        
        # Если netloc пустой (например, если пользователь ввел просто домен без протокола),
        # пытаемся получить из path
        if not domain:
            # Убираем первый слеш если есть
            path = parsed.path.lstrip("/")
            if path:
                # Берем первую часть до первого слеша
                domain = path.split("/")[0]
            else:
                # Если и path пустой, возможно это уже просто домен
                # Попробуем взять из исходной строки
                original = website.replace("http://", "").replace("https://", "")
                domain = original.split("/")[0].split("?")[0].split("#")[0]
        
        if not domain:
            return None
        
        # Убираем www. (только если это префикс)
        domain = domain.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        
        # Убираем порт если есть
        if ":" in domain:
            domain = domain.split(":")[0]
        
        # Убираем пути, параметры, якоря если они остались
        domain = domain.split("/")[0].split("?")[0].split("#")[0]
        
        # Проверяем, что это похоже на домен (содержит хотя бы одну точку или это localhost)
        if "." in domain or domain == "localhost":
            return domain if domain else None
        else:
            # Если не похоже на домен, возвращаем None
            return None
    except Exception:
        return None


def is_personal_email(email: str) -> bool:
    """
    Проверить, является ли email личным (из популярных почтовых сервисов).
    
    Args:
        email: Email адрес
    
    Returns:
        True если email личный, False иначе
    """
    if not email or "@" not in email:
        return False
    
    email_domain = email.split("@")[1].lower()
    personal_domains = load_personal_email_domains()
    
    return email_domain in personal_domains


def is_corporate_email(email: str, website: str | None) -> bool:
    """
    Проверить, является ли email корпоративным (домен email совпадает с доменом сайта).
    
    Args:
        email: Email адрес
        website: URL сайта компании
    
    Returns:
        True если email корпоративный, False иначе
    """
    if not email or "@" not in email:
        return False
    
    if not website:
        return False
    
    try:
        email_domain = email.split("@")[1].lower()
        website_domain = normalize_website_url(website)
        
        if not website_domain:
            return False
        
        return email_domain == website_domain
    except Exception:
        return False


def is_email_requiring_documents(email: str, website: str | None) -> bool:
    """
    Определить, требуются ли документы для email.
    
    Документы требуются если:
    - Email личный (из списка популярных почтовых сервисов)
    - ИЛИ email не корпоративный (домен не совпадает с сайтом)
    
    Args:
        email: Email адрес
        website: URL сайта компании
    
    Returns:
        True если требуются документы, False иначе
    """
    if not email:
        return False
    
    # Если это личная почта - всегда требуются документы
    if is_personal_email(email):
        return True
    
    # Если это не корпоративная почта - требуются документы
    if not is_corporate_email(email, website):
        return True
    
    # Иначе не требуются
    return False

