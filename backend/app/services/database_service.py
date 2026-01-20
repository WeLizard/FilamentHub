"""Service for database management operations."""

import asyncio
import logging
import math
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

# Путь к директории с миграциями
ALEMBIC_CONFIG_PATH = Path(__file__).parent.parent.parent / "alembic.ini"
ALEMBIC_VERSIONS_PATH = Path(__file__).parent.parent.parent / "alembic" / "versions"


def get_alembic_config() -> Config:
    """Получить конфигурацию Alembic."""
    config = Config(str(ALEMBIC_CONFIG_PATH))
    # Экранируем % для Alembic (он интерпретирует % как интерполяцию)
    database_url_escaped = settings.DATABASE_URL.replace('%', '%%')
    config.set_main_option("sqlalchemy.url", database_url_escaped)
    return config


async def _ensure_migration_history_table(db: AsyncSession) -> None:
    """Создать таблицу для истории миграций, если её нет."""
    try:
        # Проверяем существование таблицы перед созданием
        result = await db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'alembic_migration_history'
            )
        """))
        exists = result.scalar()
        
        if not exists:
            logger.info("Создаем таблицу alembic_migration_history...")
            await db.execute(text("""
                CREATE TABLE alembic_migration_history (
                    revision VARCHAR(50) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT now(),
                    applied_by VARCHAR(255),
                    downgraded_at TIMESTAMP,
                    downgraded_by VARCHAR(255)
                )
            """))
            logger.info("✅ Таблица alembic_migration_history создана")
        else:
            logger.debug("Таблица alembic_migration_history уже существует")
    except Exception as e:
        logger.error(f"❌ Не удалось создать таблицу истории миграций: {e}", exc_info=True)
        await db.rollback()
        raise  # Пробрасываем исключение дальше, чтобы вызывающий код знал об ошибке


async def _record_migration_application(db: AsyncSession, revision: str, applied_by: str | None = None) -> None:
    """Записать применение миграции в историю."""
    await _ensure_migration_history_table(db)
    try:
        await db.execute(text("""
            INSERT INTO alembic_migration_history (revision, applied_at, applied_by, downgraded_at, downgraded_by)
            VALUES (:revision, now(), :applied_by, NULL, NULL)
            ON CONFLICT (revision) 
            DO UPDATE SET 
                applied_at = now(),
                applied_by = :applied_by,
                downgraded_at = NULL,
                downgraded_by = NULL
        """), {"revision": revision, "applied_by": applied_by})
        await db.commit()
    except Exception as e:
        logger.warning(f"Не удалось записать применение миграции {revision}: {e}")
        await db.rollback()


async def _record_migration_downgrade(db: AsyncSession, revision: str, downgraded_by: str | None = None) -> None:
    """Записать откат миграции в историю."""
    await _ensure_migration_history_table(db)
    try:
        await db.execute(text("""
            UPDATE alembic_migration_history
            SET downgraded_at = now(), downgraded_by = :downgraded_by
            WHERE revision = :revision
        """), {"revision": revision, "downgraded_by": downgraded_by})
        await db.commit()
    except Exception as e:
        logger.warning(f"Не удалось записать откат миграции {revision}: {e}")
        await db.rollback()


async def get_migration_history(db: AsyncSession) -> dict:
    """Получить историю миграций."""
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    
    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)
    
    # Получаем текущую ревизию из БД
    current_revision = None
    try:
        # Используем прямой запрос без транзакции для чтения
        # Явно указываем autocommit для чтения
        result = await db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        if row:
            current_revision = str(row[0])  # Явно преобразуем в строку
            logger.info(f"✅ Текущая ревизия из БД: {current_revision}")
        else:
            logger.info("⚠️ Таблица alembic_version пуста (миграции ещё не применялись)")
    except Exception as e:
        # Таблица alembic_version может не существовать, если миграции ещё не применялись
        logger.warning(f"❌ Не удалось получить текущую ревизию: {e}", exc_info=True)
        current_revision = None
    
    # Получаем историю применения миграций
    migration_history_map = {}
    try:
        # Создаем таблицу истории миграций, если её нет
        await _ensure_migration_history_table(db)
        # Коммитим создание таблицы отдельно, чтобы она была доступна для запросов
        await db.commit()
        
        result = await db.execute(text("""
            SELECT revision, applied_at, applied_by, downgraded_at, downgraded_by
            FROM alembic_migration_history
            WHERE downgraded_at IS NULL
        """))
        for row in result.fetchall():
            # Конвертируем datetime в ISO строку для Pydantic
            applied_at = row[1]
            if applied_at and isinstance(applied_at, datetime):
                applied_at = applied_at.isoformat()
            migration_history_map[row[0]] = {
                "applied_at": applied_at,
                "applied_by": row[2],
            }
    except Exception as e:
        logger.warning(f"Не удалось получить историю миграций: {e}")
    
    # Получаем все миграции
    migrations = []
    heads = [rev.revision for rev in script.get_revisions("heads")]
    
    # Сначала строим карту всех миграций для быстрого доступа
    all_revisions_map = {}
    for rev in script.walk_revisions():
        all_revisions_map[rev.revision] = rev
        # Получаем дату применения из истории, если есть
        history = migration_history_map.get(rev.revision, {})
        # down_revision может быть tuple (merge миграции) - конвертируем в строку
        down_rev = rev.down_revision
        if isinstance(down_rev, tuple):
            down_rev = ",".join(down_rev)
        
        migration = {
            "revision": rev.revision,
            "down_revision": down_rev,
            "branch_labels": ",".join(rev.branch_labels) if rev.branch_labels else None,
            "is_head": rev.revision in heads,
            "is_applied": False,  # Будет обновлено ниже
            "applied_at": history.get("applied_at"),  # Дата из истории миграций
            "description": rev.doc if rev.doc else None,
        }
        migrations.append(migration)
    
    # Проверяем, какая миграция применена
    # Alembic хранит только текущую ревизию, поэтому нужно проверить цепочку
    applied_revisions = set()
    if current_revision:
        # Находим все применённые миграции (от текущей до начальной)
        # Используем рекурсивный подход для обработки всех веток
        visited = set()
        
        def add_migration_chain(revision_id: str | None):
            """Рекурсивно добавляет миграцию и все её предшественники."""
            if revision_id is None or revision_id in visited:
                return
            
            visited.add(revision_id)
            
            # Получаем ревизию из карты или через script
            rev = all_revisions_map.get(revision_id)
            if not rev:
                try:
                    rev = script.get_revision(revision_id)
                except Exception:
                    logger.warning(f"Не удалось найти ревизию {revision_id}")
                    applied_revisions.add(revision_id)
                    return
            
            if rev:
                applied_revisions.add(rev.revision)
                logger.debug(f"Добавлена применённая миграция: {rev.revision}")
                
                # Обрабатываем down_revision
                if rev.down_revision:
                    if isinstance(rev.down_revision, tuple):
                        # Множественные down_revision (merge) - обрабатываем все ветки
                        logger.debug(f"Обнаружен merge в {rev.revision}, ветки: {rev.down_revision}")
                        for down_rev in rev.down_revision:
                            if down_rev:
                                add_migration_chain(down_rev)
                    else:
                        # Одна ветка
                        add_migration_chain(rev.down_revision)
        
        # Начинаем с текущей ревизии
        logger.info(f"Начинаем построение цепочки применённых миграций с {current_revision}")
        add_migration_chain(current_revision)
        logger.info(f"Найдено применённых миграций: {len(applied_revisions)}")
        logger.debug(f"Применённые ревизии: {sorted(applied_revisions)}")
    
    # Обновляем статус применения
    for migration in migrations:
        migration["is_applied"] = migration["revision"] in applied_revisions
    
    return {
        "current_revision": current_revision,
        "heads": heads,
        "migrations": migrations,
    }


async def validate_migration_integrity(db: AsyncSession) -> tuple[bool, list[str]]:
    """
    Проверить целостность БД после применения миграций.

    Проверяет, что все таблицы из миграций действительно существуют в БД.

    Returns:
        (is_valid, list_of_missing_tables)
    """
    from alembic.script import ScriptDirectory

    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)

    # Получаем список таблиц из моделей SQLAlchemy
    from app.db.base import Base
    # Импортируем ВСЕ модели для регистрации в metadata
    from app.models import (  # noqa: F401
        Brand,
        BrandRequest,
        Filament,
        FilamentReview,
        MaterialMapping,
        Preset,
        PresetPrinter,
        Printer,
        PrinterRequest,
        User,
        UserSavedPreset,
    )
    # Дополнительные модели (могут отсутствовать в старых версиях)
    try:
        from app.models.feedback import Feedback  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.notification import Notification  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.wiki_article import WikiArticle  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.wiki_category import WikiCategory  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.wiki_feedback import WikiArticleFeedback  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.bad_word import BadWord  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.printer_profile import PrinterProfile  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.print_profile import PrintProfile  # noqa: F401
    except ImportError:
        pass
    
    # Получаем все таблицы из metadata
    expected_tables = set(Base.metadata.tables.keys())
    # Добавляем alembic_version, которая не в моделях
    expected_tables.add('alembic_version')
    
    # Получаем реальные таблицы из БД
    try:
        result = await db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        existing_tables = {row[0] for row in result.fetchall()}
        
        # Находим отсутствующие таблицы
        missing_tables = expected_tables - existing_tables
        
        return len(missing_tables) == 0, list(missing_tables)
    except Exception as e:
        logger.error(f"Ошибка проверки целостности БД: {e}", exc_info=True)
        return False, [f"Ошибка проверки: {str(e)}"]


async def recreate_missing_tables(db: AsyncSession) -> tuple[bool, str, list[str]]:
    """
    Восстановить все недостающие таблицы через применение миграций Alembic.
    
    Сначала пытается применить все неприменённые миграции до head.
    Если это не помогает, использует SQLAlchemy metadata как fallback.
    
    Returns:
        (success, message, created_tables)
    """
    try:
        # Шаг 1: Проверяем, какие таблицы отсутствуют
        is_valid, missing_tables = await validate_migration_integrity(db)
        
        if is_valid:
            return True, "Все таблицы уже существуют. Нечего восстанавливать.", []
        
        if not missing_tables:
            return True, "Все таблицы уже существуют. Нечего восстанавливать.", []
        
        # Шаг 2: Пытаемся применить миграции до head
        # Это правильный способ создания таблиц
        logger.info(f"Обнаружены отсутствующие таблицы: {missing_tables}. Применяем миграции до head...")
        
        try:
            config = get_alembic_config()
            
            def run_upgrade():
                # Применяем все миграции до head
                command.upgrade(config, "head")
            
            await asyncio.to_thread(run_upgrade)
            
            # Проверяем результат
            is_valid_after, still_missing = await validate_migration_integrity(db)
            
            if is_valid_after:
                return True, f"✅ Успешно восстановлено через миграции. Все таблицы созданы.", list(missing_tables)
            
            if still_missing:
                logger.warning(f"После применения миграций всё ещё отсутствуют таблицы: {still_missing}")
                # Продолжаем к fallback методу
                missing_tables = still_missing
        
        except Exception as migration_error:
            logger.warning(f"Не удалось применить миграции: {migration_error}. Используем fallback метод.")
            # Продолжаем к fallback методу
        
        # Шаг 3: Fallback - создаём через SQLAlchemy metadata
        # Это используется только если миграции не помогли
        logger.info(f"Используем fallback метод для создания таблиц: {missing_tables}")

        from app.db.base import Base
        # Импортируем ВСЕ модели для регистрации в metadata
        from app.models import (  # noqa: F401
            Brand,
            BrandRequest,
            Filament,
            FilamentReview,
            MaterialMapping,
            Preset,
            PresetPrinter,
            Printer,
            PrinterRequest,
            User,
            UserSavedPreset,
        )
        # Дополнительные модели
        try:
            from app.models.feedback import Feedback  # noqa: F401
            from app.models.notification import Notification  # noqa: F401
            from app.models.wiki_article import WikiArticle  # noqa: F401
            from app.models.wiki_category import WikiCategory  # noqa: F401
            from app.models.wiki_feedback import WikiArticleFeedback  # noqa: F401
            from app.models.bad_word import BadWord  # noqa: F401
            from app.models.printer_profile import PrinterProfile  # noqa: F401
            from app.models.print_profile import PrintProfile  # noqa: F401
        except ImportError:
            pass
        
        # Получаем список существующих таблиц
        result = await db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        existing_tables = {row[0] for row in result.fetchall()}
        
        # Получаем все таблицы из metadata
        all_tables = set(Base.metadata.tables.keys())
        
        # Находим отсутствующие таблицы (исключаем alembic_version)
        tables_to_create = all_tables - existing_tables - {'alembic_version'}
        
        if not tables_to_create:
            return True, "Все таблицы уже существуют после применения миграций.", []
        
        # Создаём недостающие таблицы через SQLAlchemy metadata
        from app.db.session import engine
        
        async def create_tables_async():
            async with engine.begin() as conn:
                # Используем run_sync для выполнения синхронного create_all
                await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        
        await create_tables_async()
        
        # Проверяем, что таблицы действительно созданы
        result = await db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        new_existing_tables = {row[0] for row in result.fetchall()}
        actually_created = tables_to_create & new_existing_tables
        
        if actually_created:
            warning = " (⚠️ ВНИМАНИЕ: использован fallback метод через metadata. Проверьте ENUM типы и индексы!)"
            return True, f"Создано таблиц через fallback метод: {len(actually_created)}{warning}", list(actually_created)
        else:
            return False, "Не удалось создать таблицы. Проверьте логи для деталей.", []
    
    except Exception as e:
        logger.error(f"Ошибка восстановления таблиц: {e}", exc_info=True)
        return False, f"Ошибка восстановления таблиц: {str(e)}", []


async def apply_migration(revision: str = "head", applied_by: str | None = None) -> tuple[bool, str, Optional[str], Optional[list[str]]]:
    """
    Применить миграцию через Alembic с валидацией и записью в историю.
    
    Args:
        revision: Ревизия для применения ('head', '+1', '-1', или конкретная ревизия)
        applied_by: Имя пользователя, применившего миграцию (опционально)
    
    Returns:
        (success, message, current_revision, validation_errors)
    """
    try:
        config = get_alembic_config()
        
        # Определяем, какие миграции будут применены
        # Для этого нужно получить текущую ревизию и вычислить целевую
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as pre_db:
            result = await pre_db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            old_revision = row[0] if row else None
        
        # Запускаем Alembic команду синхронно (Alembic не поддерживает async напрямую)
        # Используем asyncio.to_thread для неблокирующего выполнения
        def run_upgrade():
            command.upgrade(config, revision)
        
        await asyncio.to_thread(run_upgrade)
        
        # Получаем текущую ревизию после применения
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            current_revision = row[0] if row else None
            
            # Записываем в историю все применённые миграции
            if current_revision and current_revision != old_revision:
                from alembic.script import ScriptDirectory
                script = ScriptDirectory.from_config(config)
                applied_revisions = []
                
                # Находим все миграции между old_revision и current_revision
                if old_revision:
                    # Строим путь от старой до новой ревизии через down_revision цепочку
                    # Начинаем с current_revision и идём назад до old_revision
                    path = []
                    current = current_revision
                    visited = set()
                    
                    while current and current not in visited:
                        visited.add(current)
                        path.append(current)
                        
                        if current == old_revision:
                            # Нашли начало пути, разворачиваем список
                            applied_revisions = list(reversed(path))
                            break
                        
                        try:
                            rev = script.get_revision(current)
                            if rev and rev.down_revision:
                                if isinstance(rev.down_revision, tuple):
                                    # Merge - берём первую ветку
                                    current = rev.down_revision[0] if rev.down_revision[0] else None
                                else:
                                    current = rev.down_revision
                            else:
                                break
                        except Exception:
                            break
                    
                    # Если не удалось найти путь, просто записываем текущую
                    if not applied_revisions:
                        applied_revisions = [current_revision]
                else:
                    # Если не было старой ревизии, записываем текущую
                    applied_revisions = [current_revision]
                
                # Записываем все применённые миграции
                for rev in applied_revisions:
                    await _record_migration_application(db, rev, applied_by)
        
        # Валидация после применения миграции
        async with AsyncSessionLocal() as validation_db:
            is_valid, missing_tables = await validate_migration_integrity(validation_db)
            
            if not is_valid:
                warning_msg = f"Миграция {revision} применена, но обнаружены проблемы: отсутствуют таблицы {', '.join(missing_tables)}"
                logger.warning(warning_msg)
                return True, f"Миграция {revision} применена. ВНИМАНИЕ: {warning_msg}", current_revision, missing_tables
        
        return True, f"Миграция {revision} успешно применена и проверена", current_revision, None
    
    except Exception as e:
        logger.error(f"Ошибка применения миграции {revision}: {e}", exc_info=True)
        return False, f"Ошибка применения миграции: {str(e)}", None, None


async def downgrade_migration(revision: str = "-1", downgraded_by: str | None = None) -> tuple[bool, str, Optional[str]]:
    """
    Откатить миграцию через Alembic с записью в историю.

    Args:
        revision: Ревизия для отката ('-1', 'base', или конкретная ревизия)
        downgraded_by: Имя пользователя, откатившего миграцию (опционально)

    Returns:
        (success, message, current_revision)
    """
    try:
        config = get_alembic_config()

        # Получаем текущую ревизию до отката
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as pre_db:
            result = await pre_db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            old_revision = row[0] if row else None

        def run_downgrade():
            command.downgrade(config, revision)

        await asyncio.to_thread(run_downgrade)

        # Получаем текущую ревизию после отката
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            current_revision = row[0] if row else None

            # Записываем откат в историю
            if old_revision and old_revision != current_revision:
                await _record_migration_downgrade(db, old_revision, downgraded_by)

        return True, f"Миграция успешно откачена до {revision}", current_revision

    except Exception as e:
        logger.error(f"Ошибка отката миграции до {revision}: {e}", exc_info=True)
        return False, f"Ошибка отката миграции: {str(e)}", None


async def stamp_migration(revision: str = "head", stamped_by: str | None = None) -> tuple[bool, str, Optional[str]]:
    """
    Пометить миграцию как применённую БЕЗ выполнения SQL.

    Полезно когда:
    - Миграция частично применилась (enum создан, но таблица нет)
    - Нужно синхронизировать состояние alembic_version с реальной БД
    - База была создана вручную и нужно пометить миграции как применённые

    Args:
        revision: Ревизия для пометки ('head' или конкретная ревизия)
        stamped_by: Имя пользователя (опционально)

    Returns:
        (success, message, current_revision)
    """
    try:
        config = get_alembic_config()

        def run_stamp():
            command.stamp(config, revision)

        await asyncio.to_thread(run_stamp)

        # Получаем текущую ревизию после stamp
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            current_revision = row[0] if row else None

            # Записываем в историю
            if current_revision:
                await _record_migration_application(db, current_revision, stamped_by)

        return True, f"Миграция {revision} помечена как применённая (без выполнения SQL)", current_revision

    except Exception as e:
        logger.error(f"Ошибка пометки миграции {revision}: {e}", exc_info=True)
        return False, f"Ошибка пометки миграции: {str(e)}", None


async def list_database_dumps() -> list[dict]:
    """
    Получить список всех дампов базы данных.
    
    Returns:
        Список словарей с информацией о дампах: filename, size, created_at, format
    """
    try:
        dumps_dir = Path(settings.UPLOAD_DIR) / "database_dumps"
        if not dumps_dir.exists():
            return []
        
        dumps = []
        for file_path in dumps_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                filename = file_path.name
                
                # Определяем формат по расширению
                if filename.endswith('.dump'):
                    format_type = 'custom'
                elif filename.endswith('.sql'):
                    format_type = 'plain'
                elif filename.endswith('.tar'):
                    format_type = 'tar'
                else:
                    format_type = 'unknown'
                
                dumps.append({
                    "filename": filename,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "format": format_type,
                })
        
        # Сортируем по дате создания (новые первыми)
        dumps.sort(key=lambda x: x["created_at"], reverse=True)
        return dumps
    
    except Exception as e:
        logger.error(f"Ошибка получения списка дампов: {e}", exc_info=True)
        return []


async def delete_database_dump(filename: str) -> tuple[bool, str]:
    """
    Удалить файл дампа базы данных.
    
    Args:
        filename: Имя файла дампа
    
    Returns:
        (success, message)
    """
    try:
        dumps_dir = Path(settings.UPLOAD_DIR) / "database_dumps"
        dump_file = dumps_dir / filename
        
        # Проверяем, что файл существует и находится в правильной директории
        if not dump_file.exists():
            return False, f"Файл дампа не найден: {filename}"
        
        # Проверяем, что файл действительно в директории дампов (безопасность)
        if not str(dump_file).startswith(str(dumps_dir.resolve())):
            return False, "Недопустимый путь к файлу"
        
        # Удаляем файл
        dump_file.unlink()
        
        return True, f"Файл дампа {filename} успешно удалён"
    
    except Exception as e:
        logger.error(f"Ошибка удаления дампа {filename}: {e}", exc_info=True)
        return False, f"Ошибка удаления: {str(e)}"


async def get_database_stats(db: AsyncSession) -> dict:
    """Получить статистику базы данных."""
    # Получаем имя базы данных
    db_name_result = await db.execute(text("SELECT current_database()"))
    db_name = db_name_result.scalar()
    
    # Получаем размер базы данных
    size_result = await db.execute(
        text("SELECT pg_size_pretty(pg_database_size(current_database())) as size, "
             "pg_database_size(current_database()) as size_bytes")
    )
    size_row = size_result.fetchone()
    db_size = size_row[0] if size_row else "0 bytes"
    db_size_bytes = size_row[1] if size_row else 0
    
    # Получаем статистику по таблицам
    tables_result = await db.execute(
        text("""
            SELECT 
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_schema = schemaname AND table_name = tablename
                ) AS column_count
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
        """)
    )
    
    table_stats = []
    for row in tables_result.fetchall():
        # Получаем количество записей в таблице
        # Безопасное использование имён таблиц (они уже из pg_tables, так что безопасны)
        schema_name = row[0].replace('"', '""')
        table_name = row[1].replace('"', '""')
        count_result = await db.execute(
            text(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"')
        )
        row_count = count_result.scalar() or 0
        
        table_stats.append({
            "schema": row[0],
            "table": row[1],
            "size": row[2],
            "size_bytes": row[3],
            "column_count": row[4],
            "row_count": row_count,
        })
    
    return {
        "database_name": db_name,
        "database_size": db_size,
        "database_size_bytes": db_size_bytes,
        "table_stats": table_stats,
    }


async def export_database(
    format: str = "custom",
    include_data: bool = True,
    tables: Optional[list[str]] = None,
) -> tuple[bool, str, Optional[str], Optional[int]]:
    """
    Экспортировать базу данных через pg_dump.
    
    Args:
        format: Формат экспорта ('custom', 'plain', 'tar')
        include_data: Включать ли данные (True) или только схему (False)
        tables: Список таблиц для экспорта (None = все таблицы)
    
    Returns:
        (success, message, filename, size)
    """
    try:
        # Парсим DATABASE_URL для получения параметров подключения
        from urllib.parse import urlparse
        parsed = urlparse(settings.DATABASE_URL.replace("+asyncpg", ""))
        
        db_name = parsed.path.lstrip("/")
        db_user = parsed.username
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432
        
        # Создаём директорию для дампов если её нет
        dumps_dir = Path(settings.UPLOAD_DIR) / "database_dumps"
        dumps_dir.mkdir(parents=True, exist_ok=True)
        
        # Генерируем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if format == "custom":
            ext = ".dump"
        elif format == "plain":
            ext = ".sql"
        elif format == "tar":
            ext = ".tar"
        else:
            ext = ".dump"
        
        filename = f"filamenthub_backup_{timestamp}{ext}"
        filepath = dumps_dir / filename
        
        # Формируем команду pg_dump
        cmd = [
            "pg_dump",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-d", db_name,
            "-F", format[0],  # 'c' для custom, 'p' для plain, 't' для tar
        ]
        
        if not include_data:
            cmd.append("--schema-only")
        
        if tables:
            for table in tables:
                cmd.extend(["-t", table])
        
        # Устанавливаем переменную окружения для пароля
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        # Выполняем экспорт
        def run_export():
            with open(filepath, "wb") as f:
                process = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=True,
                )
                return process.returncode == 0
        
        success = await asyncio.to_thread(run_export)
        
        if success:
            size = filepath.stat().st_size
            return True, f"База данных успешно экспортирована", filename, size
        else:
            return False, "Ошибка экспорта базы данных", None, None
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка экспорта базы данных: {e.stderr.decode()}", exc_info=True)
        return False, f"Ошибка экспорта: {e.stderr.decode()}", None, None
    except Exception as e:
        logger.error(f"Ошибка экспорта базы данных: {e}", exc_info=True)
        return False, f"Ошибка экспорта: {str(e)}", None, None


async def import_database(
    filepath: str,
    format: str = "custom",
    clean: bool = False,
    create: bool = False,
) -> tuple[bool, str]:
    """
    Импортировать базу данных через pg_restore или psql.
    
    Args:
        filepath: Путь к файлу дампа
        format: Формат импорта ('custom', 'plain', 'tar')
        clean: Очистить базу перед импортом
        create: Создать базу если не существует
    
    Returns:
        (success, message)
    """
    try:
        # Парсим DATABASE_URL
        from urllib.parse import urlparse
        parsed = urlparse(settings.DATABASE_URL.replace("+asyncpg", ""))
        
        db_name = parsed.path.lstrip("/")
        db_user = parsed.username
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432
        
        # Проверяем существование файла
        dump_file = Path(settings.UPLOAD_DIR) / "database_dumps" / filepath
        if not dump_file.exists():
            return False, f"Файл дампа не найден: {filepath}"
        
        # Формируем команду в зависимости от формата
        if format == "plain":
            # Для plain используется psql
            cmd = [
                "psql",
                "-h", db_host,
                "-p", str(db_port),
                "-U", db_user,
                "-d", db_name,
                "-f", str(dump_file),
            ]
        else:
            # Для custom и tar используется pg_restore
            cmd = [
                "pg_restore",
                "-h", db_host,
                "-p", str(db_port),
                "-U", db_user,
                "-d", db_name,
            ]
            
            if clean:
                cmd.append("--clean")
            
            if create:
                cmd.append("--create")
            
            cmd.append(str(dump_file))
        
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        def run_import():
            try:
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=True,
                    timeout=300,  # Таймаут 5 минут для больших дампов
                )
                return True, process.stdout.decode() if process.stdout else "База данных успешно импортирована"
            except subprocess.TimeoutExpired:
                return False, "Таймаут импорта: операция заняла слишком много времени (>5 минут)"
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                logger.error(f"Ошибка импорта: {error_msg}")
                return False, f"Ошибка импорта: {error_msg[:500]}"  # Ограничиваем длину сообщения
            except Exception as e:
                logger.error(f"Неожиданная ошибка импорта: {e}", exc_info=True)
                return False, f"Ошибка импорта: {str(e)}"
        
        success, result_message = await asyncio.to_thread(run_import)
        
        if success:
            return True, result_message if isinstance(result_message, str) else "База данных успешно импортирована"
        else:
            return False, result_message if isinstance(result_message, str) else "Ошибка импорта базы данных"
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка импорта базы данных: {e.stderr.decode()}", exc_info=True)
        return False, f"Ошибка импорта: {e.stderr.decode()}"
    except Exception as e:
        logger.error(f"Ошибка импорта базы данных: {e}", exc_info=True)
        return False, f"Ошибка импорта: {str(e)}"


async def get_table_structure(db: AsyncSession, table_name: str, schema_name: str = "public") -> dict:
    """Получить структуру таблицы (колонки, индексы, ограничения)."""
    
    # Получаем информацию о колонках
    columns_result = await db.execute(
        text("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = :schema_name AND table_name = :table_name
            ORDER BY ordinal_position
        """),
        {"schema_name": schema_name, "table_name": table_name}
    )
    
    columns = []
    for row in columns_result.fetchall():
        columns.append({
            "column_name": row[0],
            "data_type": row[1],
            "is_nullable": row[2] == "YES",
            "column_default": row[3],
            "character_maximum_length": row[4],
        })
    
    # Получаем информацию об индексах
    indexes_result = await db.execute(
        text("""
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = :schema_name AND tablename = :table_name
        """),
        {"schema_name": schema_name, "table_name": table_name}
    )
    
    indexes = []
    for row in indexes_result.fetchall():
        indexes.append({
            "name": row[0],
            "definition": row[1],
        })
    
    # Получаем информацию об ограничениях
    constraints_result = await db.execute(
        text("""
            SELECT 
                constraint_name,
                constraint_type
            FROM information_schema.table_constraints
            WHERE table_schema = :schema_name AND table_name = :table_name
        """),
        {"schema_name": schema_name, "table_name": table_name}
    )
    
    constraints = []
    for row in constraints_result.fetchall():
        constraints.append({
            "name": row[0],
            "type": row[1],
        })
    
    return {
        "table_name": table_name,
        "schema_name": schema_name,
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
    }


async def get_table_data(
    db: AsyncSession,
    table_name: str,
    schema_name: str = "public",
    page: int = 1,
    size: int = 50,
    order_by: Optional[str] = None,
    order_desc: bool = False,
    search: Optional[str] = None,
) -> dict:
    """Получить данные из таблицы с пагинацией."""
    
    # Безопасное имя таблицы (защита от SQL injection)
    safe_table_name = table_name.replace('"', '""')
    safe_schema_name = schema_name.replace('"', '""')
    qualified_table = f'"{safe_schema_name}"."{safe_table_name}"'
    
    # Получаем список колонок
    columns_result = await db.execute(
        text(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema_name AND table_name = :table_name
            ORDER BY ordinal_position
        """),
        {"schema_name": schema_name, "table_name": table_name}
    )
    columns = [row[0] for row in columns_result.fetchall()]
    
    if not columns:
        raise ValueError(f"Таблица {schema_name}.{table_name} не найдена или не имеет колонок")
    
    # Строим WHERE для поиска
    where_clause = ""
    search_params = {}
    if search:
        # Поиск по всем текстовым колонкам
        search_conditions = []
        for col in columns:
            search_conditions.append(f'CAST("{col}" AS TEXT) ILIKE :search')
        where_clause = "WHERE " + " OR ".join(search_conditions)
        search_params["search"] = f"%{search}%"
    
    # Строим ORDER BY
    order_clause = ""
    if order_by and order_by in columns:
        safe_order_by = order_by.replace('"', '""')
        order_clause = f'ORDER BY "{safe_order_by}" {"DESC" if order_desc else "ASC"}'
    
    # Подсчет общего количества строк
    count_query = text(f'SELECT COUNT(*) FROM {qualified_table} {where_clause}')
    count_result = await db.execute(count_query, search_params)
    total = count_result.scalar() or 0
    
    # Получение данных с пагинацией
    offset = (page - 1) * size
    data_query = text(f'SELECT * FROM {qualified_table} {where_clause} {order_clause} LIMIT :limit OFFSET :offset')
    data_params = {**search_params, "limit": size, "offset": offset}
    data_result = await db.execute(data_query, data_params)
    
    # Преобразуем строки в словари
    rows = []
    for row in data_result.fetchall():
        row_dict = {}
        for i, col in enumerate(columns):
            value = row[i]
            # Преобразуем специальные типы в строки для JSON
            if isinstance(value, datetime):
                value = value.isoformat()
            elif hasattr(value, '__dict__'):
                value = str(value)
            row_dict[col] = value
        rows.append(row_dict)
    
    pages = math.ceil(total / size) if total > 0 else 0
    
    return {
        "table_name": table_name,
        "schema_name": schema_name,
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }

