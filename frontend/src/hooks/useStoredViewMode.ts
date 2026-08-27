import type { ViewMode } from '../components/ViewModeToggle';
import { useStoredUiChoice } from './useStoredUiChoice';

const VIEW_MODES = ['grid', 'list'] as const;

export function useStoredViewMode(
  preferenceKey: string,
  userId: number | null | undefined,
  fallback: ViewMode = 'grid',
): [ViewMode, (mode: ViewMode) => void] {
  return useStoredUiChoice(preferenceKey, userId, VIEW_MODES, fallback);
}
