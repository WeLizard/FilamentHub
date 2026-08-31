import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Download, X } from "lucide-react";
import type { AxiosError } from "axios";
import { labelsAPI } from "../api/client";
import { useDebounce } from "../hooks/useDebounce";
import type {
  LabelExportOptions,
  LabelField,
  LabelOptions,
} from "../types/labels";
import { translateApiError } from "../utils/translateApiError";
import { ModalOverlay } from "./ModalOverlay";
import { Dropdown } from "./Dropdown";
import { toast } from "./Toast";

const initialLabel: LabelOptions = {
  width_mm: 50,
  height_mm: 30,
  kind: "full",
  color_mode: "mono",
  dpi: 203,
  locale: "ru",
  attribution: "full",
  qr_mark: false,
  brand_logo: true,
  fields: ["nozzle", "bed", "drying", "abrasiveness", "diameter", "density"],
  comment: "",
};
const inputClass =
  "w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white focus:border-cyan-300 focus:outline-none";
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
  onClose,
}: {
  filamentId: number;
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
  const [copies, setCopies] = useState(1);
  const [start, setStart] = useState(1);
  const [margin, setMargin] = useState(5);
  const [gap, setGap] = useState(2);
  const [showSheet, setShowSheet] = useState(false);
  const [downloading, setDownloading] = useState(false);
  useEffect(() => {
    try {
      sessionStorage.setItem(orientationKey, orientation);
    } catch {
      // Restricted storage must not prevent editing the current label.
    }
  }, [orientation]);
  const metadata = useQuery({
    queryKey: ["label-metadata", filamentId, locale],
    queryFn: () => labelsAPI.metadata(filamentId, locale),
    retry: false,
  });
  const supportsComment =
    label.kind === "full" &&
    Math.min(label.width_mm, label.height_mm) >= 50 &&
    label.width_mm * label.height_mm >= 6000;
  const microLabel =
    label.kind === "full" && Math.min(label.width_mm, label.height_mm) <= 12;
  const options = useMemo<LabelExportOptions>(
    () => ({
      label: {
        ...label,
        locale,
        attribution: microLabel ? "none" : label.attribution,
        comment: supportsComment ? comment : "",
        fields: label.fields.filter((key) =>
          metadata.data?.data.fields.some((field) => field[0] === key),
        ),
      },
      format,
      media,
      copies: media === "single" ? 1 : copies,
      start_position: media === "single" ? 1 : start,
      page_margin_mm: margin,
      gap_mm: gap,
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
    ],
  );
  const optionsKey = JSON.stringify({ ...options, format: "svg" });
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
    queryKey: ["label-preview", filamentId, previewKey],
    queryFn: ({ signal }) =>
      labelsAPI.preview(filamentId, JSON.parse(previewKey), signal),
    enabled: !!metadata.data,
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
  const chooseField = (key: LabelField) =>
    setLabel((previous) => ({
      ...previous,
      fields: previous.fields.includes(key)
        ? previous.fields.filter((field) => field !== key)
        : [
            ...previous.fields.filter((field) =>
              metadata.data?.data.fields.some((entry) => entry[0] === field),
            ),
            key,
          ].slice(0, 6),
    }));
  const download = async () => {
    setDownloading(true);
    try {
      await labelsAPI.download(filamentId, options);
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
  ) => (
    <label className="space-y-1 text-sm text-gray-300">
      {caption}
      <input
        className={inputClass}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) update(Math.min(max, Math.max(min, next)));
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
              {t("labelStudio.publicHint")}
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
            <p className="text-gray-400">{t("labelStudio.personalHint")}</p>
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
                    {preview.isError
                      ? errorMessage(preview.error)
                      : imageError
                        ? t("labelStudio.failed")
                        : !current && image
                          ? t("labelStudio.updating")
                          : ""}
                  </p>
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
                  <div className="grid grid-cols-3 gap-2">
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
                          className={buttonClass}
                          aria-pressed={
                            label.width_mm === w && label.height_mm === h
                          }
                          onClick={() => setDimensions(w, h)}
                        >
                          {w} × {h}
                        </button>
                      );
                    })}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="space-y-1 text-sm text-gray-300">
                      {t("labelStudio.width")}
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={width}
                        onChange={(event) => setWidth(event.target.value)}
                      />
                    </label>
                    <label className="space-y-1 text-sm text-gray-300">
                      {t("labelStudio.height")}
                      <input
                        className={inputClass}
                        inputMode="decimal"
                        value={height}
                        onChange={(event) => setHeight(event.target.value)}
                      />
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <button className={buttonClass} onClick={applyDimensions}>
                      {t("labelStudio.apply")}
                    </button>
                  </div>
                  {label.kind === "full" && (
                    <div
                      role="group"
                      aria-label={t("labelStudio.orientation")}
                      className="grid grid-cols-2 gap-2"
                    >
                      {(["landscape", "portrait"] as const).map((value) => (
                        <button
                          key={value}
                          onClick={() => chooseOrientation(value)}
                          aria-pressed={orientation === value}
                          className={`${buttonClass} ${orientation === value ? "!border-cyan-300/70 !bg-cyan-300/10" : ""}`}
                        >
                          {t(`labelStudio.${value}`)}
                        </button>
                      ))}
                    </div>
                  )}
                </fieldset>
                <fieldset className="space-y-4 border-t border-white/10 pt-4">
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
                      <div className="rounded-xl border border-white/10 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium">
                            {metadata.data.data.brand}
                          </span>
                          <label className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-cyan-400"
                              checked={
                                label.brand_logo &&
                                metadata.data.brand_logo_available
                              }
                              disabled={!metadata.data.brand_logo_available}
                              onChange={(event) =>
                                setLabel((previous) => ({
                                  ...previous,
                                  brand_logo: event.target.checked,
                                }))
                              }
                            />
                            {t("labelStudio.brandLogo")}
                          </label>
                        </div>
                        <p className="mt-2 text-sm text-gray-400">
                          {metadata.data.data.material} ·{" "}
                          {metadata.data.data.name}
                        </p>
                      </div>
                      {microLabel ? (
                        <p className="text-sm text-gray-400">
                          {t("labelStudio.microAttribution")}
                        </p>
                      ) : (
                        <Dropdown
                          label={t("labelStudio.attribution")}
                          value={label.attribution}
                          clearable={false}
                          options={(["full", "mark", "none"] as const).map(
                            (value) => ({
                              value,
                              label: t(`labelStudio.attribution_${value}`),
                            }),
                          )}
                          onChange={(value) =>
                            setLabel((previous) => ({
                              ...previous,
                              attribution: value as LabelOptions["attribution"],
                            }))
                          }
                        />
                      )}
                      <div>
                        <p className="mb-2 text-sm text-gray-300">
                          {t("labelStudio.fields")}
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                          {metadata.data.data.fields.map(
                            ([key, heading, value]) => (
                              <label
                                key={key}
                                className="flex items-start gap-2 text-sm"
                              >
                                <input
                                  type="checkbox"
                                  className="mt-1 h-4 w-4 shrink-0 accent-cyan-400"
                                  checked={label.fields.includes(key)}
                                  disabled={
                                    !label.fields.includes(key) &&
                                    options.label.fields.length >= 6
                                  }
                                  onChange={() => chooseField(key)}
                                />
                                <span>
                                  {heading}
                                  <small className="block text-gray-400">
                                    {value}
                                  </small>
                                </span>
                              </label>
                            ),
                          )}
                        </div>
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
                </fieldset>
                <fieldset className="space-y-3 border-t border-white/10 pt-4">
                  <legend className="pt-4 font-semibold">
                    {t("labelStudio.export")}
                  </legend>
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
                      onChange={(value) =>
                        setMedia(value as LabelExportOptions["media"])
                      }
                    />
                  </div>
                  {media !== "single" && (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        {numberControl(
                          t("labelStudio.copies"),
                          copies,
                          setCopies,
                          1,
                          50,
                        )}
                        {numberControl(
                          t("labelStudio.start"),
                          start,
                          setStart,
                          1,
                          500,
                        )}
                        {numberControl(
                          t("labelStudio.margin"),
                          margin,
                          setMargin,
                          0,
                          25,
                        )}
                        {numberControl(
                          t("labelStudio.gap"),
                          gap,
                          setGap,
                          0,
                          10,
                        )}
                      </div>
                      <p className="text-xs text-gray-400">
                        {t("labelStudio.oneSheet")}
                      </p>
                    </>
                  )}
                  <button
                    disabled={
                      !current ||
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
