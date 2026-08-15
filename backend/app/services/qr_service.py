"""QR code generation service."""

import base64
from io import BytesIO
from pathlib import Path

import qrcode
import qrcode.image.svg
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.brand import Brand
from app.models.filament import Filament
from app.services.qr_mark import (
    MARK_COLOR,
    MARK_COLOR_HEX,
    MARK_VIEWBOX,
    draw_mark,
    mark_paths,
)

# Доля ширины кода под знак. Выбрана замером декодером, а не по площади.
BRANDED_MARK_SHARE = 0.22


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


def _qr_target_url(short_code: str) -> str:
    base_url = settings.BASE_URL
    # Убеждаемся, что используется HTTPS для внешнего домена
    if base_url.startswith("http://") and "filamenthub.ru" in base_url:
        base_url = base_url.replace("http://", "https://")
    return f"{base_url}/qr/{short_code}"


def _qr_for(url: str, error_correction: str, box_size: int) -> qrcode.QRCode:
    error_level_map = {
        "L": qrcode.constants.ERROR_CORRECT_L,  # ~7% повреждений
        "M": qrcode.constants.ERROR_CORRECT_M,  # ~15% повреждений
        "Q": qrcode.constants.ERROR_CORRECT_Q,  # ~25% повреждений
        "H": qrcode.constants.ERROR_CORRECT_H,  # ~30% повреждений
    }
    qr = qrcode.QRCode(
        version=1,
        error_correction=error_level_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M),
        box_size=box_size,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr


def generate_qr_code_image(
    short_code: str,
    size: int = 300,
    error_correction: str = "M",
) -> BytesIO:
    """
    Генерирует изображение QR-кода.

    Args:
        short_code: Короткий код (например: "FHUB-ABC123")
        size: Размер изображения в пикселях (300, 600, 1200)
        error_correction: Уровень коррекции ошибок (L, M, Q, H).
            M — замеренный оптимум для печати без логотипа: столько же модулей,
            что и L, вдвое больший запас на повреждения и читается с меньшего
            размера. H оправдан только когда часть кода закрыта знаком: он
            добавляет модули, и на мелкой наклейке код читается хуже.

    Returns:
        BytesIO объект с PNG изображением
    """
    url = _qr_target_url(short_code)

    # Модуль кода должен быть целым числом пикселей: при дробном масштабе одни
    # модули выходят на пиксель шире других, и на мелкой печати это стоит
    # читаемости. Поэтому размер подбирается вниз, а остаток добирается белым
    # полем — тихая зона от этого только растёт, что безопасно.
    measured = _qr_for(url, error_correction, box_size=1)
    modules = measured.modules_count + 2 * measured.border
    box_size = max(1, size // modules)

    qr = _qr_for(url, error_correction, box_size=box_size)
    img = qr.make_image(fill_color="black", back_color="white").convert("1")

    if img.size[0] != size:
        canvas = Image.new("1", (size, size), 1)
        offset = (size - img.size[0]) // 2
        canvas.paste(img, (offset, offset))
        img = canvas

    # Сохраняем в BytesIO
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _branded_layout(short_code: str, mark_share: float) -> tuple[list[list[bool]], int, int]:
    """Раскладка брендированного кода: матрица и окно под знак в модулях.

    Считается один раз для обоих форматов: растр для экрана и вектор для
    типографии обязаны совпадать модуль в модуль, иначе бренд получит две
    разные картинки одного кода.

    Уровень `H` здесь обязателен — часть кода закрыта, и эту потерю оплачивает
    избыточность. Доля 22% выбрана замером декодером на всех предлагаемых
    размерах, а не расчётом по площади: коррекция работает по кодовым словам,
    а не по проценту картинки.
    """
    qr = _qr_for(_qr_target_url(short_code), "H", box_size=1)
    matrix = qr.get_matrix()

    # Окно той же чётности, что и сетка: иначе знак встанет на полмодуля мимо
    # центра и края окна будут рваными.
    window = max(1, round(qr.modules_count * mark_share))
    if window % 2 != qr.modules_count % 2:
        window += 1
    low = (len(matrix) - window) // 2
    return matrix, window, low


def generate_branded_qr_code_image(
    short_code: str,
    size: int = 1200,
    mark_share: float = BRANDED_MARK_SHARE,
) -> BytesIO:
    """Тот же код со знаком FilamentHub в середине.

    Знак не кладётся поверх готового кода: окно под него выравнивается по
    модульной сетке, и модули там просто не рисуются. Поэтому нет ни белой
    заплаты, ни срезанных наполовину модулей, а знак читается как часть кода.

    Брендированный вариант предлагается бренду вторым, а не подменяет обычный:
    это наш знак на чужой упаковке.
    """
    matrix, window, low = _branded_layout(short_code, mark_share)
    total = len(matrix)
    high = low + window

    box_size = max(1, size // total)
    side = box_size * total
    image = Image.new("RGB", (side, side), "white")
    draw = ImageDraw.Draw(image)

    for row_index, row in enumerate(matrix):
        for column_index, is_dark in enumerate(row):
            if not is_dark:
                continue
            if low <= row_index < high and low <= column_index < high:
                continue
            x = column_index * box_size
            y = row_index * box_size
            draw.rectangle([x, y, x + box_size - 1, y + box_size - 1], fill=MARK_COLOR)

    mark_px = window * box_size
    mark = draw_mark(mark_px)
    image.paste(mark, ((side - mark_px) // 2, (side - mark_px) // 2), mark)

    if side != size:
        canvas = Image.new("RGB", (size, size), "white")
        offset = (size - side) // 2
        canvas.paste(image, (offset, offset))
        image = canvas

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def generate_branded_qr_code_svg(
    short_code: str,
    mark_share: float = BRANDED_MARK_SHARE,
) -> BytesIO:
    """Брендированный код в векторе — то, что уходит в типографию.

    Модули и знак идут контурами в одной системе координат, где единица — это
    модуль. Растровой вставки внутри нет: печать на упаковке масштабируется без
    потери края.
    """
    matrix, window, low = _branded_layout(short_code, mark_share)
    total = len(matrix)
    high = low + window

    modules = [
        f"M{column_index},{row_index}h1v1h-1z"
        for row_index, row in enumerate(matrix)
        for column_index, is_dark in enumerate(row)
        if is_dark and not (low <= row_index < high and low <= column_index < high)
    ]

    # Знак живёт в поле 20×20, окно — window модулей: масштабируем и сдвигаем.
    scale = window / MARK_VIEWBOX
    mark = (
        f'<g transform="translate({low},{low}) scale({scale:.6f})">'
        + "".join(f'<path d="{path}"/>' for path in mark_paths())
        + "</g>"
    )

    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}" '
        f'shape-rendering="crispEdges">'
        f'<rect width="{total}" height="{total}" fill="#ffffff"/>'
        f'<g fill="{MARK_COLOR_HEX}">'
        f'<path d="{"".join(modules)}"/>'
        f"</g>"
        f'<g fill="{MARK_COLOR_HEX}" shape-rendering="geometricPrecision">{mark}</g>'
        f"</svg>\n"
    )
    return BytesIO(svg.encode("utf-8"))


def generate_qr_code_svg(
    short_code: str,
    error_correction: str = "M",
) -> BytesIO:
    """Тот же код в векторе — для типографии, которая печатает на упаковке."""
    qr = _qr_for(_qr_target_url(short_code), error_correction, box_size=10)
    buffer = BytesIO()
    qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buffer)
    buffer.seek(0)
    return buffer


def generate_qr_code_base64(
    short_code: str,
    size: int = 300,
    error_correction: str = "M",
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
    error_correction: str = "M",
) -> dict[str, str]:
    """
    Сохраняет изображения QR-кода на диск в разных размерах.

    Args:
        short_code: Короткий код (например: "FH-001")
        sizes: Список размеров для сохранения (по умолчанию: 300, 600, 1200)
        error_correction: Уровень коррекции ошибок (L, M, Q, H).
            M — замеренный оптимум для печати без логотипа: столько же модулей,
            что и L, вдвое больший запас на повреждения и читается с меньшего
            размера. H оправдан только когда часть кода закрыта знаком: он
            добавляет модули, и на мелкой наклейке код читается хуже.

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

        # Уровень коррекции в имени: файлы, записанные прежним генератором,
        # перестают находиться сами собой и не отдаются вместо новых.
        filename = f"{short_code}-{size}-{error_correction.upper()}.png"
        filepath = qr_dir / filename
        filepath.write_bytes(buffer.getvalue())

        # Сохраняем относительный путь для использования в URL
        saved_paths[str(size)] = f"qr_codes/{filename}"

    return saved_paths


def get_qr_code_path(short_code: str, size: int = 300, error_correction: str = "M") -> Path | None:
    """
    Получить путь к сохраненному изображению QR-кода.

    Returns:
        Path к файлу или None если файл не существует
    """
    base_path = Path(__file__).parent.parent.parent
    qr_dir = base_path / settings.QR_CODES_DIR
    filepath = qr_dir / f"{short_code}-{size}-{error_correction.upper()}.png"

    if filepath.exists():
        return filepath
    return None


async def ensure_filament_qr_code(
    filament: Filament,
    db: AsyncSession,
    *,
    render_images: bool = True,
) -> bool:
    """Assign a QR short code and optionally render label images.

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
    if render_images:
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


async def repair_verified_brand_qr_codes(db: AsyncSession) -> int:
    """Restore missing QR codes for every active material of a verified brand.

    This is the application-startup safety net. Normal creation and verification
    paths already assign the code immediately; this repair closes gaps left by
    old data, interrupted maintenance or an accidental cleared value without
    replacing any existing code.
    """
    result = await db.execute(
        select(Filament)
        .join(Brand, Brand.id == Filament.brand_id)
        .where(
            Brand.verified.is_(True),
            Brand.active.is_(True),
            Filament.active.is_(True),
            Filament.qr_code.is_(None),
        )
    )
    assigned = 0
    for filament in result.scalars().all():
        # Startup recovery restores the durable identity only. Rendering every
        # raster size here would stall the event loop on a large catalogue;
        # public and download endpoints already render a missing asset on demand.
        if await ensure_filament_qr_code(filament, db, render_images=False):
            assigned += 1
    return assigned

