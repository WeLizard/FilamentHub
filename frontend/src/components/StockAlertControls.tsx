import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, BellOff, Loader2, X } from 'lucide-react';

import {
  stockAlertsAPI,
  type StockAlertRule,
  type StockAlertRulePayload,
  type StockAlertRules,
} from '../api/client';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';
import { parseDecimalInput } from '../utils/decimalInput';
import { stockAlertQueryKeys } from '../utils/spoolQueries';
import { translateApiError } from '../utils/translateApiError';

const FALLBACK_THRESHOLD_G = 100;
const MAX_THRESHOLD_G = 100_000;

export type SpoolAlertState = 'own' | 'default' | 'off';

const sameTarget = (rule: StockAlertRule, payload: Pick<StockAlertRulePayload, 'scope' | 'spool_id' | 'material_key'>) => (
  rule.scope === payload.scope
  && (payload.scope !== 'spool' || rule.spool_id === payload.spool_id)
  && (payload.scope !== 'material' || rule.material_key === payload.material_key)
);

const parseThreshold = (value: string): number | null => {
  const parsed = parseDecimalInput(value);
  return Number.isFinite(parsed) && parsed > 0 && parsed <= MAX_THRESHOLD_G ? Math.round(parsed) : null;
};

function showError(t: ReturnType<typeof useTranslation>['t'], error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  toast.error(translateApiError(t, detail), undefined, 'stock-alerts');
}

export function useStockAlertRules(userId: number | null | undefined) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const queryKey = stockAlertQueryKeys.rules(userId);
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => stockAlertsAPI.rules(signal),
    enabled: !!userId,
    staleTime: 60_000,
  });
  const data = query.data;
  const defaultThreshold = data?.default_threshold_g ?? FALLBACK_THRESHOLD_G;
  const allRule = data?.rules.find((rule) => rule.scope === 'all') ?? null;
  const accountEnabled = !!allRule?.enabled;
  const accountThreshold = allRule?.threshold_g ?? defaultThreshold;

  const spoolRule = (spoolId: number) => data?.rules.find(
    (rule) => rule.scope === 'spool' && rule.spool_id === spoolId && rule.enabled,
  ) ?? null;
  const materialRule = (key: string) => data?.rules.find(
    (rule) => rule.scope === 'material' && rule.material_key === key && rule.enabled,
  ) ?? null;
  const spoolState = (spoolId: number): SpoolAlertState => {
    if (spoolRule(spoolId)) return 'own';
    return accountEnabled ? 'default' : 'off';
  };

  const writeRule = (payload: StockAlertRulePayload, id: number) => {
    queryClient.setQueryData<StockAlertRules>(queryKey, (prev) => {
      const base = prev ?? { default_threshold_g: defaultThreshold, rules: [] };
      const next: StockAlertRule = {
        id,
        scope: payload.scope,
        spool_id: payload.spool_id ?? null,
        material_key: payload.material_key ?? null,
        threshold_g: payload.threshold_g,
        enabled: payload.enabled,
      };
      const index = base.rules.findIndex((rule) => rule.id === id || sameTarget(rule, payload));
      const rules = [...base.rules];
      if (index >= 0) rules[index] = next;
      else rules.push(next);
      return { ...base, rules };
    });
  };

  const save = async (payload: StockAlertRulePayload): Promise<boolean> => {
    const snapshot = queryClient.getQueryData<StockAlertRules>(queryKey);
    const existing = snapshot?.rules.find((rule) => sameTarget(rule, payload));
    writeRule(payload, existing?.id ?? -1);
    try {
      const saved = await stockAlertsAPI.saveRule(payload);
      writeRule({ ...payload, threshold_g: saved.threshold_g, enabled: saved.enabled }, saved.id);
      return true;
    } catch (error) {
      queryClient.setQueryData(queryKey, snapshot);
      showError(t, error);
      return false;
    }
  };

  const remove = async (rule: StockAlertRule): Promise<boolean> => {
    const snapshot = queryClient.getQueryData<StockAlertRules>(queryKey);
    queryClient.setQueryData<StockAlertRules>(queryKey, (prev) => prev && ({
      ...prev,
      rules: prev.rules.map((item) => (item.id === rule.id ? { ...item, enabled: false } : item)),
    }));
    try {
      await stockAlertsAPI.deleteRule(rule.id);
      return true;
    } catch (error) {
      queryClient.setQueryData(queryKey, snapshot);
      showError(t, error);
      return false;
    }
  };

  return {
    isLoading: query.isPending,
    defaultThreshold,
    accountEnabled,
    accountThreshold,
    spoolRule,
    materialRule,
    spoolState,
    save,
    remove,
  };
}

export type StockAlertRulesApi = ReturnType<typeof useStockAlertRules>;

interface ThresholdInputProps {
  value: string;
  onChange: (value: string) => void;
  onCommit?: () => void;
  disabled?: boolean;
  label: string;
}

function ThresholdInput({ value, onChange, onCommit, disabled, label }: ThresholdInputProps) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1">
      <input
        inputMode="numeric"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onCommit}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && onCommit) {
            event.preventDefault();
            onCommit();
          }
        }}
        disabled={disabled}
        aria-label={label}
        className="w-16 rounded-md border border-white/20 bg-white/5 px-2 py-0.5 text-right text-sm text-white focus:border-purple-500 focus:outline-none disabled:opacity-50"
      />
      <span className="text-xs text-gray-400">{t('common.unitGram')}</span>
    </span>
  );
}

export function StockAlertDefaultControl({ alerts }: { alerts: StockAlertRulesApi }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(String(Math.round(alerts.accountThreshold)));

  useEffect(() => {
    setDraft(String(Math.round(alerts.accountThreshold)));
  }, [alerts.accountThreshold]);

  const save = async (enabled: boolean, threshold: number) => {
    await alerts.save({ scope: 'all', threshold_g: threshold, enabled });
  };

  const commitThreshold = () => {
    const threshold = parseThreshold(draft);
    if (threshold === null) {
      setDraft(String(Math.round(alerts.accountThreshold)));
      return;
    }
    if (threshold !== Math.round(alerts.accountThreshold)) void save(true, threshold);
  };

  return (
    <div className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 py-1 pl-1 pr-2 text-sm">
      <button
        type="button"
        onClick={() => void save(!alerts.accountEnabled, Math.round(alerts.accountThreshold))}
        disabled={alerts.isLoading}
        aria-pressed={alerts.accountEnabled}
        title={t('profilePage.stockAlerts.defaultHint')}
        className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 transition-colors disabled:opacity-50 ${
          alerts.accountEnabled ? 'bg-purple-500/25 text-white' : 'text-gray-300 hover:bg-white/10'
        }`}
      >
        {alerts.accountEnabled ? <Bell className="h-3.5 w-3.5" /> : <BellOff className="h-3.5 w-3.5" />}
        <span>{t('profilePage.stockAlerts.toggle')}</span>
      </button>
      {alerts.accountEnabled && (
        <span className="inline-flex items-center gap-1 text-xs text-gray-400">
          {t('profilePage.stockAlerts.below')}
          <ThresholdInput
            value={draft}
            onChange={setDraft}
            onCommit={commitThreshold}
            label={t('profilePage.stockAlerts.thresholdLabel')}
          />
        </span>
      )}
    </div>
  );
}

export type StockAlertTarget =
  | { scope: 'spool'; spoolId: number; name: string }
  | { scope: 'material'; materialKey: string; name: string };

interface StockAlertRuleModalProps {
  target: StockAlertTarget;
  alerts: StockAlertRulesApi;
  onClose: () => void;
}

export function StockAlertRuleModal({ target, alerts, onClose }: StockAlertRuleModalProps) {
  const { t } = useTranslation();
  const rule = target.scope === 'spool' ? alerts.spoolRule(target.spoolId) : alerts.materialRule(target.materialKey);
  const initial = rule?.threshold_g
    ?? (target.scope === 'spool' && alerts.accountEnabled ? alerts.accountThreshold : alerts.defaultThreshold);
  const [draft, setDraft] = useState(String(Math.round(initial)));
  const [busy, setBusy] = useState(false);
  const threshold = parseThreshold(draft);

  let status: string;
  if (target.scope === 'material') {
    status = rule
      ? t('profilePage.stockAlerts.materialOn', { threshold: Math.round(rule.threshold_g) })
      : t('profilePage.stockAlerts.materialOff');
  } else if (rule) {
    status = t('profilePage.stockAlerts.spoolOwn', { threshold: Math.round(rule.threshold_g) });
  } else if (alerts.accountEnabled) {
    status = t('profilePage.stockAlerts.spoolDefault', { threshold: Math.round(alerts.accountThreshold) });
  } else {
    status = t('profilePage.stockAlerts.spoolDefaultOff');
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (threshold === null || busy) return;
    setBusy(true);
    const ok = await alerts.save(target.scope === 'spool'
      ? { scope: 'spool', spool_id: target.spoolId, threshold_g: threshold, enabled: true }
      : { scope: 'material', material_key: target.materialKey, threshold_g: threshold, enabled: true });
    setBusy(false);
    if (ok) onClose();
  };

  const removeRule = async () => {
    if (!rule || busy) return;
    setBusy(true);
    const ok = await alerts.remove(rule);
    setBusy(false);
    if (ok) onClose();
  };

  return (
    <ModalOverlay onClose={onClose}>
      <form
        role="dialog"
        aria-label={t('profilePage.stockAlerts.title')}
        onSubmit={submit}
        className="glass-panel w-full max-w-sm space-y-3 rounded-2xl border border-white/20 p-4 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="flex items-center gap-2 text-base font-semibold text-white">
              <Bell className="h-4 w-4 text-purple-300" aria-hidden />
              {t('profilePage.stockAlerts.title')}
            </h3>
            <p className="mt-0.5 truncate text-xs text-gray-400">{target.name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            title={t('common.close')}
            aria-label={t('common.close')}
            className="rounded-lg p-1 text-gray-400 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-gray-300">{status}</p>
        {target.scope === 'material' && (
          <p className="text-[11px] leading-relaxed text-gray-500">{t('profilePage.stockAlerts.materialNote')}</p>
        )}

        <label className="flex flex-wrap items-center gap-2 text-sm text-gray-200">
          <span>{t(target.scope === 'spool' ? 'profilePage.stockAlerts.ownThreshold' : 'profilePage.stockAlerts.materialThreshold')}</span>
          <ThresholdInput value={draft} onChange={setDraft} label={t('profilePage.stockAlerts.thresholdLabel')} />
        </label>

        <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
          {rule && (
            <button
              type="button"
              onClick={() => void removeRule()}
              disabled={busy}
              className="mr-auto rounded-lg px-2 py-1.5 text-xs text-gray-400 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
            >
              {t(target.scope === 'spool' ? 'profilePage.stockAlerts.useDefault' : 'profilePage.stockAlerts.turnOff')}
            </button>
          )}
          <button
            type="submit"
            disabled={busy || threshold === null}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-1.5 text-sm font-medium text-white transition hover:from-purple-700 hover:to-pink-700 disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('common.save')}
          </button>
        </div>
      </form>
    </ModalOverlay>
  );
}
