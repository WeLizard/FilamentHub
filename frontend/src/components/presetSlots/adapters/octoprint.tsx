import { useTranslation } from 'react-i18next';
import { AlertTriangle, ExternalLink } from 'lucide-react';

import type { FeedAdapter } from './types';

const PLUGIN_PAGE = 'https://plugins.octoprint.org/plugins/Spoolman/';

function SetupStep() {
  const { t } = useTranslation();

  return (
    <div className="mb-3 rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-300" />
        <span className="text-xs font-medium text-amber-100">
          {t('presetSlots.octoprint.setupTitle')}
        </span>
        <a
          href={PLUGIN_PAGE}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[11px] text-amber-200 transition hover:bg-white/10 hover:text-amber-100"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          {t('presetSlots.octoprint.pluginPage')}
        </a>
      </div>
      <p className="mt-1 text-[11px] leading-4 text-amber-100/70">
        {t('presetSlots.octoprint.setupDescription')}
      </p>
    </div>
  );
}

export const octoprintAdapter: FeedAdapter = {
  id: 'octoprint',
  labelKey: 'presetSlots.feedSystem.octoprint',
  fixedSlots: null,
  capabilities: ['read', 'write', 'spool_identity', 'consumption'],
  link: {
    hintKey: 'presetSlots.octoprint.linkHint',
    // The plugin appends /api/v1 itself and supports keeping the secret in a
    // dedicated request header instead of leaking it through its URL.
    snippet: (baseUrl) => baseUrl,
    apiKeyHeader: 'X-API-Key',
  },
  renderSetup: ({ linkConfirmed }) => (linkConfirmed ? null : <SetupStep />),
};
