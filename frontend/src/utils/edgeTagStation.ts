// An Edge kit with a reader, used from the website as a tag station over USB:
// read a tag, write a spool's FilamentHub address onto it. The kit answers one
// command at a time; this class keeps that order and turns its lines into
// promises. The port itself lives in edgeDevice.ts.

import { EdgeConsole, EdgeDeviceError, requestEdgePort } from './edgeDevice';
import type { EdgeDeviceMessage } from './edgeFirmware';

/** Tag types the kit firmware can write a guarded NDEF URI to. */
export const EDGE_WRITABLE_TAG_TYPES = ['ntag213', 'ntag215', 'ntag216'] as const;

// A configured kit keeps its provisioning window open for 15 seconds after a
// restart before it accepts reader commands; firmware 0.2.1 and later close it
// at once on START_LINE.
const READY_TIMEOUT_MS = 30_000;
const START_LINE = '{"command":"start"}';
const READ_TIMEOUT_MS = 8_000;
const WRITE_TIMEOUT_MS = 20_000;

export interface EdgeTagRead {
  uid: string;
  type: string;
  uri: string | null;
  ndefKnown: boolean;
  /** The tag's memory as base64 (firmware 0.2.2 and later), or null. */
  data: string | null;
}

/**
 * `code` is either one of the station's own conditions below or the error the
 * firmware reported (`no_tag_or_io_error`, `write_rejected_or_interrupted`, ...).
 */
export class EdgeTagStationError extends Error {
  constructor(public readonly code: string) {
    super(code);
    this.name = 'EdgeTagStationError';
  }
}

export interface EdgeConsoleLike {
  send(line: string): Promise<void>;
  close(): Promise<void>;
}

export type EdgeConsoleOpener = (
  onMessage: (message: EdgeDeviceMessage) => void,
  onLost: () => void,
) => Promise<EdgeConsoleLike>;

interface Pending {
  handle: (message: EdgeDeviceMessage) => void;
  reject: (error: EdgeTagStationError) => void;
}

export class EdgeTagStation {
  private console: EdgeConsoleLike | null = null;
  private pending: Pending | null = null;
  private lost = false;

  private constructor() {}

  /** Opens the kit, restarts it and waits until its reader accepts commands. */
  static async connect(open: EdgeConsoleOpener): Promise<EdgeTagStation> {
    const station = new EdgeTagStation();
    // The boot line may come before the console is handed over.
    let skipWindow = false;
    const ready = station.expect<void>(READY_TIMEOUT_MS, (message, resolve, reject) => {
      if (message.kind === 'boot' && !message.configured) reject('not_configured');
      if (message.kind === 'boot' && message.configured && message.provisionSkip) {
        if (station.console) void station.console.send(START_LINE).catch(() => undefined);
        else skipWindow = true;
      }
      if (message.kind === 'ready') {
        if (message.nfc) resolve();
        else reject('reader_disabled');
      }
    });
    try {
      station.console = await open(
        (message) => station.pending?.handle(message),
        () => station.markLost(),
      );
    } catch (error) {
      ready.catch(() => undefined);
      station.rejectPending('connection');
      throw new EdgeTagStationError(error instanceof EdgeDeviceError ? error.code : 'connection');
    }
    if (skipWindow) void station.console.send(START_LINE).catch(() => undefined);
    try {
      await ready;
    } catch (error) {
      await station.close();
      throw error;
    }
    return station;
  }

  get connected(): boolean {
    return this.console !== null && !this.lost;
  }

  read(): Promise<EdgeTagRead> {
    return this.command('{"command":"read"}', READ_TIMEOUT_MS, (message, resolve) => {
      if (message.kind === 'tag') {
        resolve({
          uid: message.uid,
          type: message.type,
          uri: message.uri,
          ndefKnown: message.ndefKnown,
          data: message.data,
        });
      }
    });
  }

  /** Writes `uri` to the one tag on the reader, provided its UID is `expectedUid`. */
  writeUri(expectedUid: string, uri: string): Promise<void> {
    const line = JSON.stringify({ command: 'write_uri', expected_uid: expectedUid, uri });
    return this.command(line, WRITE_TIMEOUT_MS, (message, resolve) => {
      if (message.kind === 'written') resolve();
    });
  }

  async close(): Promise<void> {
    const open = this.console;
    this.console = null;
    this.rejectPending('lost');
    await open?.close().catch(() => undefined);
  }

  private async command<T>(
    line: string,
    timeoutMs: number,
    onAnswer: (message: EdgeDeviceMessage, resolve: (value: T) => void) => void,
  ): Promise<T> {
    if (!this.connected) throw new EdgeTagStationError('lost');
    if (this.pending) throw new EdgeTagStationError('busy');
    const answer = this.expect<T>(timeoutMs, (message, resolve, reject) => {
      // A restart in the middle of a command means the answer will never come.
      if (message.kind === 'boot') reject('lost');
      else if (message.kind === 'failure') reject(message.error);
      else onAnswer(message, resolve);
    });
    try {
      await this.console!.send(line);
    } catch {
      this.rejectPending('connection');
    }
    return answer;
  }

  private expect<T>(
    timeoutMs: number,
    handle: (
      message: EdgeDeviceMessage,
      resolve: (value: T) => void,
      reject: (code: string) => void,
    ) => void,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const finish = () => {
        window.clearTimeout(timer);
        if (this.pending === pending) this.pending = null;
      };
      const pending: Pending = {
        handle: (message) => handle(
          message,
          (value) => { finish(); resolve(value); },
          (code) => { finish(); reject(new EdgeTagStationError(code)); },
        ),
        reject: (error) => { finish(); reject(error); },
      };
      const timer = window.setTimeout(() => pending.reject(new EdgeTagStationError('no_answer')), timeoutMs);
      this.pending = pending;
    });
  }

  private markLost() {
    this.lost = true;
    this.rejectPending('lost');
  }

  private rejectPending(code: string) {
    this.pending?.reject(new EdgeTagStationError(code));
  }
}

/** Asks the person to pick the kit; null when they close the browser's dialog. */
export async function connectEdgeTagStation(): Promise<EdgeTagStation | null> {
  const port = await requestEdgePort();
  if (!port) return null;
  return EdgeTagStation.connect((onMessage, onLost) => EdgeConsole.open(port, onMessage, onLost));
}

// The open and factory formats the site reads from a tag's memory.
const TAG_FORMAT_LABELS: Record<string, string> = {
  tigertag: 'TigerTag',
  openspool: 'OpenSpool',
  openprinttag: 'OpenPrintTag',
};

/** A tag format as people know it; unknown codes are shown as they are. */
export function tagFormatLabel(format: string): string {
  return TAG_FORMAT_LABELS[format] ?? format;
}

export function isWritableTag(tag: EdgeTagRead): boolean {
  return (EDGE_WRITABLE_TAG_TYPES as readonly string[]).includes(tag.type) && tag.uid.length === 14;
}

/**
 * Addresses to try for a spool's QR identity. The kit writes only under the
 * site address it was linked from, which may differ from the canonical one
 * (another domain, or a local development site).
 */
export function spoolTagUris(targetUrl: string, shortCode: string, siteOrigin: string): string[] {
  return [...new Set([targetUrl, `${siteOrigin}/qr/${shortCode}`])];
}

/**
 * Writes the first address the kit accepts. The kit checks the address before
 * it touches the tag, so a refused address is safe to follow with the next.
 */
export async function writeSpoolUri(
  station: EdgeTagStation,
  tag: EdgeTagRead,
  uris: readonly string[],
): Promise<string> {
  if (!isWritableTag(tag)) throw new EdgeTagStationError('not_writable');
  for (const uri of uris) {
    try {
      await station.writeUri(tag.uid, uri);
      return uri;
    } catch (error) {
      if (!(error instanceof EdgeTagStationError) || error.code !== 'invalid_write_request') throw error;
    }
  }
  throw new EdgeTagStationError('origin_mismatch');
}
