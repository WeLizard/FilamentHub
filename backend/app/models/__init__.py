"""SQLAlchemy models."""

# BadWord импортируется лениво, чтобы не падать при отсутствии таблицы
# from app.models.bad_word import BadWord
from app.models.brand import Brand
from app.models.brand_request import BrandRequest, BrandRequestStatus, BrandRequestType
from app.models.filament import Filament
from app.models.filament_review import FilamentReview
from app.models.material_mapping import MaterialMapping, MaterialMappingPriority
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.printer_request import PrinterRequest, PrinterRequestStatus
from app.models.printer_profile import PrinterProfile
from app.models.print_profile import PrintProfile
from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole
from app.models.user_saved_preset import UserSavedPreset

__all__ = [
    # "BadWord",  # Убрано из экспорта, чтобы не падать при отсутствии таблицы
    "Brand",
    "BrandRequest",
    "BrandRequestStatus",
    "BrandRequestType",
    "Filament",
    "FilamentReview",
    "MaterialMapping",
    "MaterialMappingPriority",
    "Notification",
    "NotificationType",
    "Preset",
    "PresetModerationStatus",
    "PresetPrinter",
    "Printer",
    "PrinterRequest",
    "PrinterRequestStatus",
    "PrinterProfile",
    "PrintProfile",
    "User",
    "UserRole",
    "UserSavedPreset",
]