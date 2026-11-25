/** Which preset this one was made from, when it was made from another. */

import { useTranslation } from 'react-i18next';
import { GitBranch } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { presetsAPI } from '../api/client';

interface PresetOriginProps {
  sourceId: number | null | undefined;
  className?: string;
}

export function PresetOrigin({ sourceId, className = '' }: PresetOriginProps) {
  const { t } = useTranslation();
  const source = useQuery({
    queryKey: ['preset-origin', sourceId],
    queryFn: () => presetsAPI.get(sourceId!),
    enabled: !!sourceId,
    // A source that is private or gone stays so; asking again changes nothing.
    retry: false,
    staleTime: 5 * 60_000,
  });

  if (!sourceId || source.isLoading) return null;

  return (
    <p className={`flex items-center gap-1.5 text-xs text-gray-400 ${className}`}>
      <GitBranch aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
      <span className="min-w-0 truncate">
        {source.data
          ? t('presetOrigin.basedOn', { name: source.data.name })
          : t('presetOrigin.basedOnUnavailable')}
      </span>
    </p>
  );
}
