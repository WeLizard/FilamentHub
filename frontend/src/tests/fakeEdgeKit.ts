// A stand-in for an Edge kit on USB that answers with the firmware's own JSON
// lines (edge-agent/firmware/src/nfc_console.c), parsed by the site's parser:
// boot and ready, read, and the guarded write_uri with its origin check.

import { parseEdgeDeviceLine, type EdgeDeviceMessage } from '../utils/edgeFirmware';
import type { EdgeConsoleOpener } from '../utils/edgeTagStation';

export interface FakeTag {
  uid: string;
  type: string;
  uri?: string;
}

export function fakeEdgeKit(options: {
  configured?: boolean;
  nfc?: boolean;
  origin?: string;
  tag?: FakeTag | null;
} = {}) {
  const { configured = true, nfc = true, origin = 'https://filamenthub.ru' } = options;
  let tag: FakeTag | null = options.tag === undefined ? { uid: '04112233445566', type: 'ntag215' } : options.tag;
  const sent: string[] = [];
  let emit: (message: EdgeDeviceMessage) => void = () => undefined;
  let lose: () => void = () => undefined;
  let silent = false;
  const say = (line: string) => {
    const message = parseEdgeDeviceLine(line);
    if (message) queueMicrotask(() => emit(message));
  };
  const allowed = (uri: string) => uri.startsWith(`${origin}/qr/`)
    && /^[A-Za-z0-9_-]{3,100}$/.test(uri.slice(origin.length + 4));

  const open: EdgeConsoleOpener = async (onMessage, onLost) => {
    emit = onMessage;
    lose = onLost;
    say(`{"event":"boot","firmware":"0.2.0","configured":${configured}${configured ? ',"provision_window_ms":15000' : ''}}`);
    if (configured) say(`{"event":"ready","nfc":${nfc}}`);
    return {
      send: async (line: string) => {
        sent.push(line);
        if (silent) return;
        const command = JSON.parse(line);
        if (command.command === 'read') {
          if (!tag) say('{"ok":false,"error":"no_tag_or_io_error"}');
          else say(JSON.stringify({ ok: true, type: tag.type, uid: tag.uid, ndef_known: true, ...(tag.uri ? { uri: tag.uri } : {}) }));
        } else if (command.command === 'write_uri') {
          if (!allowed(command.uri)) say('{"ok":false,"error":"invalid_write_request"}');
          else if (!tag || tag.uid !== command.expected_uid) say('{"ok":false,"error":"write_rejected_or_interrupted"}');
          else {
            tag = { ...tag, uri: command.uri };
            say('{"ok":true,"written":true}');
          }
        }
      },
      close: async () => undefined,
    };
  };

  return {
    open,
    sent,
    lose: () => lose(),
    silence: () => { silent = true; },
    setTag: (next: FakeTag | null) => { tag = next; },
    get tag() { return tag; },
  };
}
