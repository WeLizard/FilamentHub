import { Loader2, Nfc } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  edgeTagStationErrorText,
  identifyStationTag,
  useEdgeTagStation,
  type StationTagIntake,
} from '../hooks/useEdgeTagStation';
import { translateApiError } from '../utils/translateApiError';
import { toast } from './Toast';

/**
 * Reads any tag on the station: a tag of one of the person's spools opens that
 * spool, any other tag starts a new spool from what the tag says.
 */
export function ReadSpoolTagButton({
  onSpool,
  onNewSpool,
}: {
  onSpool: (spoolId: number) => void;
  onNewSpool: (intake: StationTagIntake) => void;
}) {
  const { t } = useTranslation();
  const edge = useEdgeTagStation();
  if (!edge.supported) return null;
  const busy = edge.status === 'connecting' || edge.status === 'working';

  const read = () => {
    edge.run(async (station) => identifyStationTag(await station.read()))
      .then((intake) => {
        if (!intake) return;
        const { identity } = intake;
        if (identity.status === 'matched' && identity.spool_id !== null) onSpool(identity.spool_id);
        else onNewSpool(intake);
      })
      .catch((error: unknown) => {
        const detail = (error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;
        toast.error(edgeTagStationErrorText(t, error) ?? translateApiError(t, detail), undefined, 'spool-tags');
      });
  };

  return (
    <button
      type="button"
      onClick={read}
      disabled={busy}
      title={t(edge.status === 'connecting' ? 'edgeTags.connecting' : 'edgeTags.readTagHint')}
      className="flex items-center gap-1.5 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-sm text-cyan-100 transition-colors hover:bg-cyan-400/20 disabled:opacity-60"
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Nfc className="h-4 w-4" />}
      <span>{t('edgeTags.readTag')}</span>
    </button>
  );
}
