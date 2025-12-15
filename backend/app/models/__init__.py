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
from app.models.print_profile_printer import PrintProfilePrinter
from app.models.print_profile_filament import PrintProfileFilament
from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole
from app.models.user_saved_preset import UserSavedPreset
from app.models.feedback import Feedback, FeedbackType, FeedbackStatus
from app.models.wiki_category import WikiCategory
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.material_property import MaterialProperty
from app.models.print_problem import PrintProblem, PrintProblemSeverity

__all__ = [
    # "BadWord",  # Убрано из экспорта, чтобы не падать при отсутствии таблицы
    "Brand",
    "BrandRequest",
    "BrandRequestStatus",
    "BrandRequestType",
    "Feedback",
    "FeedbackType",
    "FeedbackStatus",
    "Filament",
    "FilamentReview",
    "MaterialMapping",
    "MaterialMappingPriority",
    "MaterialProperty",
    "Notification",
    "NotificationType",
    "Preset",
    "PresetModerationStatus",
    "PresetPrinter",
    "Printer",
    "PrinterRequest",
    "PrinterRequestStatus",
    "PrinterProfile",
    "PrintProblem",
    "PrintProblemSeverity",
    "PrintProfile",
    "PrintProfilePrinter",
    "PrintProfileFilament",
    "User",
    "UserRole",
    "UserSavedPreset",
    "WikiArticle",
    "WikiArticleStatus",
    "WikiCategory",
]