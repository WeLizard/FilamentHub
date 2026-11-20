// Every Edge build the site describes, composed from a few options. One table
// of pins per board, one list of modules; the wiring drawing, the parts list
// and the warnings are all derived here, so a combination can never show a
// pin twice or a part that is not wired.

export type EdgeMcu = 'c3' | 's3';
export type EdgeDisplay = 'none' | 'oled' | 'touch';
export type EdgePower = 'usb' | 'battery' | 'printer';
export type EdgeBuildStatus = 'prototype' | 'design';

export interface EdgeBuildOptions {
  mcu: EdgeMcu;
  display: EdgeDisplay;
  power: EdgePower;
  /** One RGB LED and a buzzer that report each scan. */
  feedback: boolean;
  /** Eight slot keys with an LED each: the station. */
  keys: boolean;
  /** Temperature and humidity sensor. */
  climate: boolean;
}

export type EdgeNet = 'v5' | 'v33' | 'gnd' | 'spi' | 'i2c' | 'signal' | 'analog';

export type EdgeSignal =
  | 'nfcSck' | 'nfcMiso' | 'nfcMosi' | 'nfcNss' | 'nfcBusy' | 'nfcRst'
  | 'i2cSda' | 'i2cScl' | 'ledData' | 'buzzer' | 'keysInt' | 'batterySense' | 'wake'
  | 'tftCs' | 'tftDc' | 'tftRst' | 'touchCs' | 'touchIrq';

export type EdgeModuleId =
  | 'reader' | 'oled' | 'touch' | 'expander' | 'leds' | 'led' | 'buzzer' | 'climate' | 'battery' | 'wakeKey';

export interface EdgeModulePin {
  pin: string;
  net: EdgeNet;
  /** The board pad this module pin goes to; power pins go to their rail. */
  signal?: EdgeSignal;
}

export interface EdgeModule {
  id: EdgeModuleId;
  label: string;
  pins: EdgeModulePin[];
  /** Translation key of a short line drawn under the block. */
  note?: string;
}

export interface EdgeWire {
  module: EdgeModuleId;
  modulePin: string;
  boardPin: string;
  net: EdgeNet;
}

export type EdgePowerStage = 'usb' | 'cell' | 'charger' | 'switch' | 'boost' | 'printer' | 'buck' | 'diode' | 'board';

export type EdgePartKey =
  | 'boardC3' | 'boardS3' | 'reader' | 'oled' | 'touch' | 'expander' | 'keys' | 'leds' | 'led'
  | 'buzzer' | 'climate' | 'pullup' | 'cell' | 'holder' | 'charger' | 'switch' | 'boost' | 'diode'
  | 'divider' | 'wakeKey' | 'buck' | 'powerPlug' | 'wire' | 'cable' | 'tags' | 'filament' | 'screws';

export interface EdgePart {
  key: EdgePartKey;
  qty: number;
}

/** Each ready build has a case made for exactly its parts. */
export type EdgeEnclosureId = EdgePreset['id'];

export interface EdgeBuild {
  options: EdgeBuildOptions;
  board: string;
  modules: EdgeModule[];
  wires: EdgeWire[];
  powerPath: EdgePowerStage[];
  parts: EdgePart[];
  /** Translation keys of notes that apply to this combination. */
  notes: string[];
  enclosure: EdgeEnclosureId | null;
  firmware: boolean;
}

export interface EdgePreset {
  id: 'tagC3' | 'tagS3' | 'portableS3' | 'portableC3' | 'touchS3' | 'stationC3' | 'stationS3';
  status: EdgeBuildStatus;
  options: EdgeBuildOptions;
}

export const EDGE_PRESETS: EdgePreset[] = [
  { id: 'tagC3', status: 'prototype', options: { mcu: 'c3', display: 'none', power: 'usb', feedback: false, keys: false, climate: false } },
  { id: 'tagS3', status: 'design', options: { mcu: 's3', display: 'oled', power: 'usb', feedback: true, keys: false, climate: false } },
  { id: 'portableS3', status: 'design', options: { mcu: 's3', display: 'oled', power: 'battery', feedback: true, keys: false, climate: false } },
  { id: 'portableC3', status: 'design', options: { mcu: 'c3', display: 'none', power: 'battery', feedback: true, keys: false, climate: false } },
  { id: 'touchS3', status: 'design', options: { mcu: 's3', display: 'touch', power: 'usb', feedback: true, keys: false, climate: false } },
  { id: 'stationC3', status: 'design', options: { mcu: 'c3', display: 'none', power: 'printer', feedback: false, keys: true, climate: false } },
  { id: 'stationS3', status: 'design', options: { mcu: 's3', display: 'oled', power: 'usb', feedback: false, keys: true, climate: true } },
];

export const EDGE_BOARD_NAMES: Record<EdgeMcu, string> = {
  c3: 'ESP32-C3 SuperMini',
  s3: 'ESP32-S3-DevKitC-1 N16R8',
};

/**
 * Board pads per signal. The C3 NFC pins are the ones of the released kit
 * profile `c3-supermini-pn5180`; the rest avoid strapping, USB, flash and
 * PSRAM pins (C3: 8, 9, 18, 19; S3: 0, 3, 19, 20, 26–37, 38, 43–46, 48).
 */
export const EDGE_PIN_MAPS: Record<EdgeMcu, Partial<Record<EdgeSignal, number>>> = {
  c3: {
    nfcSck: 4, nfcMiso: 5, nfcMosi: 6, nfcNss: 7, nfcBusy: 0, nfcRst: 1,
    i2cSda: 3, i2cScl: 10, ledData: 21, buzzer: 20, keysInt: 2, batterySense: 2,
  },
  s3: {
    nfcSck: 12, nfcMiso: 13, nfcMosi: 11, nfcNss: 10, nfcBusy: 9, nfcRst: 14,
    i2cSda: 1, i2cScl: 2, ledData: 4, buzzer: 5, keysInt: 6, batterySense: 7, wake: 15,
    tftCs: 17, tftDc: 18, tftRst: 8, touchCs: 39, touchIrq: 40,
  },
};

/** Pads an Edge build must never use, per board. */
export const EDGE_RESERVED_PINS: Record<EdgeMcu, number[]> = {
  c3: [8, 9, 18, 19],
  s3: [0, 3, 19, 20, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 43, 44, 45, 46, 48],
};

/** Why a combination cannot be built, or null when it can. */
export type EdgeOptionProblem = 'touchNeedsS3' | 'c3BatteryAndKeys' | null;

export function edgeOptionProblem(options: EdgeBuildOptions): EdgeOptionProblem {
  // A touch screen needs PSRAM for its frame buffer; the C3 has none.
  if (options.display === 'touch' && options.mcu === 'c3') return 'touchNeedsS3';
  // On the C3 the battery reading and the key interrupt need the same last free ADC pad.
  if (options.mcu === 'c3' && options.power === 'battery' && options.keys) return 'c3BatteryAndKeys';
  return null;
}

/** Turns an impossible combination into the nearest possible one after `changed` was set. */
export function edgeFixOptions(options: EdgeBuildOptions, changed: keyof EdgeBuildOptions): EdgeBuildOptions {
  const next = { ...options };
  if (edgeOptionProblem(next) === 'touchNeedsS3') {
    if (changed === 'mcu') next.display = 'oled';
    else next.mcu = 's3';
  }
  if (edgeOptionProblem(next) === 'c3BatteryAndKeys') {
    if (changed === 'keys') next.power = 'usb';
    else if (changed === 'power') next.keys = false;
    else next.mcu = 's3';
  }
  return next;
}

function boardPin(mcu: EdgeMcu, signal: EdgeSignal): string {
  const pad = EDGE_PIN_MAPS[mcu][signal];
  if (pad === undefined) throw new Error(`${mcu} has no pad for ${signal}`);
  return `GPIO${pad}`;
}

const READER: EdgeModule = {
  id: 'reader',
  label: 'PN5180',
  pins: [
    { pin: '+5V', net: 'v5' },
    { pin: '+3.3V', net: 'v33' },
    { pin: 'GND', net: 'gnd' },
    { pin: 'SCK', net: 'spi', signal: 'nfcSck' },
    { pin: 'MISO', net: 'spi', signal: 'nfcMiso' },
    { pin: 'MOSI', net: 'spi', signal: 'nfcMosi' },
    { pin: 'NSS', net: 'spi', signal: 'nfcNss' },
    { pin: 'BUSY', net: 'signal', signal: 'nfcBusy' },
    { pin: 'RST', net: 'signal', signal: 'nfcRst' },
  ],
};

const i2cModule = (id: EdgeModuleId, label: string, power: string, note?: string): EdgeModule => ({
  id,
  label,
  pins: [
    { pin: power, net: 'v33' },
    { pin: 'GND', net: 'gnd' },
    { pin: 'SDA', net: 'i2c', signal: 'i2cSda' },
    { pin: 'SCL', net: 'i2c', signal: 'i2cScl' },
  ],
  note,
});

export function composeEdgeBuild(options: EdgeBuildOptions): EdgeBuild {
  if (edgeOptionProblem(options)) throw new Error(`impossible Edge build: ${edgeOptionProblem(options)}`);
  const { mcu, display, power, keys, climate } = options;
  const feedback = options.feedback || keys;
  const modules: EdgeModule[] = [READER];
  const notes: string[] = [];

  if (display === 'oled') modules.push(i2cModule('oled', 'OLED 128×64 I²C', 'VCC'));
  if (display === 'touch') {
    modules.push({
      id: 'touch',
      label: 'ILI9341 + XPT2046',
      pins: [
        { pin: 'VCC', net: 'v33' },
        { pin: 'LED', net: 'v33' },
        { pin: 'GND', net: 'gnd' },
        { pin: 'SCK · T_CLK', net: 'spi', signal: 'nfcSck' },
        { pin: 'SDO · T_DO', net: 'spi', signal: 'nfcMiso' },
        { pin: 'SDI · T_DIN', net: 'spi', signal: 'nfcMosi' },
        { pin: 'CS', net: 'spi', signal: 'tftCs' },
        { pin: 'DC', net: 'signal', signal: 'tftDc' },
        { pin: 'RESET', net: 'signal', signal: 'tftRst' },
        { pin: 'T_CS', net: 'spi', signal: 'touchCs' },
        { pin: 'T_IRQ', net: 'signal', signal: 'touchIrq' },
      ],
      note: 'edgeBuilds.wiring.notes.touch',
    });
    notes.push('edgeBuilds.notes.sharedSpi');
  }
  if (keys) {
    modules.push({
      id: 'expander',
      label: 'PCF8574',
      pins: [
        { pin: 'VCC', net: 'v33' },
        { pin: 'GND', net: 'gnd' },
        { pin: 'SDA', net: 'i2c', signal: 'i2cSda' },
        { pin: 'SCL', net: 'i2c', signal: 'i2cScl' },
        { pin: 'INT', net: 'signal', signal: 'keysInt' },
      ],
      note: 'edgeBuilds.wiring.notes.keys',
    });
    if (mcu === 'c3') notes.push('edgeBuilds.notes.c3Pullup');
  }
  if (climate) modules.push(i2cModule('climate', 'SHT40', 'VIN'));
  if (feedback) {
    modules.push({
      id: keys ? 'leds' : 'led',
      label: keys ? 'WS2812B × 8' : 'WS2812B',
      pins: [
        { pin: '5V', net: 'v5' },
        { pin: 'GND', net: 'gnd' },
        { pin: 'DIN', net: 'signal', signal: 'ledData' },
      ],
      note: keys ? 'edgeBuilds.wiring.notes.ledChain' : undefined,
    });
    modules.push({
      id: 'buzzer',
      label: 'Buzzer',
      pins: [
        { pin: 'VCC', net: 'v33' },
        { pin: 'GND', net: 'gnd' },
        { pin: 'I/O', net: 'signal', signal: 'buzzer' },
      ],
    });
    notes.push('edgeBuilds.notes.ledLevel');
  }
  if (power === 'battery') {
    modules.push({
      id: 'battery',
      label: '100k / 100k',
      pins: [
        { pin: 'MID', net: 'analog', signal: 'batterySense' },
        { pin: 'GND', net: 'gnd' },
      ],
      note: 'edgeBuilds.wiring.notes.divider',
    });
    if (mcu === 's3') {
      modules.push({
        id: 'wakeKey',
        label: 'Scan key',
        pins: [
          { pin: 'K1', net: 'signal', signal: 'wake' },
          { pin: 'K2', net: 'gnd' },
        ],
      });
    }
    notes.push('edgeBuilds.notes.battery');
    if (mcu === 'c3') notes.push('edgeBuilds.notes.c3Battery');
  }
  if (power === 'printer') notes.push('edgeBuilds.notes.printerPower');
  if (keys && power === 'usb') notes.push('edgeBuilds.notes.usbBudget');

  const wires: EdgeWire[] = [];
  for (const module of modules) {
    for (const pin of module.pins) {
      const target = pin.signal
        ? boardPin(mcu, pin.signal)
        : pin.net === 'v5' ? '5V' : pin.net === 'v33' ? '3V3' : 'GND';
      wires.push({ module: module.id, modulePin: pin.pin, boardPin: target, net: pin.net });
    }
  }

  const powerPath: EdgePowerStage[] = power === 'battery'
    ? ['cell', 'charger', 'switch', 'boost', 'diode', 'board']
    : power === 'printer'
      ? ['printer', 'buck', 'diode', 'board']
      : ['usb', 'board'];

  const ledCount = keys ? 8 : feedback ? 1 : 0;
  const parts: EdgePart[] = [
    { key: mcu === 'c3' ? 'boardC3' : 'boardS3', qty: 1 },
    { key: 'reader', qty: 1 },
    ...(display === 'oled' ? [{ key: 'oled' as const, qty: 1 }] : []),
    ...(display === 'touch' ? [{ key: 'touch' as const, qty: 1 }] : []),
    ...(keys ? [{ key: 'expander' as const, qty: 1 }, { key: 'keys' as const, qty: 8 }] : []),
    ...(keys && mcu === 'c3' ? [{ key: 'pullup' as const, qty: 1 }] : []),
    ...(ledCount > 1 ? [{ key: 'leds' as const, qty: ledCount }] : []),
    ...(ledCount === 1 ? [{ key: 'led' as const, qty: 1 }] : []),
    ...(feedback ? [{ key: 'buzzer' as const, qty: 1 }] : []),
    ...(climate ? [{ key: 'climate' as const, qty: 1 }] : []),
    ...(power === 'battery'
      ? [
        { key: 'cell' as const, qty: 1 },
        { key: 'holder' as const, qty: 1 },
        { key: 'charger' as const, qty: 1 },
        { key: 'switch' as const, qty: 1 },
        { key: 'boost' as const, qty: 1 },
        { key: 'diode' as const, qty: 1 },
        { key: 'divider' as const, qty: 2 },
        ...(mcu === 's3' ? [{ key: 'wakeKey' as const, qty: 1 }] : []),
      ]
      : []),
    ...(power === 'printer'
      ? [{ key: 'buck' as const, qty: 1 }, { key: 'diode' as const, qty: 1 }, { key: 'powerPlug' as const, qty: 1 }]
      : []),
    { key: 'wire', qty: 1 },
    { key: 'cable', qty: 1 },
    { key: 'tags', qty: 1 },
    { key: 'filament', qty: 1 },
    { key: 'screws', qty: 4 },
  ];

  return {
    options: { ...options, feedback },
    board: EDGE_BOARD_NAMES[mcu],
    modules,
    wires,
    powerPath,
    parts,
    notes,
    enclosure: edgeEnclosureFor(options),
    firmware: mcu === 'c3' && display === 'none' && power === 'usb' && !feedback && !keys && !climate,
  };
}

/**
 * The printed case for this combination. A case is made for one exact set of
 * parts, so only a ready build has one: an extra module would have no pocket,
 * a missing one would leave an empty window.
 */
export function edgeEnclosureFor(options: EdgeBuildOptions): EdgeEnclosureId | null {
  return edgePresetFor(options)?.id ?? null;
}

export function edgePresetFor(options: EdgeBuildOptions): EdgePreset | undefined {
  return EDGE_PRESETS.find((preset) => (Object.keys(options) as (keyof EdgeBuildOptions)[])
    .every((key) => preset.options[key] === options[key]));
}

export interface EdgeEnclosureFile {
  key: string;
  file: string;
}

const caseFiles = (slug: string, extra: EdgeEnclosureFile[] = []): EdgeEnclosureFile[] => [
  { key: 'shell', file: `fh-edge-${slug}-shell.stl` },
  { key: 'base', file: `fh-edge-${slug}-base.stl` },
  { key: 'mark', file: `fh-edge-${slug}-mark.stl` },
  ...extra,
  { key: 'shellStep', file: `fh-edge-${slug}-shell.step` },
  { key: 'baseStep', file: `fh-edge-${slug}-base.step` },
];
const STATION_EXTRAS: EdgeEnclosureFile[] = [
  { key: 'caps', file: 'fh-edge-station-keycaps.stl' },
  { key: 'clip', file: 'fh-edge-station-clip-2020.stl' },
];

export const EDGE_ENCLOSURE_FILES: Record<EdgeEnclosureId, EdgeEnclosureFile[]> = {
  tagC3: [
    { key: 'shell', file: 'fh-edge-kit-shell.stl' },
    { key: 'base', file: 'fh-edge-kit-base.stl' },
    { key: 'mark', file: 'fh-edge-kit-mark.stl' },
    { key: 'shellStep', file: 'fh-edge-kit-shell.step' },
    { key: 'baseStep', file: 'fh-edge-kit-base.step' },
  ],
  tagS3: caseFiles('tag-s3'),
  portableS3: caseFiles('portable-s3', [{ key: 'cap', file: 'fh-edge-keycap.stl' }]),
  portableC3: caseFiles('portable-c3'),
  touchS3: caseFiles('touch-s3'),
  stationC3: caseFiles('station-c3', STATION_EXTRAS),
  stationS3: caseFiles('station-s3', STATION_EXTRAS),
};

export const EDGE_ENCLOSURE_IMAGES: Record<EdgeEnclosureId, string> = {
  tagC3: 'kit-front.webp',
  tagS3: 'tag-s3-front.webp',
  portableS3: 'portable-s3-front.webp',
  portableC3: 'portable-c3-front.webp',
  touchS3: 'touch-s3-front.webp',
  stationC3: 'station-c3-front.webp',
  stationS3: 'station-s3-front.webp',
};

/** The same case seen through, its boards and modules in their places. */
export const EDGE_ENCLOSURE_INSIDE_IMAGES: Record<EdgeEnclosureId, string> = {
  tagC3: 'kit-inside.webp',
  tagS3: 'tag-s3-inside.webp',
  portableS3: 'portable-s3-inside.webp',
  portableC3: 'portable-c3-inside.webp',
  touchS3: 'touch-s3-inside.webp',
  stationC3: 'station-c3-inside.webp',
  stationS3: 'station-s3-inside.webp',
};
