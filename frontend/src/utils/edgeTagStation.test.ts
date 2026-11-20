import { afterEach, describe, expect, it, vi } from 'vitest';

import { fakeEdgeKit } from '../tests/fakeEdgeKit';
import {
  EdgeTagStation,
  EdgeTagStationError,
  spoolTagUris,
  writeSpoolUri,
} from './edgeTagStation';

const SITE = 'https://filamenthub.ru';
const UID = '04112233445566';
const CODE = 'FHQ1_04_UExBLTE_U_abcdefghijklmnopqrstuv';

afterEach(() => {
  vi.useRealTimers();
});

describe('Edge tag station', () => {
  it('reads the tag on the reader once the kit is ready', async () => {
    const kit = fakeEdgeKit();
    const station = await EdgeTagStation.connect(kit.open);
    await expect(station.read()).resolves.toEqual({ uid: UID, type: 'ntag215', uri: null, ndefKnown: true });
    expect(kit.sent).toEqual(['{"command":"read"}']);
  });

  it('ends the provisioning window of newer firmware instead of waiting it out', async () => {
    const kit = fakeEdgeKit({ firmware: '0.2.1' });
    const station = await EdgeTagStation.connect(kit.open);
    await expect(station.read()).resolves.toMatchObject({ uid: UID });
    expect(kit.sent).toEqual(['{"command":"start"}', '{"command":"read"}']);
  });

  it('explains a kit without settings or without a reader', async () => {
    await expect(EdgeTagStation.connect(fakeEdgeKit({ configured: false }).open))
      .rejects.toMatchObject({ code: 'not_configured' });
    await expect(EdgeTagStation.connect(fakeEdgeKit({ nfc: false }).open))
      .rejects.toMatchObject({ code: 'reader_disabled' });
  });

  it('passes the firmware error through', async () => {
    const station = await EdgeTagStation.connect(fakeEdgeKit({ tag: null }).open);
    await expect(station.read()).rejects.toMatchObject({ code: 'no_tag_or_io_error' });
  });

  it('writes the spool address and reads it back from the tag', async () => {
    const station = await EdgeTagStation.connect(fakeEdgeKit().open);
    const tag = await station.read();
    const uri = await writeSpoolUri(station, tag, spoolTagUris(`${SITE}/qr/${CODE}`, CODE, SITE));
    expect(uri).toBe(`${SITE}/qr/${CODE}`);
    await expect(station.read()).resolves.toMatchObject({ uid: UID, uri: `${SITE}/qr/${CODE}` });
  });

  it('falls back to the address the kit was linked from', async () => {
    const local = 'http://192.168.1.2:3000';
    const kit = fakeEdgeKit({ origin: local });
    const station = await EdgeTagStation.connect(kit.open);
    const tag = await station.read();
    const uri = await writeSpoolUri(station, tag, spoolTagUris(`${SITE}/qr/${CODE}`, CODE, local));
    expect(uri).toBe(`${local}/qr/${CODE}`);
    expect(kit.tag?.uri).toBe(`${local}/qr/${CODE}`);
  });

  it('says so when the kit belongs to another site', async () => {
    const station = await EdgeTagStation.connect(fakeEdgeKit({ origin: 'https://other.example' }).open);
    const tag = await station.read();
    await expect(writeSpoolUri(station, tag, spoolTagUris(`${SITE}/qr/${CODE}`, CODE, SITE)))
      .rejects.toMatchObject({ code: 'origin_mismatch' });
  });

  it('refuses tags the firmware cannot write before sending anything', async () => {
    const kit = fakeEdgeKit({ tag: { uid: 'A1B2C3D4', type: 'iso14443a' } });
    const station = await EdgeTagStation.connect(kit.open);
    const tag = await station.read();
    await expect(writeSpoolUri(station, tag, [`${SITE}/qr/${CODE}`])).rejects.toMatchObject({ code: 'not_writable' });
    expect(kit.sent).toEqual(['{"command":"read"}']);
  });

  it('does not write over a tag that was swapped after reading', async () => {
    const kit = fakeEdgeKit();
    const station = await EdgeTagStation.connect(kit.open);
    const tag = await station.read();
    kit.setTag({ uid: '04AABBCCDDEEFF', type: 'ntag215' });
    await expect(writeSpoolUri(station, tag, [`${SITE}/qr/${CODE}`]))
      .rejects.toMatchObject({ code: 'write_rejected_or_interrupted' });
    expect(kit.tag?.uri).toBeUndefined();
  });

  it('runs one command at a time and gives up on a silent kit', async () => {
    const kit = fakeEdgeKit();
    const station = await EdgeTagStation.connect(kit.open);
    kit.silence();
    vi.useFakeTimers();
    const first = station.read();
    await expect(station.read()).rejects.toMatchObject({ code: 'busy' });
    vi.advanceTimersByTime(8_000);
    await expect(first).rejects.toMatchObject({ code: 'no_answer' });
    expect(station.connected).toBe(true);
  });

  it('fails a pending command when the kit is unplugged', async () => {
    const kit = fakeEdgeKit();
    const station = await EdgeTagStation.connect(kit.open);
    kit.silence();
    const read = station.read();
    kit.lose();
    await expect(read).rejects.toBeInstanceOf(EdgeTagStationError);
    await expect(read).rejects.toMatchObject({ code: 'lost' });
    expect(station.connected).toBe(false);
  });
});
