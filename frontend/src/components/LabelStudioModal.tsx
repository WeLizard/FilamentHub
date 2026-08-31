import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  ArrowLeftRight,
  ChevronLeft,
  ChevronRight,
  Download,
  X,
} from "lucide-react";
import type { AxiosError } from "axios";
import { labelsAPI } from "../api/client";
import { useDebounce } from "../hooks/useDebounce";
import type {
  LabelExportOptions,
  LabelField,
  LabelOptions,
} from "../types/labels";
import { translateApiError } from "../utils/translateApiError";
import { labelCutGuideLimits, labelSheetGrid } from "../utils/labelSheet";
import { ModalOverlay } from "./ModalOverlay";
import { LabelBrandingControl } from "./LabelBrandingControl";
import { Dropdown } from "./Dropdown";
import { toast } from "./Toast";

type LabelDraft = Omit<LabelOptions, "fields"> & {
  fields: (LabelField | "")[];
};
const initialLabel: LabelDraft = {
  width_mm: 50,
  height_mm: 30,
  kind: "full",
  color_mode: "mono",
  dpi: 203,
  locale: "ru",
  attribution: "full",
  qr_mark: true,
  brand_mode: "full",
  border: false,
  fields: ["nozzle", "bed", "drying", "abrasiveness", "diameter", "density"],
  comment: "",
};
const inputClass =
  "min-w-0 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white focus:border-cyan-300 focus:outline-none";
const buttonClass =
  "rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40";
type Orientation = "landscape" | "portrait";
const orientationKey = "label-studio-orientation";

function readOrientation(): Orientation {
  try {
    return sessionStorage.getItem(orientationKey) === "portrait"
      ? "portrait"
      : "landscape";
  } catch {
    return "landscape";
  }
}

function orientSize(width: number, height: number, orientation: Orientation) {
  const long = Math.max(width, height),
    short = Math.min(width, height);
  return orientation === "portrait" ? [short, long] : [long, short];
}

export function LabelStudioModal({
  filamentId,
  spoolId,
  onClose,
}: ({
  filamentId: number;
  spoolId?: never;
} | {
  filamentId?: never;
  spoolId: number;
}) & {
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const locale: LabelOptions["locale"] = i18n.language.startsWith("ru")
    ? "ru"
    : i18n.language.startsWith("zh")
      ? "zh"
      : "en";
  const [orientation, setOrientation] = useState<Orientation>(readOrientation);
  const [label, setLabel] = useState(() => {
    const [width_mm, height_mm] = orientSize(50, 30, orientation);
    return { ...initialLabel, width_mm, height_mm };
  });
  const [width, setWidth] = useState(String(label.width_mm));
  const [height, setHeight] = useState(String(label.height_mm));
  const [comment, setComment] = useState("");
  const [media, setMedia] = useState<LabelExportOptions["media"]>("single");
  const [format, setFormat] = useState<LabelExportOptions["format"]>("pdf");
  const [requestedCopies, setRequestedCopies] = useState<number | null>(null);
  const [requestedStart, setRequestedStart] = useState(1);
  const [margin, setMargin] = useState(5);
  const [gap, setGap] = useState(2);
  const [cropMarks, setCropMarks] = useState(false);
  const [showSheet, setShowSheet] = useState(false);
  const [selectedPage, setSelectedPage] = useState({ key: "", number: 1 });
  const [downloading, setDownloading] = useState(false);
  const sourceKey = spoolId === undefined ? `filament-${filamentId}` : `spool-${spoolId}`;
  const codeHint = t(
    spoolId === undefined ? "labelStudio.productCodeHint" : "labelStudio.instanceCodeHint",
  );
  useEffect(() => {
    try {
      sessionStorage.setItem(orientationKey, orientation);
    } catch {
      // Restricted storage must not prevent editing the current label.
    }
  }, [orientation]);
  const metadata = useQuery({
    queryKey: ["label-metadata", sourceKey, locale],
    queryFn: () =>
      spoolId === undefined
        ? labelsAPI.metadata(filamentId, locale)
        : labelsAPI.spoolMetadata(spoolId, locale),
    retry: false,
  });
  const supportsComment =
    label.kind === "full" &&
    Math.min(label.width_mm, label.height_mm) >= 50 &&
    label.width_mm * label.height_mm >= 6000;
  const microLabel =
    label.kind === "full" && Math.min(label.width_mm, label.height_mm) <= 12;
  const grid = labelSheetGrid(
    media === "single" ? undefined : metadata.data?.sheet_media[media],
    label,
    margin,
    gap,
  );
  const validSheet = media === "single" || grid.capacity > 0;
  const cutGuideLimits = labelCutGuideLimits(margin, gap);
  const start = Math.max(1, Math.min(requestedStart, grid.capacity));
  const copies =
    requestedCopies ?? Math.max(1, Math.min(50, grid.capacity - start + 1));
  const pageCount =
    media === "single" || !grid.capacity
      ? 1
      : Math.ceil((start - 1 + copies) / grid.capacity);
  const requiresPdf = media !== "single" && pageCount > 1 && format !== "pdf";
  const options = useMemo<LabelExportOptions>(
    () => ({
      label: {
        ...label,
        locale,
        attribution: microLabel ? "none" : label.attribution,
        comment: supportsComment ? comment : "",
        fields: label.fields.filter(
          (key): key is LabelField =>
            key !== "" &&
            !!metadata.data?.data.fields.some((field) => field[0] === key),
        ),
      },
      format,
      media,
      copies: media === "single" ? 1 : copies,
      start_position: media === "single" ? 1 : start,
      page_margin_mm: margin,
      gap_mm: gap,
      crop_marks: media !== "single" && cropMarks,
    }),
    [
      label,
      locale,
      supportsComment,
      microLabel,
      comment,
      metadata.data,
      format,
      media,
      copies,
      start,
      margin,
      gap,
      cropMarks,
    ],
  );
  const optionsKey = JSON.stringify({ ...options, format: "svg" });
  const previewPage =
    selectedPage.key === optionsKey
      ? Math.min(selectedPage.number, pageCount)
      : 1;
  const debouncedComment = useDebounce(options.label.comment, 180);
  const previewKey = JSON.stringify({
    ...options,
    label: {
      ...options.label,
      comment: supportsComment ? debouncedComment : "",
    },
    format: "svg",
  });
  const preview = useQuery({
    queryKey: ["label-preview", sourceKey, previewKey, previewPage],
    queryFn: ({ signal }) =>
      spoolId === undefined
        ? labelsAPI.preview(
            filamentId,
            JSON.parse(previewKey),
            signal,
            previewPage,
          )
        : labelsAPI.spoolPreview(
            spoolId,
            JSON.parse(previewKey),
            signal,
            previewPage,
          ),
    enabled: !!metadata.data && validSheet,
    placeholderData: keepPreviousData,
    retry: false,
    gcTime: 0,
    staleTime: Infinity,
  });
  const svg =
    showSheet && media !== "single"
      ? preview.data?.page_svg
      : preview.data?.svg;
  const [image, setImage] = useState<{ svg: string; url: string } | null>(null);
  const [imageError, setImageError] = useState(false);
  useEffect(() => {
    if (!svg) return;
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    const next = new Image();
    let cancelled = false,
      published = false;
    setImageError(false);
    next.src = url;
    void next
      .decode()
      .then(() => {
        if (cancelled) return;
        published = true;
        setImage({ svg, url });
      })
      .catch(() => {
        if (!cancelled) setImageError(true);
      });
    return () => {
      cancelled = true;
      if (!published) URL.revokeObjectURL(url);
    };
  }, [svg]);
  useEffect(
    () => () => {
      if (image) URL.revokeObjectURL(image.url);
    },
    [image],
  );
  const current =
    validSheet &&
    previewKey === optionsKey &&
    preview.isSuccess &&
    !preview.isFetching &&
    !preview.isPlaceholderData &&
    image?.svg === svg &&
    !imageError;
  const errorMessage = (error: unknown) =>
    translateApiError(
      t,
      (error as AxiosError<{ detail: unknown }>)?.response?.data?.detail,
      t("labelStudio.failed"),
    );
  const setDimensions = (w: number, h: number) => {
    setLabel((previous) => ({ ...previous, width_mm: w, height_mm: h }));
    setWidth(String(w));
    setHeight(String(h));
  };
  const chooseOrientation = (next: Orientation) => {
    setOrientation(next);
    const [w, h] = orientSize(label.width_mm, label.height_mm, next);
    setDimensions(w, h);
  };
  const applyDimensions = () => {
    const w = Number(width.replace(",", ".")),
      h = Number(height.replace(",", "."));
    if (
      ![w, h].every(
        (value) => Number.isFinite(value) && value >= 8 && value <= 220,
      ) ||
      (label.kind === "classic" && w !== h)
    ) {
      toast.error(t("labelStudio.invalidSize"));
      return;
    }
    setDimensions(w, h);
    if (w !== h) setOrientation(w > h ? "landscape" : "portrait");
  };
  const chooseKind = (kind: LabelOptions["kind"]) => {
    setLabel((previous) => ({
      ...previous,
      kind,
      width_mm:
        kind === "classic"
          ? Math.min(previous.width_mm, previous.height_mm)
          : previous.width_mm,
    }));
    if (kind === "classic") {
      const side = Math.min(label.width_mm, label.height_mm);
      setDimensions(side, side);
    }
  };
  const chooseField = (position: number, key: LabelField | "") =>
    setLabel((previous) => {
      const fields = previous.fields.map((field) =>
        metadata.data?.data.fields.some((entry) => entry[0] === field)
          ? field
          : "",
      );
      const other = key ? fields.indexOf(key) : -1;
      if (other >= 0 && other !== position) fields[other] = fields[position];
      fields[position] = key;
      return { ...previous, fields };
    });
  const download = async () => {
    setDownloading(true);
    try {
      if (spoolId === undefined) {
        await labelsAPI.download(filamentId, options);
      } else {
        await labelsAPI.spoolDownload(spoolId, options);
      }
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setDownloading(false);
    }
  };
  const numberControl = (
    caption: string,
    value: number,
    update: (value: number) => void,
    min: number,
    max: number,
    integer = false,
  ) => (
    <label className="min-w-0 space-y-1 text-sm text-gray-300">
      {caption}
      <input
        className={inputClass}
        type="number"
        min={min}
        max={max}
        step={integer ? 1 : 0.1}
        value={value}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next))
            update(
              Math.min(max, Math.max(min, integer ? Math.floor(next) : next)),
            );
        }}
      />
    </label>
  );

  return (
    <ModalOverlay onClose={onClose} contentClassName="min-h-full p-3 sm:p-6">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="label-studio-title"
        className="mx-auto max-w-7xl rounded-2xl border border-white/15 bg-[#100c20] text-white shadow-2xl"
      >
        <header className="sticky top-0 z-10 flex items-center justify-between gap-4 rounded-t-2xl border-b border-white/10 bg-[#100c20] px-5 py-4">
          <div>
            <h2 id="label-studio-title" className="text-xl font-semibold">
              {t("labelStudio.title")}
            </h2>
            <p className="mt-1 text-sm text-gray-400">
              {codeHint}
            </p>
          </div>
          <button
            className={buttonClass}
            onClick={onClose}
            aria-label={t("common.close")}
          >
            <X size={20} />
          </button>
        </header>
        {metadata.isPending ? (
          <p className="p-6" role="status">
            {t("common.loading")}
          </p>
        ) : metadata.isError ? (
          <div className="space-y-3 p-6" role="alert">
            <p>{errorMessage(metadata.error)}</p>
            <p className="text-gray-400">{codeHint}</p>
          </div>
        ) : (
          metadata.data && (
            <div className="grid items-start gap-6 p-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,1fr)] lg:p-6">
              <div className="lg:sticky lg:top-24">
                <div className="overflow-hidden rounded-2xl border border-white/15">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 p-4">
                    <div>
                      <p className="font-semibold">
                        {label.width_mm} × {label.height_mm}{" "}
                        {t("labelStudio.mm")}
                      </p>
                      <p className="text-xs text-gray-400">
                        {t(`labelStudio.${label.color_mode}`)} · {label.dpi} dpi
                      </p>
                    </div>
                    {media !== "single" && (
                      <button
                        className={buttonClass}
                        onClick={() => setShowSheet((value) => !value)}
                      >
                        {t(
                          showSheet
                            ? "labelStudio.showLabel"
                            : "labelStudio.showSheet",
                        )}
                      </button>
                    )}
                  </div>
                  <div
                    className="flex min-h-60 items-center justify-center bg-[#181126] p-3 sm:p-4"
                    style={{
                      backgroundImage:
                        "linear-gradient(#ffffff07 1px, transparent 1px), linear-gradient(90deg, #ffffff07 1px, transparent 1px)",
                      backgroundSize: "22px 22px",
                    }}
                    aria-busy={!current}
                  >
                    {image ? (
                      <img
                        src={image.url}
                        alt={t("labelStudio.preview")}
                        style={{
                          maxHeight: "max(160px, calc(100dvh - 300px))",
                        }}
                        className="w-full object-contain"
                      />
                    ) : (
                      <p role="status">{t("common.loading")}</p>
                    )}
                  </div>
                  <p
                    role={preview.isError || imageError ? "alert" : "status"}
                    className="min-h-7 px-4 py-1 text-xs text-amber-200"
                  >
                    {!validSheet
                      ? t("labelStudio.sheetDoesNotFit")
                      : preview.isError
                        ? errorMessage(preview.error)
                        : imageError
                          ? t("labelStudio.failed")
                          : !current && image
                            ? t("labelStudio.updating")
                            : ""}
                  </p>
                  {showSheet && media !== "single" && validSheet && (
                    <div className="flex items-center justify-center gap-3 border-t border-white/10 p-2 text-sm">
                      <button
                        className={buttonClass}
                        aria-label={t("labelStudio.previousPage")}
                        disabled={previewPage <= 1}
                        onClick={() =>
                          setSelectedPage({
                            key: optionsKey,
                            number: previewPage - 1,
                          })
                        }
                      >
                        <ChevronLeft size={16} />
                      </button>
                      <span>
                        {t("labelStudio.pageNumber", {
                          page: previewPage,
                          total: pageCount,
                        })}
                      </span>
                      <button
                        className={buttonClass}
                        aria-label={t("labelStudio.nextPage")}
                        disabled={previewPage >= pageCount}
                        onClick={() =>
                          setSelectedPage({
                            key: optionsKey,
                            number: previewPage + 1,
                          })
                        }
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  )}
                  {preview.data && (
                    <div className="grid grid-cols-2 gap-3 border-t border-white/10 p-4 text-xs text-gray-300">
                      <p>
                        {t("labelStudio.matrix")}: {preview.data.modules} ×{" "}
                        {preview.data.modules}
                      </p>
                      <p>
                        {t("labelStudio.dots")}:{" "}
                        {preview.data.scene.dots_per_module.toFixed(1)}
                      </p>
                      <p className="col-span-2 text-amber-200">
                        {!preview.data.printable
                          ? t("labelStudio.tooDense")
                          : preview.data.proof_required
                            ? t("labelStudio.proof")
                            : t("labelStudio.printAt100")}
                      </p>
                    </div>
                  )}
                </div>
              </div>
              <div className="space-y-6">
                <fieldset className="space-y-3">
                  <legend className="mb-2 font-semibold">
                    {t("labelStudio.result")}
                  </legend>
                  <div className="grid grid-cols-2 gap-2">
                    {(["full", "classic"] as const).map((kind) => (
                      <button
                        key={kind}
                        aria-pressed={label.kind === kind}
                        onClick={() => chooseKind(kind)}
                        className={`${buttonClass} ${label.kind === kind ? "!border-cyan-300/70 !bg-cyan-300/10" : ""}`}
                      >
                        {t(`labelStudio.${kind}`)}
                      </button>
                    ))}
                  </div>
                  {label.kind === "classic" && (
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={label.qr_mark}
                        onChange={(event) =>
                          setLabel((previous) => ({
                            ...previous,
                            qr_mark: event.target.checked,
                          }))
                        }
                        className="h-4 w-4 accent-cyan-400"
                      />
                      {t("labelStudio.centerMark")}
                    </label>
                  )}
                </fieldset>
                <fieldset className="space-y-3 border-t border-white/10 pt-4">
                  <legend className="pt-4 font-semibold">
                    {t("labelStudio.size")}
                  </legend>
                  <div
                    className={`grid gap-2 ${label.kind === "classic" ? "grid-cols-4" : "grid-cols-6"}`}
                  >
                    {(label.kind === "classic"
                      ? metadata.data.classic_presets_mm.map((side) => ({
                          width_mm: side,
                          height_mm: side,
                        }))
                      : metadata.data.media_presets
                    ).map((size) => {
                      const [w, h] = orientSize(
                        size.width_mm,
                        size.height_mm,
                        orientation,
                      );
                      return (
                        <button
                          key={`${size.width_mm}-${size.height_mm}`}
                          className={`${buttonClass} min-h-12 min-w-0 !px-1 !py-2.5 !text-sm ${label.width_mm === w && label.height_mm === h ? "!border-cyan-300/70 !bg-cyan-300/10" : ""}`}
                          aria-label={`${w} × ${h}`}
                          aria-pressed={
                            label.width_mm === w && label.height_mm === h
                          }
                          onClick={() => setDimensions(w, h)}
                        >
                          <span className="inline-block">{w}×</span>
                          <wbr />
                          <span className="inline-block">{h}</span>
                        </button>
                      );
                    })}
                  </div>
                  <div
                    className={`grid items-end gap-2 ${label.kind === "full" ? "grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]" : "grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"}`}
                  >
                    <label className="min-w-0 space-y-1 text-xs text-gray-300 sm:text-sm">
                      {t("labelStudio.width")}
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={width}
                        onChange={(event) => setWidth(event.target.value)}
                      />
                    </label>
                    <label className="min-w-0 space-y-1 text-xs text-gray-300 sm:text-sm">
                      {t("labelStudio.height")}
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={height}
                        onChange={(event) => setHeight(event.target.value)}
                      />
                    </label>
                    <button
                      className={buttonClass}
                      onClick={applyDimensions}
                      aria-label={t("labelStudio.apply")}
                    >
                      {t("labelStudio.applyShort")}
                    </button>
                    {label.kind === "full" && (
                      <button
                        type="button"
                        aria-label={t("labelStudio.orientation")}
                        aria-pressed={orientation === "portrait"}
                        title={`${t("labelStudio.orientation")}: ${t(`labelStudio.${orientation}`)}`}
                        onClick={() =>
                          chooseOrientation(
                            orientation === "portrait"
                              ? "landscape"
                              : "portrait",
                          )
                        }
                        className={`${buttonClass} flex min-h-10 items-center gap-2 !px-2 sm:!px-3`}
                      >
                        <ArrowLeftRight
                          size={16}
                          className={
                            orientation === "portrait" ? "rotate-90" : ""
                          }
                        />
                        <span className="hidden sm:inline">
                          {t(`labelStudio.${orientation}`)}
                        </span>
                      </button>
                    )}
                  </div>
                </fieldset>
                <fieldset className="@container space-y-4 border-t border-white/10 pt-4">
                  <legend className="pt-4 font-semibold">
                    {t("labelStudio.content")}
                  </legend>
                  <div className="grid grid-cols-2 gap-3">
                    <Dropdown
                      label={t("labelStudio.printMode")}
                      value={label.color_mode}
                      clearable={false}
                      options={(["mono", "color"] as const).map((value) => ({
                        value,
                        label: t(`labelStudio.${value}`),
                      }))}
                      onChange={(value) =>
                        setLabel((previous) => ({
                          ...previous,
                          color_mode: value as LabelOptions["color_mode"],
                        }))
                      }
                    />
                    <Dropdown
                      label={t("labelStudio.resolution")}
                      value={label.dpi}
                      clearable={false}
                      options={[203, 300, 600].map((value) => ({
                        value,
                        label: `${value} dpi`,
                      }))}
                      onChange={(value) =>
                        setLabel((previous) => ({
                          ...previous,
                          dpi: Number(value) as LabelOptions["dpi"],
                        }))
                      }
                    />
                  </div>
                  {label.kind === "full" && (
                    <>
                      <div>
                        <div className="grid grid-cols-2 divide-x divide-white/10 overflow-hidden rounded-xl border border-white/10">
                          <div className="flex min-w-0 flex-col gap-3 p-3">
                            <div className="flex-1 space-y-1 break-words">
                              <p className="font-medium">
                                {metadata.data.data.brand}
                              </p>
                              <p className="text-xs text-gray-400">
                                {metadata.data.data.material} ·{" "}
                                {metadata.data.data.name}
                              </p>
                            </div>
                            <LabelBrandingControl
                              label={t("labelStudio.brand")}
                              value={label.brand_mode}
                              markAvailable={metadata.data.brand_logo_available}
                              onChange={(brand_mode) =>
                                setLabel((previous) => ({
                                  ...previous,
                                  brand_mode,
                                }))
                              }
                            />
                          </div>
                          <div className="flex min-w-0 flex-col gap-3 p-3">
                            <div className="flex-1 space-y-1">
                              <p className="font-medium">
                                {t("labelStudio.siteName")}
                              </p>
                              <p className="text-xs text-gray-400">
                                {t("labelStudio.outsideQr")}
                              </p>
                            </div>
                            <LabelBrandingControl
                              label={t("labelStudio.attribution")}
                              value={microLabel ? "none" : label.attribution}
                              disabled={microLabel}
                              onChange={(attribution) =>
                                setLabel((previous) => ({
                                  ...previous,
                                  attribution,
                                }))
                              }
                            />
                          </div>
                        </div>
                        {!metadata.data.brand_logo_available && (
                          <p className="mt-2 text-xs text-gray-400">
                            {t("labelStudio.brandLogoUnavailable")}
                          </p>
                        )}
                        {microLabel && (
                          <p className="mt-2 text-xs text-gray-400">
                            {t("labelStudio.microAttribution")}
                          </p>
                        )}
                      </div>
                      <div>
                        <p className="mb-2 text-sm text-gray-300">
                          {t("labelStudio.fields")}
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                          {label.fields.map((key, position) => {
                            const field = metadata.data.data.fields.find(
                              (entry) => entry[0] === key,
                            );
                            return (
                              <div key={position} className="min-w-0">
                                <Dropdown
                                  size="sm"
                                  label={t("labelStudio.fieldPosition", {
                                    position: position + 1,
                                  })}
                                  value={field ? key : ""}
                                  clearable={false}
                                  options={[
                                    {
                                      value: "",
                                      label: t("labelStudio.fieldEmpty"),
                                    },
                                    ...metadata.data.data.fields.map(
                                      ([value, heading]) => ({
                                        value,
                                        label: heading,
                                      }),
                                    ),
                                  ]}
                                  onChange={(value) =>
                                    chooseField(
                                      position,
                                      value as LabelField | "",
                                    )
                                  }
                                />
                                <p className="mt-1 min-h-4 text-xs text-gray-400">
                                  {field?.[2]}
                                </p>
                              </div>
                            );
                          })}
                        </div>
                        <p className="mt-2 text-xs text-gray-400">
                          {t("labelStudio.fieldsHint")}
                        </p>
                      </div>
                      {supportsComment && (
                        <label className="block space-y-2 text-sm text-gray-300">
                          <span>
                            {t("labelStudio.comment")} · {comment.length}/200
                          </span>
                          <textarea
                            rows={4}
                            maxLength={200}
                            value={comment}
                            onChange={(event) => setComment(event.target.value)}
                            className={inputClass}
                          />
                        </label>
                      )}
                      {!supportsComment && comment && (
                        <p className="text-xs text-amber-200">
                          {t("labelStudio.commentUnavailable")}
                        </p>
                      )}
                    </>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <Dropdown
                      label={t("labelStudio.file")}
                      value={format}
                      clearable={false}
                      options={["pdf", "svg", "png"].map((value) => ({
                        value,
                        label: value.toUpperCase(),
                      }))}
                      onChange={(value) =>
                        setFormat(value as LabelExportOptions["format"])
                      }
                    />
                    <Dropdown
                      label={t("labelStudio.media")}
                      value={media}
                      clearable={false}
                      options={(["single", "a4", "letter"] as const).map(
                        (value) => ({
                          value,
                          label: t(`labelStudio.${value}`),
                        }),
                      )}
                      onChange={(value) => {
                        setMedia(value as LabelExportOptions["media"]);
                        setShowSheet(value !== "single");
                      }}
                    />
                  </div>
                  {media !== "single" && (
                    <>
                      <div className="grid grid-cols-2 gap-3 @min-[32rem]:grid-cols-4">
                        {numberControl(
                          t("labelStudio.copies"),
                          copies,
                          setRequestedCopies,
                          1,
                          50,
                          true,
                        )}
                        {numberControl(
                          t("labelStudio.start"),
                          start,
                          setRequestedStart,
                          1,
                          Math.max(1, Math.min(500, grid.capacity)),
                          true,
                        )}
                        {numberControl(
                          t("labelStudio.margin"),
                          margin,
                          setMargin,
                          cropMarks ? cutGuideLimits.minMargin : 0,
                          25,
                        )}
                        {numberControl(
                          t("labelStudio.gap"),
                          gap,
                          setGap,
                          cropMarks ? cutGuideLimits.minGap : 0,
                          cropMarks ? cutGuideLimits.maxGap : 10,
                        )}
                      </div>
                      <p className="text-xs text-gray-400">
                        {t("labelStudio.startHint")}
                      </p>
                    </>
                  )}
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="h-4 w-4 shrink-0 accent-cyan-400"
                        checked={label.border}
                        onChange={(event) =>
                          setLabel((previous) => ({
                            ...previous,
                            border: event.target.checked,
                          }))
                        }
                      />
                      {t("labelStudio.border")}
                    </label>
                    {media !== "single" && (
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          className="h-4 w-4 shrink-0 accent-cyan-400"
                          checked={cropMarks}
                          disabled={!cutGuideLimits.allowed}
                          onChange={(event) =>
                            setCropMarks(event.target.checked)
                          }
                          aria-describedby="label-crop-marks-hint"
                        />
                        {t("labelStudio.cropMarks")}
                      </label>
                    )}
                  </div>
                  {media !== "single" && (
                    <>
                      <p
                        id="label-crop-marks-hint"
                        className="text-xs text-gray-400"
                      >
                        {t("labelStudio.cropMarksHint", {
                          gap: cutGuideLimits.minGap,
                          margin: cutGuideLimits.minMargin,
                        })}
                      </p>
                      {cropMarks && (
                        <p className="text-sm text-gray-300">
                          {t("labelStudio.cutSize", {
                            width: Number((label.width_mm + gap).toFixed(2)),
                            height: Number((label.height_mm + gap).toFixed(2)),
                            allowance: gap / 2,
                          })}
                        </p>
                      )}
                      <button
                        className={buttonClass}
                        disabled={!validSheet}
                        onClick={() => setRequestedCopies(null)}
                      >
                        {t("labelStudio.fillSheet")}
                      </button>
                      <div
                        role="status"
                        className="space-y-1 rounded-xl border border-white/10 p-3 text-sm"
                      >
                        {validSheet ? (
                          <>
                            <p>
                              {t("labelStudio.sheetGrid", {
                                columns: grid.columns,
                                rows: grid.rows,
                                capacity: grid.capacity,
                              })}
                            </p>
                            <p>
                              {t("labelStudio.sheetCount", {
                                copies,
                                pages: pageCount,
                              })}
                            </p>
                          </>
                        ) : (
                          <p className="text-amber-200">
                            {t("labelStudio.sheetDoesNotFit")}
                          </p>
                        )}
                        <p className="text-xs text-gray-400">
                          {t("labelStudio.sheetHint")}
                        </p>
                      </div>
                      {requiresPdf && (
                        <p role="alert" className="text-sm text-amber-200">
                          {t("labelStudio.multiplePdf")}
                        </p>
                      )}
                    </>
                  )}
                  <button
                    disabled={
                      !current ||
                      requiresPdf ||
                      !preview.data?.printable ||
                      preview.isError ||
                      downloading
                    }
                    onClick={() => void download()}
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 py-3 font-semibold text-slate-950 hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Download size={18} />
                    {t(downloading ? "common.loading" : "labelStudio.download")}
                  </button>
                  <p className="text-xs leading-relaxed text-gray-400">
                    {t("labelStudio.printHint")}
                  </p>
                </fieldset>
              </div>
            </div>
          )
        )}
      </section>
    </ModalOverlay>
  );
}
