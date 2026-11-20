// What the site knows about Edge kit firmware, and how it talks to a kit over
// USB. Nothing here touches a serial port: see edgeDevice.ts for that.

export const EDGE_FIRMWARE_BASE = '/firmware/edge/';
export const EDGE_INSTALL_GUIDE_URL = 'https://github.com/WeLizard/FilamentHub/tree/main/edge-agent#installation';

export type EdgeKitStatus = 'prototype' | 'hardware-verified' | 'released';

export interface EdgeFirmwareImage {
  offset: number;
  path: string;
  bytes: number;
  sha256: string;
}

export interface EdgeNfcPins {
  sck: number;
  miso: number;
  mosi: number;
  nss: number;
  busy: number;
  rst: number;
}

export interface EdgeKit {
  id: string;
  status: EdgeKitStatus;
  chip: string;
  board: string;
  reader: string;
  nfcPins: EdgeNfcPins;
  firmware: {
    version: string;
    flashBytes: number;
    partitionTableOffset: number;
    appOffset: number;
    images: EdgeFirmwareImage[];
  };
}

export interface EdgeFlashImage {
  address: number;
  data: Uint8Array;
}

/** A failure the installer can explain; `code` selects the message. */
export class EdgeFirmwareError extends Error {
  constructor(public readonly code: 'index' | 'download' | 'integrity') {
    super(code);
    this.name = 'EdgeFirmwareError';
  }
}

const PIN_NAMES = ['sck', 'miso', 'mosi', 'nss', 'busy', 'rst'] as const;
const STATUSES: EdgeKitStatus[] = ['prototype', 'hardware-verified', 'released'];
const FLASH_SIZES: Record<string, number> = { '4MB': 4 << 20, '8MB': 8 << 20, '16MB': 16 << 20 };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isOffset(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value < 16 << 20;
}

function parseImage(value: unknown): EdgeFirmwareImage {
  if (
    !isRecord(value)
    || !isOffset(value.offset)
    || typeof value.path !== 'string'
    // Images are fetched from our own static folder only.
    || !/^[a-z0-9][a-z0-9._-]*(\/[a-z0-9][a-z0-9._-]*)*\.bin$/.test(value.path)
    || typeof value.bytes !== 'number' || !Number.isInteger(value.bytes) || value.bytes <= 0
    || typeof value.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(value.sha256)
  ) {
    throw new EdgeFirmwareError('index');
  }
  return { offset: value.offset, path: value.path, bytes: value.bytes, sha256: value.sha256 };
}

function parseKit(value: unknown): EdgeKit {
  if (!isRecord(value) || !isRecord(value.firmware) || !isRecord(value.nfc_pins)) {
    throw new EdgeFirmwareError('index');
  }
  const { firmware, nfc_pins: pins } = value;
  const flash = isRecord(firmware.flash) ? firmware.flash : {};
  const flashBytes = typeof flash.size === 'string' ? FLASH_SIZES[flash.size] : undefined;
  if (
    typeof value.id !== 'string' || !/^[a-z0-9-]{1,64}$/.test(value.id)
    || !STATUSES.includes(value.status as EdgeKitStatus)
    || typeof value.chip !== 'string' || typeof value.board !== 'string'
    || typeof value.reader !== 'string'
    || typeof firmware.version !== 'string' || !/^\d+\.\d+\.\d+$/.test(firmware.version)
    || flashBytes === undefined
    || !isOffset(firmware.partition_table_offset) || !isOffset(firmware.app_offset)
    || !Array.isArray(firmware.images) || firmware.images.length === 0
    || !PIN_NAMES.every((name) => Number.isInteger(pins[name]))
  ) {
    throw new EdgeFirmwareError('index');
  }
  const images = firmware.images.map(parseImage);
  // The installer relies on both of these being separate images.
  if (!images.some((image) => image.offset === firmware.partition_table_offset)
      || !images.some((image) => image.offset === firmware.app_offset)) {
    throw new EdgeFirmwareError('index');
  }
  return {
    id: value.id,
    status: value.status as EdgeKitStatus,
    chip: value.chip,
    board: value.board,
    reader: value.reader,
    nfcPins: Object.fromEntries(PIN_NAMES.map((name) => [name, pins[name]])) as unknown as EdgeNfcPins,
    firmware: {
      version: firmware.version,
      flashBytes,
      partitionTableOffset: firmware.partition_table_offset,
      appOffset: firmware.app_offset,
      images,
    },
  };
}

export function parseEdgeFirmwareIndex(value: unknown): EdgeKit[] {
  if (!isRecord(value) || value.schema !== 1 || !Array.isArray(value.kits)) {
    throw new EdgeFirmwareError('index');
  }
  return value.kits.map(parseKit);
}

export async function fetchEdgeKits(signal?: AbortSignal): Promise<EdgeKit[]> {
  let response: Response;
  try {
    response = await fetch(`${EDGE_FIRMWARE_BASE}index.json`, { cache: 'no-cache', signal });
  } catch {
    throw new EdgeFirmwareError('download');
  }
  if (!response.ok) throw new EdgeFirmwareError('download');
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new EdgeFirmwareError('index');
  }
  return parseEdgeFirmwareIndex(body);
}

async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data as BufferSource);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** Downloads the kit's images and refuses any that is not the published one. */
export async function downloadEdgeImages(kit: EdgeKit, signal?: AbortSignal): Promise<EdgeFlashImage[]> {
  const images: EdgeFlashImage[] = [];
  for (const image of kit.firmware.images) {
    let data: Uint8Array;
    try {
      const response = await fetch(EDGE_FIRMWARE_BASE + image.path, { signal });
      if (!response.ok) throw new Error(String(response.status));
      data = new Uint8Array(await response.arrayBuffer());
    } catch {
      throw new EdgeFirmwareError('download');
    }
    if (data.length !== image.bytes || await sha256Hex(data) !== image.sha256) {
      throw new EdgeFirmwareError('integrity');
    }
    images.push({ address: image.offset, data });
  }
  return images;
}

export type EdgeLayout = 'same' | 'blank' | 'other';

/**
 * Compares what is on the board where our partition table would be.
 * `same` means the settings and history areas are where this firmware expects
 * them, so the application alone can be replaced.
 */
export function compareEdgeLayout(onDevice: Uint8Array, published: Uint8Array): EdgeLayout {
  if (onDevice.length === published.length && onDevice.every((byte, at) => byte === published[at])) {
    return 'same';
  }
  return onDevice.every((byte) => byte === 0xff) ? 'blank' : 'other';
}

export interface EdgeKitLink {
  ssid: string;
  password: string;
  pairingCode: string;
}

/**
 * The single configuration line a kit accepts over USB: the network to use,
 * the site and the one-time code that make it a node of an account, and
 * where its reader is wired. It replaces whatever the kit had.
 */
export function buildEdgeProvisionLine(kit: EdgeKit, origin: string, link: EdgeKitLink): string {
  const url = new URL(origin);
  return JSON.stringify({
    wifi: { ssid: link.ssid, password: link.password },
    cloud: url.protocol === 'https:'
      ? { origin: url.origin }
      : { origin: url.origin, allow_local_http: true },
    connections: [],
    nfc: kit.nfcPins,
    node: { pairing_code: link.pairingCode },
  });
}

export type EdgeDeviceMessage =
  | { kind: 'boot'; firmware: string; configured: boolean; provisionWindowMs: number }
  | { kind: 'provision'; ok: boolean }
  | { kind: 'ready'; nfc: boolean }
  | { kind: 'wifi'; connected: boolean; reason: 'password' | 'not_found' | 'other' | null }
  | { kind: 'node'; state: 'linked' | 'code_rejected' | 'removed' }
  | { kind: 'tag'; type: string; uid: string; uri: string | null; ndefKnown: boolean }
  | { kind: 'written' }
  | { kind: 'failure'; error: string };

/** Reads one line from the kit; log lines and anything unrecognised give null. */
export function parseEdgeDeviceLine(line: string): EdgeDeviceMessage | null {
  const text = line.trim();
  if (!text.startsWith('{')) return null;
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(value)) return null;
  if (value.event === 'boot' && typeof value.firmware === 'string' && typeof value.configured === 'boolean') {
    return {
      kind: 'boot',
      firmware: value.firmware,
      configured: value.configured,
      provisionWindowMs: typeof value.provision_window_ms === 'number' ? value.provision_window_ms : 0,
    };
  }
  if (value.event === 'provision' && typeof value.ok === 'boolean') {
    return { kind: 'provision', ok: value.ok };
  }
  if (value.event === 'ready' && typeof value.nfc === 'boolean') {
    return { kind: 'ready', nfc: value.nfc };
  }
  if (value.event === 'wifi' && (value.state === 'connected' || value.state === 'failed')) {
    const reason = value.reason === 'password' || value.reason === 'not_found' ? value.reason : 'other';
    return { kind: 'wifi', connected: value.state === 'connected', reason: value.state === 'failed' ? reason : null };
  }
  if (value.event === 'node'
      && (value.state === 'linked' || value.state === 'code_rejected' || value.state === 'removed')) {
    return { kind: 'node', state: value.state };
  }
  if (value.event !== undefined) return null;
  if (value.ok === true && typeof value.uid === 'string' && typeof value.type === 'string') {
    return {
      kind: 'tag',
      type: value.type,
      uid: value.uid,
      uri: typeof value.uri === 'string' ? value.uri : null,
      ndefKnown: value.ndef_known === true,
    };
  }
  if (value.ok === true && value.written === true) {
    return { kind: 'written' };
  }
  if (value.ok === false && typeof value.error === 'string') {
    return { kind: 'failure', error: value.error };
  }
  return null;
}

// MD5 is what the ESP flasher itself reports for a written region; the browser
// has no built-in for it.
const MD5_SHIFTS = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
const MD5_SINES = Array.from({ length: 64 }, (_, i) => Math.floor(Math.abs(Math.sin(i + 1)) * 2 ** 32));

export function md5Hex(data: Uint8Array): string {
  const padded = new Uint8Array(((data.length + 8) >> 6 << 6) + 64);
  padded.set(data);
  padded[data.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, (data.length << 3) >>> 0, true);
  view.setUint32(padded.length - 4, Math.floor(data.length / 2 ** 29), true);
  const state = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476];
  for (let block = 0; block < padded.length; block += 64) {
    let [a, b, c, d] = state;
    for (let i = 0; i < 64; i++) {
      const round = i >> 4;
      let mix: number;
      let word: number;
      if (round === 0) { mix = (b & c) | (~b & d); word = i; }
      else if (round === 1) { mix = (d & b) | (~d & c); word = (5 * i + 1) % 16; }
      else if (round === 2) { mix = b ^ c ^ d; word = (3 * i + 5) % 16; }
      else { mix = c ^ (b | ~d); word = (7 * i) % 16; }
      const sum = (a + mix + MD5_SINES[i] + view.getUint32(block + word * 4, true)) >>> 0;
      const shift = MD5_SHIFTS[round * 4 + (i % 4)];
      a = d;
      d = c;
      c = b;
      b = (b + ((sum << shift) | (sum >>> (32 - shift)))) >>> 0;
    }
    state[0] = (state[0] + a) >>> 0;
    state[1] = (state[1] + b) >>> 0;
    state[2] = (state[2] + c) >>> 0;
    state[3] = (state[3] + d) >>> 0;
  }
  const out = new DataView(new ArrayBuffer(16));
  state.forEach((word, at) => out.setUint32(at * 4, word, true));
  return Array.from(new Uint8Array(out.buffer), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
