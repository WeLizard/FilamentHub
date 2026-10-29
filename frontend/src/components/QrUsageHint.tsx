import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { InfoHint } from "./InfoHint";

const SHELF_GUIDE =
  "/wiki/articles/spool-on-shelf?start=1&journey=user%3Ashelf";

/** One line that says what a spool QR is for, with the full answer in the tooltip. */
export function QrUsageHint({ className = "" }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const language = (i18n.resolvedLanguage || i18n.language).split("-")[0];
  return (
    <p
      className={`flex flex-wrap items-center gap-x-1.5 text-xs text-gray-400 ${className}`}
    >
      <span>{t("qrUsage.line")}</span>
      <InfoHint text={t("qrUsage.tooltip")} />
      <Link
        to={language === "ru" ? SHELF_GUIDE : "/wiki"}
        className="text-cyan-300 hover:text-cyan-200"
      >
        {t("qrUsage.more")}
      </Link>
    </p>
  );
}
