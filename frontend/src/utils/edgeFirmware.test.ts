// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import publishedIndex from '../../public/firmware/edge/index.json?raw';
import {
  buildEdgeProvisionLine,
  compareEdgeLayout,
  downloadEdgeImages,
  md5Hex,
  parseEdgeDeviceLine,
  parseEdgeFirmwareIndex,
  type EdgeKit,
} from './edgeFirmware';

const published = JSON.parse(publishedIndex);

afterEach(() => vi.unstubAllGlobals());

async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data as BufferSource);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

describe('published firmware index', () => {
  it('is what the installer accepts', () => {
    const kits = parseEdgeFirmwareIndex(published);
    expect(kits.length).toBeGreaterThan(0);
    expect(kits[0].firmware.images.map((image) => image.offset)).toContain(kits[0].firmware.appOffset);
  });

  it('refuses an image path that leaves the firmware folder', () => {
    const forged = structuredClone(published);
    forged.kits[0].firmware.images[0].path = '../../api/v1/anything.bin';
    expect(() => parseEdgeFirmwareIndex(forged)).toThrow();
    forged.kits[0].firmware.images[0].path = 'https://example.com/firmware.bin';
    expect(() => parseEdgeFirmwareIndex(forged)).toThrow();
  });
});

describe('downloadEdgeImages', () => {
  it('hands over the published bytes and refuses anything else', async () => {
    const files: Record<string, Uint8Array> = {
      'kit/1.0.0/partitions.bin': Uint8Array.from({ length: 96 }, (_, at) => at),
      'kit/1.0.0/firmware.bin': Uint8Array.from({ length: 5000 }, (_, at) => (at * 7) & 0xff),
    };
    const [template] = parseEdgeFirmwareIndex(published);
    const offsets = [template.firmware.partitionTableOffset, template.firmware.appOffset];
    const kit: EdgeKit = {
      ...template,
      firmware: {
        ...template.firmware,
        images: await Promise.all(Object.entries(files).map(async ([path, data], at) => ({
          offset: offsets[at], path, bytes: data.length, sha256: await sha256Hex(data),
        }))),
      },
    };
    const serve = (tamper: boolean) => vi.stubGlobal('fetch', async (url: string) => {
      const data = files[url.replace('/firmware/edge/', '')].slice();
      if (tamper && url.endsWith('firmware.bin')) data[data.length - 1] ^= 1;
      return new Response(data);
    });

    serve(false);
    const images = await downloadEdgeImages(kit);
    expect(images.map((image) => image.address)).toEqual(offsets);
    expect(images[1].data).toEqual(files['kit/1.0.0/firmware.bin']);

    serve(true);
    await expect(downloadEdgeImages(kit)).rejects.toMatchObject({ code: 'integrity' });
  });
});

describe('md5Hex', () => {
  // The flasher compares this with what the chip computes over the written
  // region; a wrong digest here fails every installation.
  it.each([
    [0, 'd41d8cd98f00b204e9800998ecf8427e'],
    [3, '3b704fb2660febf62921a0caaa8de56b'],
    [55, 'c9e512626618c9980ef21a96597af94c'],
    [56, 'ecde7caa08e9f5657c863df107cac60a'],
    [64, 'b6bf87c24b1bc334e2541387a92b981b'],
    [119, 'd5dc3d8264de3aa24dee105910ee27fe'],
    [120, 'bcc139b3848923904860d1eefd6e5923'],
    [4096, '88c3b31b216d705c77b752990f1b55f5'],
    [70001, 'e9f4118a13dce52b1ce13e95f2844615'],
  ])('matches the reference for %i bytes', (size, digest) => {
    expect(md5Hex(Uint8Array.from({ length: size }, (_, at) => (at * 31 + 7) & 0xff))).toBe(digest);
  });
});

describe('compareEdgeLayout', () => {
  it('keeps settings only when the board has exactly our partition table', () => {
    const ours = Uint8Array.from({ length: 96 }, (_, at) => at);
    expect(compareEdgeLayout(ours.slice(), ours)).toBe('same');
    expect(compareEdgeLayout(new Uint8Array(96).fill(0xff), ours)).toBe('blank');
    const foreign = ours.slice();
    foreign[40] ^= 0x10;
    expect(compareEdgeLayout(foreign, ours)).toBe('other');
  });
});

describe('kit console', () => {
  it('reads the status lines and ignores the log around them', () => {
    expect(parseEdgeDeviceLine('{"event":"boot","firmware":"0.2.0","configured":true,"provision_window_ms":15000}\r'))
      .toEqual({ kind: 'boot', firmware: '0.2.0', configured: true, provisionWindowMs: 15000 });
    expect(parseEdgeDeviceLine('{"event":"boot","firmware":"0.2.0","configured":false}'))
      .toEqual({ kind: 'boot', firmware: '0.2.0', configured: false, provisionWindowMs: 0 });
    expect(parseEdgeDeviceLine('{"event":"provision","ok":false}')).toEqual({ kind: 'provision', ok: false });
    expect(parseEdgeDeviceLine('{"event":"ready","nfc":true}')).toEqual({ kind: 'ready', nfc: true });
    expect(parseEdgeDeviceLine('{"event":"wifi","state":"connected"}'))
      .toEqual({ kind: 'wifi', connected: true, reason: null });
    expect(parseEdgeDeviceLine('{"event":"wifi","state":"failed","reason":"password"}'))
      .toEqual({ kind: 'wifi', connected: false, reason: 'password' });
    expect(parseEdgeDeviceLine('{"event":"node","state":"linked"}')).toEqual({ kind: 'node', state: 'linked' });
    expect(parseEdgeDeviceLine('{"ok":true,"type":"ntag215","uid":"04112233445566","ndef_known":false}'))
      .toEqual({ kind: 'tag', type: 'ntag215', uid: '04112233445566', uri: null });
    expect(parseEdgeDeviceLine('{"ok":false,"error":"no_tag_or_io_error"}'))
      .toEqual({ kind: 'failure', error: 'no_tag_or_io_error' });
    expect(parseEdgeDeviceLine('I (312) fh_edge: Wi-Fi connected')).toBeNull();
    expect(parseEdgeDeviceLine('{"event":"ams","status":"observed"}')).toBeNull();
    expect(parseEdgeDeviceLine('{"event":"boot"')).toBeNull();
  });

  it('builds the one line the firmware accepts', () => {
    const [kit] = parseEdgeFirmwareIndex(published);
    const link = { ssid: 'Home "2.4"', password: 'p\\ss', pairingCode: 'FE-ABCDEF-123456' };
    const line = buildEdgeProvisionLine(kit, 'https://filamenthub.ru', link);
    expect(JSON.parse(line)).toEqual({
      wifi: { ssid: 'Home "2.4"', password: 'p\\ss' },
      cloud: { origin: 'https://filamenthub.ru' },
      connections: [],
      nfc: kit.nfcPins,
      node: { pairing_code: 'FE-ABCDEF-123456' },
    });
    expect(line).not.toContain('\n');
    expect(JSON.parse(buildEdgeProvisionLine(kit, 'http://localhost:3000', link)).cloud)
      .toEqual({ origin: 'http://localhost:3000', allow_local_http: true });
  });
});
