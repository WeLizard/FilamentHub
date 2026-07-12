"""QR code generation service."""

import base64
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.brand import Brand
from app.models.filament import Filament


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
    # Убеждаемся, что используется HTTPS для внешнего домена
    if base_url.startswith("http://") and "filamenthub.ru" in base_url:
        base_url = base_url.replace("http://", "https://")
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


def save_qr_code_image(
    short_code: str,
    sizes: list[int] | None = None,
    error_correction: str = "L",
) -> dict[str, str]:
    """
    Сохраняет изображения QR-кода на диск в разных размерах.

    Args:
        short_code: Короткий код (например: "FH-001")
        sizes: Список размеров для сохранения (по умолчанию: 300, 600, 1200)
        error_correction: Уровень коррекции ошибок (L, M, Q, H)

    Returns:
        Словарь с путями к сохраненным файлам: {"300": "/qr_codes/FH-001-300.png", ...}
    """
    if sizes is None:
        sizes = [300, 600, 1200]

    # Определяем базовую директорию
    base_path = Path(__file__).parent.parent.parent
    qr_dir = base_path / settings.QR_CODES_DIR
    qr_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = {}

    for size in sizes:
        # Генерируем изображение
        buffer = generate_qr_code_image(short_code, size, error_correction)

        # Сохраняем на диск
        filename = f"{short_code}-{size}.png"
        filepath = qr_dir / filename
        filepath.write_bytes(buffer.getvalue())

        # Сохраняем относительный путь для использования в URL
        saved_paths[str(size)] = f"qr_codes/{filename}"

    return saved_paths


def get_qr_code_path(short_code: str, size: int = 300) -> Path | None:
    """
    Получить путь к сохраненному изображению QR-кода.

    Returns:
        Path к файлу или None если файл не существует
    """
    base_path = Path(__file__).parent.parent.parent
    qr_dir = base_path / settings.QR_CODES_DIR
    filename = f"{short_code}-{size}.png"
    filepath = qr_dir / filename

    if filepath.exists():
        return filepath
    return None


async def ensure_filament_qr_code(filament: Filament, db: AsyncSession) -> bool:
    """Assign a QR short code + label images to a filament that lacks one.

    Idempotent: a no-op if the filament already has a code. Collisions get an
    id-based suffix. Returns True when a code was newly assigned. Shared by
    filament creation (verified brands) and brand-verification backfill.
    """
    if filament.qr_code:
        return False

    short_code = generate_short_code(filament.id)
    if await db.scalar(select(Filament.id).where(Filament.qr_code == short_code)):
        short_code = f"{short_code}-{filament.id % 1000}"

    filament.qr_code = short_code
    # 300px (web), 600px (print), 1200px (high quality) for labels.
    save_qr_code_image(short_code, sizes=[300, 600, 1200])
    return True


async def backfill_brand_qr_codes(brand: Brand, db: AsyncSession) -> int:
    """Assign QR codes to a verified brand's active materials that still lack one.

    Covers materials created before the brand was verified (by users or the brand
    itself). Returns the number of codes assigned. The caller commits.
    """
    if not brand.verified:
        return 0

    result = await db.execute(
        select(Filament).where(
            Filament.brand_id == brand.id,
            Filament.active.is_(True),
            Filament.qr_code.is_(None),
        )
    )
    assigned = 0
    for filament in result.scalars().all():
        if await ensure_filament_qr_code(filament, db):
            assigned += 1
    return assigned

