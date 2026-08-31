import { useState } from "react";
import { Printer } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UserSpool } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { SpoolLabelFlowModal } from "./SpoolLabelFlowModal";

export function SpoolLabelButton({
  spool,
  compact = false,
  busy = false,
}: {
  spool: Pick<UserSpool, "id" | "user_id" | "filament_id" | "filament">;
  compact?: boolean;
  busy?: boolean;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  if (!user || user.id !== spool.user_id) return null;
  const available = Boolean(spool.filament_id && spool.filament?.qr_code);
  return (
    <>
      <button
        type="button"
        disabled={busy || !available}
        onClick={() => setOpen(true)}
        aria-label={t("labelStudio.printLabel")}
        title={t(
          available ? "labelStudio.printLabel" : "labelStudio.spoolUnavailable",
        )}
        className={
          compact
            ? "rounded-lg p-1.5 text-gray-300 transition hover:bg-white/10 hover:text-white disabled:opacity-40"
            : "inline-flex items-center justify-center gap-1 rounded-lg border border-cyan-400/25 bg-cyan-400/10 px-2 py-1 text-[11px] text-cyan-100 hover:bg-cyan-400/20 disabled:opacity-40"
        }
      >
        <Printer className="h-3 w-3" />
        {!compact && t("labelStudio.labelAction")}
      </button>
      {open && available && (
        <SpoolLabelFlowModal
          key={spool.id}
          spool={spool}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
