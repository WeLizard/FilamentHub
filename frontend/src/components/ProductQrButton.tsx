import { useId, useState } from "react";
import { Copy, Download, Loader2, QrCode, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { qrAPI } from "../api/client";
import type { Filament } from "../types/api";
import { filamentPublicPath } from "../utils/catalogUrls";
import { absoluteLocalizedUrl, normalizeSiteLocale } from "../utils/siteLocale";
import { translateApiError } from "../utils/translateApiError";
import { ModalOverlay } from "./ModalOverlay";
import { toast } from "./Toast";

type Product = Pick<
  Filament,
  "id" | "name" | "slug" | "brand_slug" | "qr_code"
>;

export function ProductQrButton({
  filament,
  className = "",
}: {
  filament: Product;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!filament.qr_code) return null;

  const download = async (format: "png" | "svg") => {
    setError(null);
    setDownloading(true);
    try {
      await qrAPI.downloadQRCode(filament.id, 600, { format });
    } catch (error: any) {
      setError(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setDownloading(false);
    }
  };
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(
        absoluteLocalizedUrl(
          filamentPublicPath(filament),
          normalizeSiteLocale(i18n.language) ?? "en",
        ),
      );
      toast.success(t("productQr.copied"));
    } catch {
      setError(t("productQr.copyFailed"));
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setError(null);
          setImageFailed(false);
          setOpen(true);
        }}
        className={`inline-flex items-center justify-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 py-2 text-sm text-white transition hover:bg-white/20 ${className}`}
      >
        <QrCode className="h-4 w-4 shrink-0" />
        {t("productQr.title")}
      </button>
      {open && (
        <ModalOverlay onClose={() => setOpen(false)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="w-full max-w-sm rounded-2xl border border-white/15 bg-[#100c20] p-5 text-white shadow-2xl"
          >
            <header className="mb-4 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 id={titleId} className="text-lg font-semibold">
                  {t("productQr.title")}
                </h2>
                <p className="mt-1 break-words text-sm text-gray-300">
                  {filament.name}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={t("common.close")}
                className="rounded-lg p-2 hover:bg-white/10"
              >
                <X size={20} />
              </button>
            </header>
            {imageFailed ? (
              <p role="alert" className="py-8 text-center text-sm text-red-300">
                {t("productQr.imageFailed")}
              </p>
            ) : (
              <img
                src={qrAPI.getQRCodeURL(filament.id, 600)}
                alt={t("productQr.title")}
                onError={() => setImageFailed(true)}
                className="mx-auto aspect-square w-64 max-w-full rounded-xl bg-white"
              />
            )}
            <p className="mt-3 break-all text-center font-mono text-sm">
              {filament.qr_code}
            </p>
            <p className="mt-3 text-sm text-gray-400">{t("productQr.hint")}</p>
            {error && (
              <p role="alert" className="mt-3 text-sm text-red-300">
                {error}
              </p>
            )}
            <div className="mt-4 grid grid-cols-2 gap-2">
              {(["png", "svg"] as const).map((format) => (
                <button
                  type="button"
                  key={format}
                  disabled={downloading}
                  onClick={() => void download(format)}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/20 px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-50"
                >
                  {downloading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Download size={16} />
                  )}
                  {t("productQr.download", { format: format.toUpperCase() })}
                </button>
              ))}
              <button
                type="button"
                onClick={() => void copyLink()}
                className="col-span-2 inline-flex items-center justify-center gap-2 rounded-lg border border-white/20 px-3 py-2 text-sm hover:bg-white/10"
              >
                <Copy size={16} />
                {t("productQr.copyLink")}
              </button>
            </div>
          </section>
        </ModalOverlay>
      )}
    </>
  );
}
