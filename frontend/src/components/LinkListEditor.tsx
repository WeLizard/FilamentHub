import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SocialIcon } from './socialIcons';

export interface ShopLink {
  platform: string;
  url: string;
}

type LinkItem = string | ShopLink;

interface LinkListEditorProps {
  kind: 'social' | 'shop';
  value: unknown;
  onChange: (value: string[] | ShopLink[]) => void;
  disabled?: boolean;
  label: string;
}

function parseList(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value !== 'string' || !value.trim()) return [];
  if (value.trim().startsWith('[')) {
    try {
      const parsed: unknown = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed;
    } catch { /* Fall through to the plain-text form. */ }
  }
  return value.split(';').map((item) => item.trim()).filter(Boolean);
}

function normalize(kind: 'social' | 'shop', value: unknown): LinkItem[] {
  return parseList(value).map((item) => {
    if (kind === 'social') {
      return typeof item === 'string' ? item : String((item as ShopLink | null)?.url ?? '');
    }
    if (item && typeof item === 'object') {
      const link = item as Partial<ShopLink>;
      return { platform: String(link.platform ?? ''), url: String(link.url ?? '') };
    }
    return { platform: '', url: String(item ?? '') };
  });
}

const urlOf = (item: LinkItem) => (typeof item === 'string' ? item : item.url);

const fieldClass = 'h-9 min-w-0 flex-1 rounded-lg border border-white/15 bg-slate-950/70 px-2.5 text-sm text-white placeholder:text-gray-500 focus:border-indigo-400 focus:outline-none disabled:opacity-60';

/** Compact list-of-links editor shared by the brand profile fields (social networks, shops). */
export function LinkListEditor({ kind, value, onChange, disabled = false, label }: LinkListEditorProps) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<LinkItem[]>(() => normalize(kind, value));
  const emit = (next: LinkItem[]) => {
    setRows(next);
    onChange(next.filter((item) => urlOf(item).trim()) as string[] | ShopLink[]);
  };

  const external = JSON.stringify(normalize(kind, value));
  useEffect(() => {
    setRows((current) => JSON.stringify(current.filter((item) => urlOf(item).trim())) === external
      ? current : normalize(kind, JSON.parse(external) as unknown));
  }, [external, kind]);

  return (
    <div className="space-y-1.5">
      {rows.map((item, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-gray-300">
            <SocialIcon url={urlOf(item)} className="h-4 w-4" kind={kind === 'shop' ? 'shop' : undefined} />
          </span>
          {kind === 'shop' && typeof item !== 'string' && (
            <input type="text" aria-label={`${label} ${index + 1} · ${t('brandProfile.shopPlatformPlaceholder')}`}
              disabled={disabled} value={item.platform} placeholder={t('brandProfile.shopPlatformPlaceholder')}
              onChange={(event) => emit(rows.map((row, i) => i === index ? { ...(row as ShopLink), platform: event.target.value } : row))}
              className={`${fieldClass} w-24 flex-none sm:w-28`} />
          )}
          <input type="url" aria-label={`${label} ${index + 1}`} disabled={disabled} value={urlOf(item)} placeholder="https://..."
            onChange={(event) => emit(rows.map((row, i) => i === index
              ? (typeof row === 'string' ? event.target.value : { ...row, url: event.target.value }) : row))}
            className={fieldClass} />
          {!disabled && (
            <button type="button" aria-label={`${t('adminCatalogImport.curation.removeListItem')} ${index + 1}`}
              onClick={() => emit(rows.filter((_, i) => i !== index))}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 text-gray-300 transition hover:bg-red-500/20">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      ))}
      {!disabled && (
        <button type="button"
          onClick={() => setRows([...rows, kind === 'shop' ? { platform: '', url: '' } : ''])}
          className="text-sm text-purple-300 transition hover:text-purple-200">
          + {t('brandProfile.addLink')}
        </button>
      )}
    </div>
  );
}
