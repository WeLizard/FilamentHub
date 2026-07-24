import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Download, PackageSearch } from 'lucide-react';
import { ModalOverlay } from './ModalOverlay';
import type { RecoverItem } from '../utils/pluginBridge';

interface RecoverPresetsModalProps {
  items: RecoverItem[];
  onClose: () => void;
  onImport: (names: string[]) => void;
}

export function RecoverPresetsModal({ items, onClose, onImport }: RecoverPresetsModalProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(items.filter((i) => !i.imported).map((i) => i.name)),
  );

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const allSelected = items.length > 0 && selected.size === items.length;
  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(items.map((i) => i.name)));
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-2xl border border-white/20 bg-gray-900">
        <div className="flex items-center justify-between border-b border-white/10 p-5">
          <h3 className="flex items-center gap-2 text-lg font-bold text-white">
            <PackageSearch className="h-5 w-5 text-purple-400" />
            {t('recover.title')}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white" aria-label={t('recover.close')}>
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="px-5 pt-4 text-sm text-gray-400">
          {items.length > 0 ? t('recover.found', { count: items.length }) : t('recover.empty')}
        </p>

        {items.length > 0 && (
          <>
            <div className="px-5 pt-3">
              <button onClick={toggleAll} className="text-xs text-purple-300 hover:text-purple-200">
                {allSelected ? t('recover.deselectAll') : t('recover.selectAll')}
              </button>
            </div>
            <div className="flex-1 space-y-1 overflow-y-auto px-5 py-3">
              {items.map((item) => (
                <label
                  key={item.name}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 hover:bg-white/5"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(item.name)}
                    onChange={() => toggle(item.name)}
                    className="h-4 w-4 accent-purple-600"
                  />
                  <span className="flex-1 truncate text-sm text-gray-200">{item.name}</span>
                  {item.imported && (
                    <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[11px] text-gray-400">
                      {t('recover.alreadyImported')}
                    </span>
                  )}
                </label>
              ))}
            </div>
          </>
        )}

        <div className="flex justify-end gap-2 border-t border-white/10 p-5">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-gray-300 hover:bg-white/10">
            {t('recover.cancel')}
          </button>
          <button
            onClick={() => onImport([...selected])}
            disabled={selected.size === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm text-white transition-colors hover:bg-purple-500 disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            {t('recover.import', { count: selected.size })}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}
