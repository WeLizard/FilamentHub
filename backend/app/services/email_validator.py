"""Email validation utilities for brand verification."""

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Путь к файлу с белым списком личных почтовых доменов
PERSONAL_EMAIL_DOMAINS_FILE = Path(__file__).parent.parent / "core" / "personal_email_domains.txt"

# Путь к файлу с опечатками доменов (формат: опечатка=правильный_домен)
EMAIL_DOMAIN_TYPOS_FILE = Path(__file__).parent.parent / "core" / "email_domain_typos.txt"

# Кэш для списка личных доменов
_personal_email_domains_cache: list[str] | None = None

# Кэш для словаря опечаток
_domain_typos_cache: dict[str, str] | None = None


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
        logger.warning("Failed to load personal email domains file", exc_info=True)
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
        logger.warning("Failed to normalize website URL", exc_info=True)
        return None


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(curr_row[j] + 1, prev_row[j + 1] + 1, prev_row[j] + cost))
        prev_row = curr_row
    return prev_row[-1]


def load_domain_typos() -> dict[str, str]:
    """Load email domain typos from file. Format: typo=correct_domain (one per line)."""
    global _domain_typos_cache

    if _domain_typos_cache is not None:
        return _domain_typos_cache

    typos: dict[str, str] = {}

    if not EMAIL_DOMAIN_TYPOS_FILE.exists():
        logger.warning("Email domain typos file not found: %s", EMAIL_DOMAIN_TYPOS_FILE)
        _domain_typos_cache = typos
        return typos

    try:
        with open(EMAIL_DOMAIN_TYPOS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    typo, correct = line.split("=", 1)
                    typo = typo.strip().lower()
                    correct = correct.strip().lower()
                    if typo and correct:
                        typos[typo] = correct
    except Exception:
        logger.warning("Failed to load email domain typos file", exc_info=True)

    _domain_typos_cache = typos
    return typos


# DNS check timeout (seconds)
_DNS_TIMEOUT = 5.0


async def check_domain_has_mx_or_a(domain: str) -> bool:
    """
    Check if domain has MX or A DNS records (i.e. can receive email).

    Uses dnspython (already installed as email-validator dependency).
    Runs DNS queries in a thread pool to avoid blocking the event loop.
    """
    import asyncio
    import dns.resolver

    def _resolve() -> bool:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = _DNS_TIMEOUT

        # Try MX first
        try:
            answers = resolver.resolve(domain, "MX")
            if answers:
                return True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass
        except Exception:
            pass

        # Fallback to A record (some domains accept mail without MX)
        try:
            answers = resolver.resolve(domain, "A")
            if answers:
                return True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass
        except Exception:
            pass

        return False

    try:
        return await asyncio.to_thread(_resolve)
    except Exception:
        # If DNS check fails entirely (network issue etc.), let the user pass
        logger.warning("DNS check failed for domain %s, allowing registration", domain, exc_info=True)
        return True


def check_email_domain_typo(email: str) -> str | None:
    """
    Check if email domain looks like a typo of a known personal email domain.

    Returns a hint string like "Возможно, вы имели в виду @gmail.com?"
    if the domain is a likely typo, or None if it looks fine.
    """
    if not email or "@" not in email:
        return None

    domain = email.split("@")[1].lower()
    personal_domains = load_personal_email_domains()

    # If the domain is a known personal domain — it's fine
    if domain in personal_domains:
        return None

    # Check known typos from file
    domain_typos = load_domain_typos()
    if domain in domain_typos:
        return f"Возможно, вы имели в виду @{domain_typos[domain]}?"

    # Fuzzy match against known personal domains (Levenshtein ≤ 2)
    for known_domain in personal_domains:
        if _levenshtein(domain, known_domain) <= 2:
            return f"Возможно, вы имели в виду @{known_domain}?"

    # Unknown domain (corporate etc.) — let it pass
    return None


async def validate_email_domain(email: str) -> str | None:
    """
    Full email domain validation: typo check + DNS MX/A check.

    Returns error message string if domain is invalid, None if OK.

    Validation order:
    1. Known domain from personal_email_domains.txt → OK
    2. Hardcoded typo → error with suggestion
    3. Levenshtein match → error with suggestion
    4. DNS MX/A check → error if domain doesn't exist
    """
    if not email or "@" not in email:
        return None

    domain = email.split("@")[1].lower()

    # Known personal domain — skip all checks
    personal_domains = load_personal_email_domains()
    if domain in personal_domains:
        return None

    # Typo check (hardcoded + fuzzy)
    typo_hint = check_email_domain_typo(email)
    if typo_hint:
        return typo_hint

    # DNS MX/A check for unknown domains
    has_mail_records = await check_domain_has_mx_or_a(domain)
    if not has_mail_records:
        return f"Домен @{domain} не существует или не может принимать почту"

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
        logger.warning("Failed to match email domain to website", exc_info=True)
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

