import { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Plus, X, Loader2, CheckCircle } from 'lucide-react';
import { filamentLinesAPI, filamentsAPI } from '../api/client';
import { densityForMaterial, STANDARD_DIAMETERS } from '../utils/materialDensity';
import { currencySymbol } from '../utils/currency';
import { HSLColorPicker } from './HSLColorPicker';
import { Dropdown } from './Dropdown';
import { MaterialTypeSelect } from './MaterialTypeSelect';
import { AvailabilitySelect } from './AvailabilitySelect';
import { PriceUnitField } from './PriceUnitField';
import { translateApiError } from '../utils/translateApiError';
import type { FilamentAvailability, FilamentImportResult, FilamentPalettePayload } from '../types/api';

interface PaletteEntry {
  color_name: string;
  color_hex: string;
  name: string; // переопределение авто-имени (пусто = авто)
}

interface FilamentPaletteFormProps {
  brandId: number;
  onClose: () => void;
}

const emptyEntry = (): PaletteEntry => ({ color_name: '', color_hex: '#808080', name: '' });

/** Создание набора цветов-вариантов в одной линейке (палитра). */
export function FilamentPaletteForm({ brandId, onClose }: FilamentPaletteFormProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const { data: lines = [] } = useQuery({
    queryKey: ['brand-lines', brandId],
    queryFn: () => filamentLinesAPI.list(brandId),
  });

  const { data: materialTypes = [] } = useQuery({
    queryKey: ['filaments', 'material-types'],
    queryFn: () => filamentsAPI.getMaterialTypes(),
  });

  const [lineId, setLineId] = useState<number | ''>('');
  const [newLineName, setNewLineName] = useState('');
  const [materialType, setMaterialType] = useState('');
  const [diameter, setDiameter] = useState(1.75);
  const [density, setDensity] = useState(1.24);
  const [priceMode, setPriceMode] = useState<'per_kg' | 'per_spool'>('per_kg');
  const [pricePerKg, setPricePerKg] = useState(0);
  const [pricePerSpool, setPricePerSpool] = useState(0);
  const [spoolWeight, setSpoolWeight] = useState(1000);
  const [availability, setAvailability] = useState<FilamentAvailability>('available');
  const [entries, setEntries] = useState<PaletteEntry[]>([emptyEntry(), emptyEntry(), emptyEntry()]);
  const [openPicker, setOpenPicker] = useState<number | null>(null);
  const [pasteText, setPasteText] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<FilamentImportResult | null>(null);

  // Авто-плотность по материалу (как в основной форме).
  useEffect(() => {
    const d = densityForMaterial(materialType);
    if (d) setDensity(d);
  }, [materialType]);

  // Синхронизация цены за кг ↔ за катушку (как в основной форме).
  useEffect(() => {
    if (priceMode === 'per_kg' && spoolWeight > 0 && pricePerKg > 0) {
      setPricePerSpool((pricePerKg * spoolWeight) / 1000);
    }
  }, [priceMode, pricePerKg, spoolWeight]);
  useEffect(() => {
    if (priceMode === 'per_spool' && spoolWeight > 0 && pricePerSpool > 0) {
      setPricePerKg((pricePerSpool / spoolWeight) * 1000);
    }
  }, [priceMode, pricePerSpool, spoolWeight]);

  const lineName = lineId !== '' ? (lines.find((l) => l.id === lineId)?.name ?? '') : newLineName.trim();
  const filledEntries = entries.filter((e) => e.color_name.trim());

  const updateEntry = (i: number, patch: Partial<PaletteEntry>) =>
    setEntries((prev) => prev.map((e, j) => (j === i ? { ...e, ...patch } : e)));
  const removeEntry = (i: number) => setEntries((prev) => prev.filter((_, j) => j !== i));
  const addEntry = () => setEntries((prev) => [...prev, emptyEntry()]);

  const applyPaste = () => {
    const names = pasteText
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!names.length) return;
    setEntries((prev) => [
      ...prev.filter((e) => e.color_name.trim()),
      ...names.map((n) => ({ ...emptyEntry(), color_name: n })),
    ]);
    setPasteText('');
  };

  const handleSubmit = async () => {
    setError('');
    if (!materialType.trim()) {
      setError(t('palette.errorMaterial'));
      return;
    }
    if (lineId === '' && !newLineName.trim()) {
      setError(t('palette.errorLine'));
      return;
    }
    if (!filledEntries.length) {
      setError(t('palette.errorNoColors'));
      return;
    }

    setSubmitting(true);
    try {
      let targetLineId = lineId === '' ? 0 : lineId;
      if (targetLineId === 0) {
        const created = await filamentLinesAPI.create(brandId, newLineName.trim());
        targetLineId = created.id;
        queryClient.invalidateQueries({ queryKey: ['brand-lines', brandId] });
      }

      const payload: FilamentPalettePayload = {
        material_type: materialType.trim(),
        diameter,
        density: density || null,
        price_per_kg: pricePerKg || null,
        spool_weight: spoolWeight || null,
        price_display_unit: priceMode,
        availability,
        variants: filledEntries.map((e) => ({
          color_name: e.color_name.trim(),
          color_hex: e.color_hex || null,
          name: e.name.trim() || null,
        })),
      };
      const res = await filamentLinesAPI.createVariants(targetLineId, payload);
      setResult(res);
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(translateApiError(t, detail, t('palette.errorGeneric')));
    } finally {
      setSubmitting(false);
    }
  };

  // Сводка после создания.
  if (result) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-green-300">
          <CheckCircle className="w-5 h-5" />
          <span className="font-semibold">{t('palette.doneTitle')}</span>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="bg-green-500/10 border border-green-500/30 rounded-xl py-3">
            <div className="text-2xl font-bold text-green-300">{result.created}</div>
            <div className="text-xs text-gray-400">{t('palette.created')}</div>
          </div>
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl py-3">
            <div className="text-2xl font-bold text-yellow-300">{result.skipped}</div>
            <div className="text-xs text-gray-400">{t('palette.skipped')}</div>
          </div>
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl py-3">
            <div className="text-2xl font-bold text-red-300">{result.errors}</div>
            <div className="text-xs text-gray-400">{t('palette.errorsCount')}</div>
          </div>
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all"
          >
            {t('palette.close')}
          </button>
        </div>
      </div>
    );
  }

  const inputClass =
    'w-full px-4 py-2.5 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500';

  return (
    <div className="space-y-5">
      {/* Линейка */}
      <div>
        <label className="block text-gray-300 mb-1 text-sm font-medium">{t('palette.lineLabel')}</label>
        <p className="text-gray-500 text-xs mb-2">{t('palette.lineHint')}</p>
        <div className="flex flex-col sm:flex-row gap-2">
          <select
            value={lineId === '' ? '' : String(lineId)}
            onChange={(e) => setLineId(e.target.value === '' ? '' : Number(e.target.value))}
            className={inputClass + ' sm:flex-1'}
          >
            <option value="" className="bg-gray-900">{t('palette.lineNew')}</option>
            {lines.map((l) => (
              <option key={l.id} value={l.id} className="bg-gray-900">{l.name}</option>
            ))}
          </select>
          {lineId === '' && (
            <input
              type="text"
              value={newLineName}
              onChange={(e) => setNewLineName(e.target.value)}
              placeholder={t('palette.lineNewPlaceholder')}
              maxLength={200}
              className={inputClass + ' sm:flex-1'}
            />
          )}
        </div>
      </div>

      {/* Общие параметры */}
      <div>
        <h4 className="text-sm font-medium text-gray-300 mb-2">{t('palette.sharedTitle')}</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <MaterialTypeSelect
            label={t('createFilament.materialTypeLabel')}
            value={materialType}
            onChange={setMaterialType}
            options={materialTypes}
            placeholder={t('palette.materialPlaceholder')}
          />
          <Dropdown
            label={t('palette.diameter')}
            value={diameter}
            options={STANDARD_DIAMETERS.map((d) => ({ value: d, label: `${d} ${t('palette.mm')}` }))}
            onChange={(val) => setDiameter(Number(val))}
          />
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('createFilament.densityLabel')}</label>
            <input
              type="number"
              value={density}
              onChange={(e) => setDensity(Number(e.target.value))}
              min={0.1}
              max={25}
              step="0.01"
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              placeholder="1.24"
            />
          </div>
          <AvailabilitySelect value={availability} onChange={setAvailability} />
        </div>
        <div className="mt-3">
          <PriceUnitField
            priceMode={priceMode}
            onPriceModeChange={setPriceMode}
            pricePerKg={pricePerKg}
            onPricePerKgChange={setPricePerKg}
            pricePerSpool={pricePerSpool}
            onPricePerSpoolChange={setPricePerSpool}
            spoolWeight={spoolWeight}
            onSpoolWeightChange={setSpoolWeight}
            currencySymbol={currencySymbol('RUB')}
          />
        </div>
      </div>

      {/* Палитра-доска */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-gray-300">{t('palette.colorsTitle')}</h4>
          <button
            type="button"
            onClick={addEntry}
            className="flex items-center gap-1 px-3 py-1.5 bg-white/10 hover:bg-white/20 border border-white/20 rounded-lg text-sm text-gray-200 transition-all"
          >
            <Plus className="w-4 h-4" /> {t('palette.addColor')}
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {entries.map((entry, i) => (
            <div key={i} className="relative bg-white/5 border border-white/10 rounded-xl p-3 flex flex-col items-center gap-2">
              <button
                type="button"
                onClick={() => removeEntry(i)}
                className="absolute top-1 right-1 p-1 text-gray-500 hover:text-red-400 transition-colors"
                title={t('palette.removeColor')}
              >
                <X className="w-3.5 h-3.5" />
              </button>
              <HSLColorPicker
                color={entry.color_hex}
                onChange={(hex) => updateEntry(i, { color_hex: hex })}
                isOpen={openPicker === i}
                onToggle={(open) => setOpenPicker(open ? i : null)}
                showTrigger
                triggerClassName="w-14 h-14 rounded-xl border border-white/20 cursor-pointer shadow-inner"
              />
              <input
                type="text"
                value={entry.color_name}
                onChange={(e) => updateEntry(i, { color_name: e.target.value })}
                placeholder={t('palette.colorNamePlaceholder')}
                maxLength={100}
                className="w-full px-2 py-1 text-sm text-center bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
              />
              {entry.color_name.trim() && (
                <span className="text-[11px] text-gray-500 text-center truncate w-full" title={`${lineName} ${entry.color_name}`.trim()}>
                  {`${lineName} ${entry.color_name.trim()}`.trim()}
                </span>
              )}
            </div>
          ))}
        </div>

        {/* Быстрая вставка списка */}
        <div className="mt-3 flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={t('palette.pastePlaceholder')}
            className={inputClass + ' sm:flex-1'}
          />
          <button
            type="button"
            onClick={applyPaste}
            disabled={!pasteText.trim()}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 border border-white/20 rounded-xl text-sm text-gray-200 transition-all disabled:opacity-50 whitespace-nowrap"
          >
            {t('palette.pasteApply')}
          </button>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex items-center justify-between pt-2 border-t border-white/10">
        <span className="text-sm text-gray-400">
          {t('palette.willCreate', { count: filledEntries.length, line: lineName || '—' })}
        </span>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-5 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50"
          >
            {t('palette.cancel')}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || !filledEntries.length}
            className="px-6 py-2.5 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all disabled:opacity-50 flex items-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {t('palette.submit')}
          </button>
        </div>
      </div>
    </div>
  );
}
