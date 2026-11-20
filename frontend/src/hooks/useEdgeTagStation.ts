import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { TFunction } from 'i18next';

import { spoolTagsAPI, type SpoolTagIdentity } from '../api/client';
import { isEdgeSerialSupported } from '../utils/edgeDevice';
import {
  connectEdgeTagStation,
  EdgeTagStationError,
  type EdgeTagRead,
  type EdgeTagStation,
} from '../utils/edgeTagStation';
import { isPluginEmbed } from '../utils/pluginBridge';

export type EdgeTagStationStatus = 'idle' | 'connecting' | 'ready' | 'working';

// Firmware errors the installer already explains in edgeKit.readErrors.
const KIT_READ_ERRORS = new Set([
  'no_tag_or_io_error',
  'multiple_tags_or_collision',
  'reader_disabled',
  'reader_unavailable',
  'no_answer',
]);
const STATION_ERRORS = new Set([
  'not_configured',
  'lost',
  'busy',
  'port_busy',
  'connection',
  'not_writable',
  'origin_mismatch',
  'write_rejected_or_interrupted',
  'linked_elsewhere',
]);

export function edgeTagStationErrorText(t: TFunction, error: unknown): string | null {
  if (!(error instanceof EdgeTagStationError)) return null;
  if (STATION_ERRORS.has(error.code)) return t(`edgeTags.errors.${error.code}`);
  if (KIT_READ_ERRORS.has(error.code)) return t(`edgeKit.readErrors.${error.code}`);
  return t('edgeKit.readErrors.other', { code: error.code });
}

/**
 * A tag station on USB for one screen. The kit restarts on connect and needs
 * a few seconds (up to 15 on firmware before 0.2.1) before it reads, so it
 * stays connected until the screen goes away or the person disconnects it.
 */
function useOwnEdgeTagStation() {
  const station = useRef<EdgeTagStation | null>(null);
  const [status, setStatus] = useState<EdgeTagStationStatus>('idle');
  const supported = isEdgeSerialSupported() && !isPluginEmbed();

  const disconnect = useCallback(async () => {
    const open = station.current;
    station.current = null;
    setStatus('idle');
    await open?.close();
  }, []);

  useEffect(() => () => {
    void station.current?.close();
    station.current = null;
  }, []);

  /**
   * Runs `work` on the station, connecting first when needed. Must be called
   * from a click: choosing the port needs the person's gesture. Resolves to
   * null when they close the port dialog.
   */
  const run = useCallback(async <T,>(work: (open: EdgeTagStation) => Promise<T>): Promise<T | null> => {
    let open = station.current?.connected ? station.current : null;
    if (!open) {
      setStatus('connecting');
      try {
        open = await connectEdgeTagStation();
      } catch (error) {
        setStatus('idle');
        throw error;
      }
      if (!open) {
        setStatus('idle');
        return null;
      }
      station.current = open;
    }
    setStatus('working');
    try {
      return await work(open);
    } finally {
      if (open.connected) {
        setStatus('ready');
      } else {
        station.current = null;
        setStatus('idle');
      }
    }
  }, []);

  return useMemo(
    () => ({ supported, status, run, disconnect, shared: false }),
    [supported, status, run, disconnect],
  );
}

export type EdgeTagStationHandle = ReturnType<typeof useOwnEdgeTagStation>;

const SharedStation = createContext<EdgeTagStationHandle | null>(null);

/**
 * One station for everything under it. The kit's port opens only once, so
 * the spools page, its add form and each spool's tag dialog share it instead
 * of fighting over the port.
 */
export function EdgeTagStationProvider({ children }: { children: ReactNode }) {
  const station = useOwnEdgeTagStation();
  const value = useMemo(() => ({ ...station, shared: true }), [station]);
  return createElement(SharedStation.Provider, { value }, children);
}

/** The shared station under an EdgeTagStationProvider, otherwise one of its own. */
export function useEdgeTagStation(): EdgeTagStationHandle {
  const shared = useContext(SharedStation);
  const own = useOwnEdgeTagStation();
  return shared ?? own;
}

/** A tag read on the station, with what the site knows about it. */
export interface StationTagIntake {
  tag: EdgeTagRead;
  identity: SpoolTagIdentity;
}

/** Whose spool the tag marks or, for a free tag, what its memory describes. */
export async function identifyStationTag(tag: EdgeTagRead): Promise<StationTagIntake> {
  const identity = await spoolTagsAPI.identify({ uid: tag.uid, chip: tag.type, data: tag.data });
  return { tag, identity };
}
