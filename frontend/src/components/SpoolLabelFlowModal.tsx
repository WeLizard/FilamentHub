import axios from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Package, Printer, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { UserSpool, UserSpoolQrIdentity } from "../api/client";
import { spoolQrAPI } from "../api/client";
import {
  clearIdempotencyAttempt,
  idempotencyKeyForAttempt,
} from "../utils/idempotencyAttempt";
import { translateApiError } from "../utils/translateApiError";
import { LabelStudioModal } from "./LabelStudioModal";
import { ModalOverlay } from "./ModalOverlay";
import { toast } from "./Toast";

type LifecycleAction = "issue" | "rotate" | "retire" | "restore";
type Confirmation = Exclude<LifecycleAction, "restore"> | null;

const actionClass =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40";
const primaryClass =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-cyan-300/30 bg-cyan-400/15 px-3 py-2 text-sm font-medium text-cyan-50 transition hover:bg-cyan-400/25 disabled:cursor-not-allowed disabled:opacity-40";

function errorDetail(error: unknown): unknown {
  return axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
}

export function SpoolLabelFlowModal({
  spool,
  onClose,
}: {
  spool: Pick<UserSpool, "id" | "filament_id" | "filament">;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const queryKey = ["spool-qr", spool.id] as const;
  const [editor, setEditor] = useState<"product" | "instance" | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const rotationAttemptKey = `spool-qr-rotate:${spool.id}`;

  const identityQuery = useQuery<UserSpoolQrIdentity | null>({
    queryKey,
    queryFn: async () => {
      try {
        return await spoolQrAPI.get(spool.id);
      } catch (error) {
        if (axios.isAxiosError(error) && error.response?.status === 404) return null;
        throw error;
      }
    },
    retry: false,
  });

  const lifecycle = useMutation({
    mutationFn: async (action: LifecycleAction) => {
      const identity = identityQuery.data;
      if (action === "issue") return spoolQrAPI.issue(spool.id);
      if (!identity) throw new Error("Missing spool QR identity");
      if (action === "retire") return spoolQrAPI.retire(spool.id, identity.revision);
      if (action === "restore") return spoolQrAPI.restore(spool.id, identity.revision);
      return spoolQrAPI.rotate(
        spool.id,
        identity.revision,
        idempotencyKeyForAttempt(
          rotationAttemptKey,
          "spool-qr-rotate",
          { spool_id: spool.id, revision: identity.revision },
        ),
      );
    },
    onSuccess: (identity, action) => {
      queryClient.setQueryData(queryKey, identity);
      if (action === "rotate") clearIdempotencyAttempt(rotationAttemptKey);
      toast.success(t(`spoolQr.${action}Success`));
      setConfirmation(null);
      if (action === "issue" || action === "rotate") setEditor("instance");
    },
    onError: () => {
      // A lost response may follow a committed idempotent transition. Always
      // reconcile with the authoritative binding before the owner retries.
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  if (editor === "product" && spool.filament_id) {
    return (
      <LabelStudioModal
        filamentId={spool.filament_id}
        onClose={() => setEditor(null)}
      />
    );
  }
  if (editor === "instance") {
    return <LabelStudioModal spoolId={spool.id} onClose={() => setEditor(null)} />;
  }

  const identity = identityQuery.data;
  const pending = lifecycle.isPending;
  const canPrintInstance = identity?.state === "active" || identity?.state === "linked";
  const productName = [
    spool.filament?.brand_name,
    spool.filament?.material_type,
    spool.filament?.name,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <ModalOverlay
      onClose={onClose}
      closeOnEscape={!pending}
      closeOnOverlayClick={!pending}
      contentClassName="min-h-full flex items-center justify-center p-3 sm:p-6"
    >
      <section className="w-full max-w-xl rounded-2xl border border-white/10 bg-[#151021] p-5 shadow-2xl sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-white">{t("spoolQr.title")}</h2>
            <p className="mt-1 text-sm text-slate-400">{productName}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded-lg px-2 py-1 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-40"
            aria-label={t("common.close")}
          >
            ×
          </button>
        </div>

        <div className="mt-5 rounded-2xl border border-white/10 bg-white/[0.035] p-4">
          <div className="flex items-start gap-3">
            <Package className="mt-0.5 h-5 w-5 shrink-0 text-cyan-300" />
            <div className="min-w-0 flex-1">
              <h3 className="font-medium text-white">{t("spoolQr.productTitle")}</h3>
              <p className="mt-1 text-sm leading-5 text-slate-400">
                {t("spoolQr.productHint")}
              </p>
              <button
                type="button"
                onClick={() => setEditor("product")}
                className={`${actionClass} mt-3`}
              >
                <Printer className="h-4 w-4" />
                {t("spoolQr.printProduct")}
              </button>
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-2xl border border-cyan-300/15 bg-cyan-400/[0.045] p-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-cyan-300" />
            <div className="min-w-0 flex-1">
              <h3 className="font-medium text-white">{t("spoolQr.instanceTitle")}</h3>
              {identityQuery.isLoading ? (
                <p className="mt-1 text-sm text-slate-400">{t("spoolQr.loading")}</p>
              ) : identityQuery.isError ? (
                <div className="mt-2" role="alert">
                  <p className="text-sm text-red-300">
                    {translateApiError(
                      t,
                      errorDetail(identityQuery.error),
                      t("spoolQr.loadFailed"),
                    )}
                  </p>
                  <button
                    type="button"
                    onClick={() => identityQuery.refetch()}
                    className={`${actionClass} mt-3`}
                  >
                    <RefreshCw className="h-4 w-4" />
                    {t("spoolQr.retry")}
                  </button>
                </div>
              ) : !identity ? (
                <>
                  <p className="mt-1 text-sm leading-5 text-slate-400">
                    {t("spoolQr.notIssuedHint")}
                  </p>
                  <button
                    type="button"
                    onClick={() => setConfirmation("issue")}
                    className={`${primaryClass} mt-3`}
                  >
                    {t("spoolQr.issue")}
                  </button>
                </>
              ) : identity.state === "pending_retirement" ? (
                <>
                  <p className="mt-1 text-sm leading-5 text-amber-200">
                    {t("spoolQr.pendingHint", {
                      date: identity.purge_after
                        ? new Date(identity.purge_after).toLocaleDateString()
                        : "—",
                    })}
                  </p>
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => lifecycle.mutate("restore")}
                    className={`${primaryClass} mt-3`}
                  >
                    <ArchiveRestore className="h-4 w-4" />
                    {t("spoolQr.restore")}
                  </button>
                </>
              ) : (
                <>
                  <p className="mt-1 text-sm leading-5 text-slate-300">
                    {t(
                      identity.issuer === "manufacturer"
                        ? "spoolQr.manufacturerHint"
                        : "spoolQr.activeHint",
                    )}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setEditor("instance")}
                      className={primaryClass}
                    >
                      <Printer className="h-4 w-4" />
                      {t("spoolQr.printInstance")}
                    </button>
                    {identity.issuer === "user" && (
                      <>
                        <button
                          type="button"
                          onClick={() => setConfirmation("rotate")}
                          className={actionClass}
                        >
                          {t("spoolQr.rotate")}
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmation("retire")}
                          className={actionClass}
                        >
                          {t("spoolQr.retire")}
                        </button>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {confirmation && (
          <div className="mt-4 rounded-2xl border border-amber-300/20 bg-amber-300/[0.06] p-4">
            <h3 className="font-medium text-amber-100">
              {t(`spoolQr.${confirmation}ConfirmTitle`)}
            </h3>
            <p className="mt-1 text-sm leading-5 text-amber-50/70">
              {t(`spoolQr.${confirmation}ConfirmHint`)}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={pending}
                onClick={() => lifecycle.mutate(confirmation)}
                className={primaryClass}
              >
                {pending ? t("spoolQr.saving") : t(`spoolQr.${confirmation}Confirm`)}
              </button>
              <button
                type="button"
                disabled={pending}
                onClick={() => setConfirmation(null)}
                className={actionClass}
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        )}

        {lifecycle.isError && (
          <p className="mt-4 text-sm text-red-300" role="alert">
            {translateApiError(t, errorDetail(lifecycle.error), t("spoolQr.actionFailed"))}
          </p>
        )}
        {!confirmation && canPrintInstance && identity?.issuer === "user" && (
          <p className="mt-4 text-xs leading-5 text-slate-500">{t("spoolQr.rotationHint")}</p>
        )}
      </section>
    </ModalOverlay>
  );
}
