"""QR code generation service."""

import base64
from io import BytesIO

import qrcode
from PIL import Image

from app.core.config import settings


def generate_short_code(filament_id: int) -> str:
    """
    Генерирует короткий код для QR-кода с динамическим форматом.
    
    Формат зависит от количества материалов:
    - Первые 46,655 материалов: FH-XXX (3 символа base36)
    - Далее: FH-XXX-XXX (6 символов base36, разделенных на 2 группы)
    
    Примеры:
    - ID 1 → FH-001
    - ID 13 → FH-00D
    - ID 700 → FH-0JG
    - ID 12345 → FH-9IX
    - ID 46656 → FH-001-000 (переход на расширенный формат)
    - ID 100000 → FH-002-55S
    
    Использует base36 для кодирования ID материала.
    Максимальное количество материалов: 36^6 ≈ 2.1 миллиарда.
    """
    # Преобразуем ID в base36 (цифры 0-9 и буквы A-Z)
    base36_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    
    if filament_id == 0:
        return "FH-000"
    
    # Преобразуем ID в base36
    result = []
    num = filament_id
    while num > 0:
        result.append(base36_chars[num % 36])
        num //= 36
    
    base36_str = "".join(reversed(result))
    
    # Граница перехода: 36^3 = 46,656
    # Если ID < 46656, используем короткий формат FH-XXX
    if filament_id < 46656:
        # Дополняем нулями слева до 3 символов
        base36_str = base36_str.zfill(3)
        return f"FH-{base36_str}"
    else:
        # Используем расширенный формат FH-XXX-XXX
        # Дополняем нулями слева до 6 символов (2 группы по 3)
        base36_str = base36_str.zfill(6)
        # Разбиваем на группы по 3 символа
        groups = [base36_str[i:i+3] for i in range(0, 6, 3)]
        return f"FH-{'-'.join(groups)}"


def generate_qr_code_image(
    short_code: str,
    size: int = 300,
    error_correction: str = "L",
) -> BytesIO:
    """
    Генерирует изображение QR-кода.
    
    Args:
        short_code: Короткий код (например: "FHUB-ABC123")
        size: Размер изображения в пикселях (300, 600, 1200)
        error_correction: Уровень коррекции ошибок (L, M, Q, H)
    
    Returns:
        BytesIO объект с PNG изображением
    """
    # Формируем URL для QR-кода
    base_url = settings.BASE_URL
    url = f"{base_url}/qr/{short_code}"
    
    # Выбираем уровень коррекции ошибок
    error_level_map = {
        "L": qrcode.constants.ERROR_CORRECT_L,  # ~7% повреждений
        "M": qrcode.constants.ERROR_CORRECT_M,  # ~15% повреждений
        "Q": qrcode.constants.ERROR_CORRECT_Q,  # ~25% повреждений
        "H": qrcode.constants.ERROR_CORRECT_H,  # ~30% повреждений
    }
    error_level = error_level_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_L)
    
    # Создаем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=error_level,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Генерируем изображение
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Масштабируем до нужного размера
    if size != 300:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    
    # Сохраняем в BytesIO
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def generate_qr_code_base64(
    short_code: str,
    size: int = 300,
    error_correction: str = "L",
) -> str:
    """
    Генерирует QR-код и возвращает в формате base64.
    
    Returns:
        Base64 строка для вставки в HTML (data:image/png;base64,...)
    """
    buffer = generate_qr_code_image(short_code, size, error_correction)
    image_data = buffer.getvalue()
    base64_str = base64.b64encode(image_data).decode("utf-8")
    return f"data:image/png;base64,{base64_str}"

