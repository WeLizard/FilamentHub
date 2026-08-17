"""SQLAlchemy models."""

from app.models.app_setting import AppSetting
from app.models.bad_word import BadWord
from app.models.brand import Brand
from app.models.brand_country_cell import BrandCountryCell
from app.models.brand_invite import BrandInvite
from app.models.brand_request import BrandRequest, BrandRequestStatus, BrandRequestType
from app.models.brand_slug_redirect import BrandSlugRedirect
from app.models.brand_territorial_grant import (
    BrandTerritorialGrant,
    GrantSource,
    GrantStatus,
)
from app.models.bundle import (
    Bundle,
    BundleImport,
    BundleImportStatus,
    BundleSource,
    BundleStatus,
)
from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.calculator_profile import UserCalculatorProfile
from app.models.crm import (
    CrmCustomer,
    CrmCustomerSearchToken,
    CrmOrder,
    CrmOrderSpoolReservation,
    CrmOrderStatus,
    CrmQuote,
    CrmQuoteEvent,
    CrmQuoteEventType,
    CrmQuoteLine,
    CrmQuoteStatus,
    CrmQuoteVersion,
    CrmReservationStatus,
)
from app.models.currency import Currency
from app.models.email_communication import EmailMessage, EmailSendReservation, EmailThread
from app.models.feedback import Feedback, FeedbackMessage, FeedbackStatus, FeedbackType
from app.models.filament import Filament
from app.models.filament_analytics_event import FilamentAnalyticsEvent
from app.models.filament_country_cell import CountryAvailability, FilamentCountryCell
from app.models.filament_line import FilamentLine
from app.models.filament_review import FilamentReview
from app.models.filament_slug_redirect import FilamentSlugRedirect
from app.models.material_mapping import MaterialMapping, MaterialMappingPriority
from app.models.material_property import MaterialProperty
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.notification import Notification, NotificationType
from app.models.notification_campaign import NotificationCampaign, NotificationCampaignRecipient
from app.models.octoprint_bridge import OctoPrintBridgeConnection, OctoPrintBridgeEvent
from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.orca_profile_sync import OrcaProfileBinding, OrcaProfileSyncScope
from app.models.orca_schema_observation import OrcaSchemaObservation
from app.models.orca_slice_report import OrcaSliceReport
from app.models.organization import (
    Organization,
    OrganizationBrandAccess,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.preset_printer import PresetPrinter
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.preset_version import PresetVersion, PresetVersionSource
from app.models.print_job import PrintJob, PrintJobEvent, PrintJobMaterial, PrintJobStatus
from app.models.print_problem import PrintProblem, PrintProblemSeverity
from app.models.print_profile import PrintProfile
from app.models.print_profile_configuration import PrintProfileConfigurationLink
from app.models.print_profile_filament import PrintProfileFilament
from app.models.print_profile_printer import PrintProfilePrinter
from app.models.printer import Printer
from app.models.printer_bridge_credential import PrinterBridgeCredential
from app.models.printer_bridge_observation import (
    MaterialSlotObservation,
    PhysicalPrinterStatusObservation,
)
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_profile import PrinterProfile
from app.models.printer_request import PrinterRequest, PrinterRequestStatus
from app.models.revoked_token import RevokedToken
from app.models.shared_quote import SharedQuote
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.sync_device import SyncDevice
from app.models.sync_history import SyncHistory, SyncOperation, SyncPresetType, SyncStatus
from app.models.user import User, UserRole
from app.models.user_legal_acceptance import UserLegalAcceptance
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_saved_preset import UserSavedPreset, UserSavedPresetTarget
from app.models.user_spool import UserSpool, UserSpoolState
from app.models.wiki_article import (
    WikiArticle,
    WikiArticleProvenance,
    WikiArticleStatus,
    WikiGuideProgress,
)
from app.models.wiki_category import WikiCategory
from app.models.wiki_feedback import WikiArticleFeedback, WikiFeedbackType
from app.models.wiki_media import WikiMediaAsset
from app.models.wiki_revision import (
    WikiReviewVerdict,
    WikiRevision,
    WikiRevisionAuthorship,
    WikiRevisionReview,
    WikiRevisionStatus,
)
from app.models.wiki_space import WikiSpace

__all__ = [
    "BadWord",
    "Currency",
    "Brand",
    "BrandCountryCell",
    "BrandTerritorialGrant",
    "GrantSource",
    "GrantStatus",
    "BrandInvite",
    "BrandRequest",
    "BrandRequestStatus",
    "BrandRequestType",
    "BrandSlugRedirect",
    "Bundle",
    "BundleImport",
    "BundleImportStatus",
    "BundleSource",
    "BundleStatus",
    "AppSetting",
    "CalculatorHistoryEntry",
    "UserCalculatorProfile",
    "CrmCustomer",
    "CrmCustomerSearchToken",
    "CrmOrder",
    "CrmOrderSpoolReservation",
    "CrmOrderStatus",
    "CrmQuote",
    "CrmQuoteEvent",
    "CrmQuoteEventType",
    "CrmQuoteLine",
    "CrmQuoteStatus",
    "CrmQuoteVersion",
    "CrmReservationStatus",
    "Feedback",
    "FeedbackMessage",
    "FeedbackType",
    "FeedbackStatus",
    "EmailMessage",
    "EmailSendReservation",
    "EmailThread",
    "Filament",
    "FilamentCountryCell",
    "FilamentAnalyticsEvent",
    "CountryAvailability",
    "FilamentLine",
    "FilamentReview",
    "FilamentSlugRedirect",
    "MaterialMapping",
    "MaterialMappingPriority",
    "MaterialProperty",
    "MaterialSlotAssignment",
    "MaterialSlot",
    "MaterialSystem",
    "PhysicalPrinterConnector",
    "MaterialSlotObservation",
    "PhysicalPrinterStatusObservation",
    "PrinterBridgeCredential",
    "Notification",
    "NotificationCampaign",
    "NotificationCampaignRecipient",
    "NotificationType",
    "OctoPrintBridgeConnection",
    "OctoPrintBridgeEvent",
    "OrcaPrinterConnectionObservation",
    "OrcaProfileBinding",
    "OrcaProfileSyncScope",
    "OrcaSchemaObservation",
    "OrcaSliceReport",
    "Organization",
    "OrganizationBrandAccess",
    "OrganizationMembership",
    "OrganizationMemberRole",
    "Preset",
    "PresetGateState",
    "PresetGateStateSource",
    "PresetUsageEvent",
    "PresetUsageEventType",
    "PresetVersion",
    "PresetVersionSource",
    "RevokedToken",
    "PresetModerationStatus",
    "PresetPrinter",
    "Printer",
    "PrinterConnectionBinding",
    "PrinterRequest",
    "PrinterRequestStatus",
    "PrinterProfile",
    "PrintProblem",
    "PrintProblemSeverity",
    "PrintJob",
    "PrintJobEvent",
    "PrintJobMaterial",
    "PrintJobStatus",
    "UserPrinterProfileLink",
    "PrintProfile",
    "PrintProfileConfigurationLink",
    "PrintProfilePrinter",
    "PrintProfileFilament",
    "SharedQuote",
    "Subscription",
    "SubscriptionStatus",
    "SyncDevice",
    "SyncHistory",
    "SyncOperation",
    "SyncPresetType",
    "SyncStatus",
    "User",
    "UserLegalAcceptance",
    "UserPrinterDevice",
    "UserRole",
    "UserSavedPreset",
    "UserSavedPresetTarget",
    "UserSpool",
    "UserSpoolState",
    "WikiArticle",
    "WikiArticleProvenance",
    "WikiArticleFeedback",
    "WikiArticleStatus",
    "WikiGuideProgress",
    "WikiCategory",
    "WikiFeedbackType",
    "WikiMediaAsset",
    "WikiRevision",
    "WikiRevisionAuthorship",
    "WikiRevisionReview",
    "WikiRevisionStatus",
    "WikiReviewVerdict",
    "WikiSpace",
]
