/// <reference types="w3c-web-serial" />
// Talking to an Edge kit over USB from the browser: the ROM loader for writing
// firmware and the kit's own console afterwards. Protocol knowledge that needs
// no port lives in edgeFirmware.ts.

import {
  compareEdgeLayout,
  md5Hex,
  parseEdgeDeviceLine,
  type EdgeDeviceMessage,
  type EdgeFlashImage,
  type EdgeKit,
  type EdgeLayout,
} from './edgeFirmware';

const CONSOLE_BAUD = 115200;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function isEdgeSerialSupported(): boolean {
  return typeof navigator !== 'undefined' && 'serial' in navigator;
}

/** A failure the installer can explain; `code` selects the message. */
export class EdgeDeviceError extends Error {
  constructor(public readonly code: 'wrong_chip' | 'flash_too_small' | 'port_busy' | 'connection') {
    super(code);
    this.name = 'EdgeDeviceError';
  }
}

/** Asks the person to pick the board. Resolves to null when they close the dialog. */
export async function requestEdgePort(): Promise<SerialPort | null> {
  try {
    return await navigator.serial.requestPort();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'NotFoundError') return null;
    throw error;
  }
}

export interface EdgeBoardInfo {
  chip: string;
  flashBytes: number;
  layout: EdgeLayout;
}

type Loader = import('esptool-js').ESPLoader;
type Transport = import('esptool-js').Transport;

/** A board held in its ROM loader: inspect it, then write to it or let it go. */
export class EdgeBootloaderSession {
  private constructor(
    private readonly loader: Loader,
    private readonly transport: Transport,
    readonly info: EdgeBoardInfo,
  ) {}

  /** `images` are the kit's verified images; the board's layout is compared with them. */
  static async open(
    port: SerialPort,
    kit: EdgeKit,
    images: EdgeFlashImage[],
    onLog: (line: string) => void,
  ): Promise<EdgeBootloaderSession> {
    // The flasher is only needed here, so it stays out of the page bundle.
    const { ESPLoader, Transport } = await import('esptool-js');
    const transport = new Transport(port, false);
    const loader = new ESPLoader({
      transport,
      baudrate: CONSOLE_BAUD,
      terminal: { clean() {}, write: onLog, writeLine: onLog },
    });
    try {
      await loader.main();
      if (loader.chip.CHIP_NAME !== kit.chip) throw new EdgeDeviceError('wrong_chip');
      // The JEDEC id carries the capacity as a power of two.
      const flashBytes = 2 ** ((await loader.readFlashId() >> 16) & 0xff);
      if (flashBytes < kit.firmware.flashBytes) throw new EdgeDeviceError('flash_too_small');
      const table = images.find((image) => image.address === kit.firmware.partitionTableOffset)!.data;
      const onDevice = await loader.readFlash(kit.firmware.partitionTableOffset, table.length);
      return new EdgeBootloaderSession(loader, transport, {
        chip: loader.chip.CHIP_NAME,
        flashBytes,
        layout: compareEdgeLayout(onDevice, table),
      });
    } catch (error) {
      await transport.disconnect().catch(() => undefined);
      if (error instanceof EdgeDeviceError) throw error;
      if (error instanceof DOMException && error.name === 'InvalidStateError') {
        throw new EdgeDeviceError('port_busy');
      }
      throw new EdgeDeviceError('connection');
    }
  }

  /**
   * Writes the images and restarts the board into the new firmware.
   * `eraseAll` wipes the whole chip first, settings included.
   */
  async write(
    images: EdgeFlashImage[],
    eraseAll: boolean,
    onProgress: (fraction: number) => void,
  ): Promise<void> {
    const total = images.reduce((sum, image) => sum + image.data.length, 0);
    const before = images.map((_, at) => images.slice(0, at).reduce((sum, image) => sum + image.data.length, 0));
    try {
      await this.loader.writeFlash({
        fileArray: images,
        // The published bytes are written as they are.
        flashMode: 'keep',
        flashFreq: 'keep',
        flashSize: 'keep',
        eraseAll,
        compress: true,
        calculateMD5Hash: md5Hex,
        reportProgress: (index, written, size) => {
          onProgress((before[index] + (written / size) * images[index].data.length) / total);
        },
      });
      await this.loader.after('hard_reset');
    } catch {
      throw new EdgeDeviceError('connection');
    } finally {
      await this.transport.disconnect().catch(() => undefined);
    }
  }

  /** Leaves the board as it was and restarts it into whatever firmware it has. */
  async release(): Promise<void> {
    try {
      await this.loader.after('hard_reset');
    } catch {
      // The board may already be gone; closing the port is what matters.
    }
    await this.transport.disconnect().catch(() => undefined);
  }
}

/** The kit's own line console, open after the firmware has started. */
export class EdgeConsole {
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private closed = false;

  private constructor(private readonly port: SerialPort) {}

  /**
   * Opens the console and restarts the kit, so that it introduces itself.
   * A port that was just used for flashing can take a moment to come back.
   */
  static async open(
    port: SerialPort,
    onMessage: (message: EdgeDeviceMessage) => void,
    onLost: () => void,
  ): Promise<EdgeConsole> {
    let lastError: unknown;
    for (let attempt = 0; attempt < 10; attempt++) {
      try {
        await port.open({ baudRate: CONSOLE_BAUD });
        lastError = undefined;
        break;
      } catch (error) {
        lastError = error;
        await sleep(500);
      }
    }
    if (lastError !== undefined) throw new EdgeDeviceError('port_busy');
    const session = new EdgeConsole(port);
    void session.pump(onMessage, onLost);
    await session.restart();
    return session;
  }

  private async pump(onMessage: (message: EdgeDeviceMessage) => void, onLost: () => void) {
    const decoder = new TextDecoder();
    let pending = '';
    try {
      while (!this.closed && this.port.readable) {
        this.reader = this.port.readable.getReader();
        try {
          for (;;) {
            const { value, done } = await this.reader.read();
            if (done) break;
            pending += decoder.decode(value, { stream: true });
            const lines = pending.split('\n');
            pending = lines.pop() ?? '';
            // A runaway line is noise, not a message.
            if (pending.length > 16384) pending = '';
            for (const line of lines) {
              const message = parseEdgeDeviceLine(line);
              if (message) onMessage(message);
            }
          }
        } finally {
          this.reader.releaseLock();
          this.reader = null;
        }
      }
    } catch {
      // Falls through to onLost below.
    }
    if (!this.closed) onLost();
  }

  /** Pulses the reset line the way the board's USB bridge expects. */
  async restart(): Promise<void> {
    await this.port.setSignals({ dataTerminalReady: false, requestToSend: true });
    await sleep(250);
    await this.port.setSignals({ dataTerminalReady: false, requestToSend: false });
  }

  async send(line: string): Promise<void> {
    if (!this.port.writable) throw new EdgeDeviceError('connection');
    const writer = this.port.writable.getWriter();
    try {
      await writer.write(new TextEncoder().encode(`${line}\n`));
    } catch {
      throw new EdgeDeviceError('connection');
    } finally {
      writer.releaseLock();
    }
  }

  async close(): Promise<void> {
    this.closed = true;
    await this.reader?.cancel().catch(() => undefined);
    await this.port.close().catch(() => undefined);
  }
}
