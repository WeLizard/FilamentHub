// Walks the moves of a sliced G-code file and keeps only the totals the server needs to
// split a plate's weight by part and by role (infill, support, brim, prime tower).
// Pure and import-free so it runs in a worker, in tests and in Node alike.
//
// It follows `ToolpathEvidence.consume` in backend/app/services/calculator_gcode_parser.py
// line by line. The shared fixture in backend/tests/fixtures/gcode_toolpath_parity is
// read by both test suites, so a change on one side that is not made on the other fails.
// Words are matched as ASCII; the server's `\b` also counts non-ASCII letters, which no
// slicer writes into a command.

export const TOOLPATH_EVIDENCE_VERSION = 1;

export const TOOLPATH_LIMITS = {
  tools: 256,
  rolesPerTool: 64,
  objects: 1024,
  supportRoles: 64,
  nameChars: 200,
  toolIndex: 65535,
  // The server's request cap for the serialized evidence.
  payloadBytes: 256 * 1024,
  // Memory stays constant however large the file is, unless one line is.
  lineChars: 4 * 1024 * 1024,
} as const;

export interface ToolpathEvidence {
  version: typeof TOOLPATH_EVIDENCE_VERSION;
  extrusion_by_tool_role: Record<string, Record<string, number>>;
  extrusion_by_tool_object: Record<string, Record<string, number>>;
  observed_tool: number | null;
  observed_toolchange_count: number;
  object_names: string[];
  support_roles: string[];
}

export type ToolpathLimitReason =
  | 'tools'
  | 'roles'
  | 'objects'
  | 'support_roles'
  | 'name'
  | 'tool_index'
  | 'line'
  | 'value'
  | 'size';

/** The file is valid G-code, but its summary would not fit the contract with the server. */
export class ToolpathLimitError extends Error {
  readonly reason: ToolpathLimitReason;

  constructor(reason: ToolpathLimitReason) {
    super(`toolpath_limit:${reason}`);
    this.name = 'ToolpathLimitError';
    this.reason = reason;
  }
}

const SEMICOLON = 59;
const NEW_LINE = 10;
const CARRIAGE_RETURN = 13;

// Everything `str.splitlines` treats as the end of a line, so a line is the same line here
// as it is on the server.
const LINE_BREAKS = new Uint8Array(0x202a);
for (const code of [10, 11, 12, 13, 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029]) {
  LINE_BREAKS[code] = 1;
}

// What `str.strip` removes.
const isSpace = (code: number): boolean => {
  if (code > 32 && code < 0x85) return false;
  return code === 32
    || (code >= 9 && code <= 13)
    || (code >= 0x1c && code <= 0x1f)
    || code === 0x85
    || code === 0xa0
    || code === 0x1680
    || (code >= 0x2000 && code <= 0x200a)
    || code === 0x2028
    || code === 0x2029
    || code === 0x202f
    || code === 0x205f
    || code === 0x3000;
};

const isDigit = (code: number): boolean => code >= 48 && code <= 57;

const isWord = (code: number): boolean =>
  isDigit(code) || (code >= 65 && code <= 90) || code === 95 || (code >= 97 && code <= 122);

const EXCLUDE_OBJECT_START_RE = /^EXCLUDE_OBJECT_START\b.*?\bNAME=(\S+)/i;
const EXCLUDE_OBJECT_END_RE = /^EXCLUDE_OBJECT_END\b/i;
const OBJECT_NAME_RE = /\bNAME=(\S+)/i;
const SUPPORT_ROLE_RE = /^(?:TYPE|FEATURE):\s*(Support(?:\s+interface)?)\s*$/i;
const LABEL_START_RE = /^start printing object, unique label id: *([0-9]+)$/;
const LABEL_STOP_RE = /^stop printing object, unique label id: *([0-9]+)$/;
const LABEL_NAME_RE = /^stop printing object (.+) id:([0-9]+) copy ([0-9]+)$/;

// Leading zeros dropped, so a label is the same key here and on the server.
const canonicalLabel = (digits: string): string => digits.replace(/^0+(?=.)/, '');

// `-?(?:\d+(?:\.\d*)?|\.\d+)` starting at `from`; the value, or null when there is no number.
const readNumber = (text: string, from: number, end: number): number | null => {
  let index = from;
  if (index < end && text.charCodeAt(index) === 45) index += 1;
  const integerStart = index;
  while (index < end && isDigit(text.charCodeAt(index))) index += 1;
  if (index > integerStart) {
    if (index < end && text.charCodeAt(index) === 46) {
      index += 1;
      while (index < end && isDigit(text.charCodeAt(index))) index += 1;
    }
  } else if (index < end && text.charCodeAt(index) === 46) {
    index += 1;
    const fractionStart = index;
    while (index < end && isDigit(text.charCodeAt(index))) index += 1;
    if (index === fractionStart) return null;
  } else {
    return null;
  }
  return Number(text.substring(from, index));
};

// The first `E<number>` that starts a word, as in `.*?\bE(number)`.
const findExtrusion = (text: string, from: number, end: number): number | null => {
  for (let index = from; index < end; index += 1) {
    const code = text.charCodeAt(index);
    if ((code === 69 || code === 101) && !isWord(text.charCodeAt(index - 1))) {
      const value = readNumber(text, index + 1, end);
      if (value !== null) return value;
    }
  }
  return null;
};

const atWordBoundary = (text: string, index: number, end: number): boolean =>
  index >= end || !isWord(text.charCodeAt(index));

interface ToolState {
  lastAbsoluteE: number;
  retractionDebt: number;
  roles: Map<string, number> | null;
  objects: Map<string, number> | null;
  // Bambu object labels, until settleLabels() folds them into `objects`.
  labels: Map<string, number> | null;
}

const newToolState = (): ToolState => ({
  lastAbsoluteE: 0,
  retractionDebt: 0,
  roles: null,
  objects: null,
  labels: null,
});

const checkName = (name: string) => {
  if (name.length > TOOLPATH_LIMITS.nameChars) throw new ToolpathLimitError('name');
};

export class ToolpathWalker {
  private relativeExtrusion = false;
  private observedTool: number | null = null;
  private observedToolchangeCount = 0;
  private currentRole = 'unclassified';
  private currentObject: string | null = null;
  private currentLabel: string | null = null;
  private readonly labels = new Set<string>();
  private readonly labelNames = new Map<string, string>();
  private readonly tools = new Map<number, ToolState>();
  private current: ToolState;
  private toolsWithExtrusion = 0;
  private readonly objectNames = new Set<string>();
  private readonly supportRoles = new Set<string>();
  private carry = '';

  constructor() {
    this.current = this.toolState(0);
  }

  /** Feeds the next piece of text; pieces may end anywhere, even between "\r" and "\n". */
  push(chunk: string): void {
    const text = this.carry === '' ? chunk : this.carry + chunk;
    this.carry = '';
    const length = text.length;
    let position = 0;

    while (position < length) {
      let index = position;
      let code = 0;
      for (; index < length; index += 1) {
        code = text.charCodeAt(index);
        if (code < 0x202a && LINE_BREAKS[code] === 1) break;
      }
      // A line that has not ended yet, or a "\r" that may be half of "\r\n".
      if (index === length || (code === CARRIAGE_RETURN && index + 1 === length)) {
        if (length - position > TOOLPATH_LIMITS.lineChars) throw new ToolpathLimitError('line');
        this.carry = text.substring(position);
        return;
      }
      this.consumeLine(text, position, index);
      position = index + 1;
      if (code === CARRIAGE_RETURN && text.charCodeAt(position) === NEW_LINE) position += 1;
    }
  }

  /** Reads what is left and returns what was seen. */
  finish(): ToolpathEvidence {
    this.push('\n');
    this.settleLabels();

    const sorted = [...this.tools.entries()].sort((a, b) => a[0] - b[0]);
    const byRole: Record<string, Record<string, number>> = {};
    const byObject: Record<string, Record<string, number>> = {};
    for (const [tool, state] of sorted) {
      if (state.roles !== null) byRole[String(tool)] = Object.fromEntries(state.roles);
      if (state.objects !== null) byObject[String(tool)] = Object.fromEntries(state.objects);
    }
    return {
      version: TOOLPATH_EVIDENCE_VERSION,
      extrusion_by_tool_role: byRole,
      extrusion_by_tool_object: byObject,
      observed_tool: this.observedTool,
      observed_toolchange_count: this.observedToolchangeCount,
      object_names: [...this.objectNames],
      support_roles: [...this.supportRoles],
    };
  }

  private toolState(tool: number): ToolState {
    let state = this.tools.get(tool);
    if (state === undefined) {
      state = newToolState();
      this.tools.set(tool, state);
    }
    return state;
  }

  private consumeLine(text: string, from: number, to: number): void {
    let start = from;
    let end = to;
    while (start < end && isSpace(text.charCodeAt(start))) start += 1;
    while (end > start && isSpace(text.charCodeAt(end - 1))) end -= 1;
    if (start === end) return;

    const first = text.charCodeAt(start);
    if (first === SEMICOLON) {
      this.consumeComment(text, start + 1, end);
      return;
    }

    let commandEnd = end;
    for (let index = start + 1; index < end; index += 1) {
      if (text.charCodeAt(index) === SEMICOLON) {
        commandEnd = index;
        break;
      }
    }
    while (commandEnd > start && isSpace(text.charCodeAt(commandEnd - 1))) commandEnd -= 1;

    switch (first | 32) {
      case 103: // g
        this.consumeMove(text, start, commandEnd);
        return;
      case 109: // m
        if (commandEnd - start === 3 && text.charCodeAt(start + 1) === 56) {
          const mode = text.charCodeAt(start + 2);
          if (mode === 50) this.relativeExtrusion = false;
          else if (mode === 51) this.relativeExtrusion = true;
        }
        return;
      case 101: // e
        this.consumeObjectCommand(text, start, commandEnd, end);
        return;
      case 116: // t
        this.consumeToolChange(text, start, commandEnd);
        return;
      default:
    }
  }

  private consumeComment(text: string, from: number, end: number): void {
    let start = from;
    while (start < end && isSpace(text.charCodeAt(start))) start += 1;
    if (start === end) return;

    switch (text.charCodeAt(start)) {
      case 84: // T
      case 116: // t
        if (
          end - start >= 5
          && (text.charCodeAt(start + 1) | 32) === 121
          && (text.charCodeAt(start + 2) | 32) === 112
          && (text.charCodeAt(start + 3) | 32) === 101
          && text.charCodeAt(start + 4) === 58
        ) {
          this.setRole(text, start, 5, end);
        }
        return;
      case 70: // F
      case 102: // f
        if (
          end - start >= 8
          && text.substring(start, start + 8).toLowerCase() === 'feature:'
        ) {
          this.setRole(text, start, 8, end);
        }
        return;
      case 115: // s
        this.consumeLabelMarker(text.substring(start, end));
        return;
      default:
    }
  }

  // `;TYPE:` (Orca, Prusa) and `; FEATURE:` (Bambu) name the role of the moves that follow.
  private setRole(text: string, start: number, prefixLength: number, end: number): void {
    let roleStart = start + prefixLength;
    while (roleStart < end && isSpace(text.charCodeAt(roleStart))) roleStart += 1;
    if (roleStart === end) return;
    const role = text.substring(roleStart, end).toLowerCase();
    this.currentRole = role;
    if (role.startsWith('support')) {
      const match = SUPPORT_ROLE_RE.exec(text.substring(start, end));
      if (match !== null) this.addSupportRole(match[1].toLowerCase());
    }
  }

  private consumeLabelMarker(comment: string): void {
    if (comment.startsWith('start printing object, unique label id:')) {
      const match = LABEL_START_RE.exec(comment);
      if (match !== null) {
        const label = canonicalLabel(match[1]);
        this.currentLabel = label;
        if (!this.labels.has(label)) {
          if (this.labels.size >= TOOLPATH_LIMITS.objects) throw new ToolpathLimitError('objects');
          this.labels.add(label);
        }
      }
    } else if (comment.startsWith('stop printing object')) {
      if (LABEL_STOP_RE.test(comment)) {
        this.currentLabel = null;
      } else if (this.currentLabel !== null && !this.labelNames.has(this.currentLabel)) {
        const match = LABEL_NAME_RE.exec(comment);
        // Same shape as an EXCLUDE_OBJECT name, so copies of a part group as one.
        if (match !== null) this.labelNames.set(this.currentLabel, `${match[1]}_id_${match[2]}_copy_${match[3]}`);
      }
    }
  }

  // Folds the label-keyed counts into the object counts under the names the file gave;
  // a label that never got one is "label <id>" until the server finds its name.
  private settleLabels(): void {
    if (this.labels.size === 0) return;
    const rawNames = new Map<string, string>();
    for (const label of this.labels) {
      const rawName = this.labelNames.get(label) ?? `label ${label}`;
      rawNames.set(label, rawName);
      this.addObjectName(rawName);
    }
    for (const state of this.tools.values()) {
      if (state.labels === null) continue;
      let objects = state.objects;
      if (objects === null) {
        objects = new Map();
        state.objects = objects;
      }
      for (const [label, amount] of state.labels) {
        const rawName = rawNames.get(label) as string;
        objects.set(rawName, this.addTo(objects, rawName, amount, TOOLPATH_LIMITS.objects, 'objects'));
      }
      state.labels = null;
    }
    this.labels.clear();
    this.labelNames.clear();
  }

  private consumeObjectCommand(text: string, start: number, commandEnd: number, end: number): void {
    const command = text.substring(start, commandEnd);
    const startMatch = EXCLUDE_OBJECT_START_RE.exec(command);
    if (startMatch !== null) {
      this.currentObject = startMatch[1];
    } else if (EXCLUDE_OBJECT_END_RE.test(command)) {
      this.currentObject = null;
    } else if (
      end - start >= 21
      && text.substring(start, start + 21).toUpperCase() === 'EXCLUDE_OBJECT_DEFINE'
    ) {
      const nameMatch = OBJECT_NAME_RE.exec(text.substring(start, end));
      if (nameMatch !== null) this.addObjectName(nameMatch[1]);
    }
  }

  private consumeToolChange(text: string, start: number, commandEnd: number): void {
    let index = start + 1;
    let tool = 0;
    while (index < commandEnd) {
      const digit = text.charCodeAt(index) - 48;
      if (digit < 0 || digit > 9) break;
      // Saturates: only whether the index fits the limit matters.
      tool = Math.min(tool * 10 + digit, 1e9);
      index += 1;
    }
    if (index === start + 1 || !atWordBoundary(text, index, commandEnd)) return;
    if (tool > TOOLPATH_LIMITS.toolIndex) throw new ToolpathLimitError('tool_index');

    if (this.observedTool !== null && tool !== this.observedTool) {
      this.observedToolchangeCount += 1;
    }
    this.observedTool = tool;
    this.current = this.toolState(tool);
  }

  private consumeMove(text: string, start: number, commandEnd: number): void {
    const second = text.charCodeAt(start + 1);
    if (second === 57 && text.charCodeAt(start + 2) === 50) {
      if (!atWordBoundary(text, start + 3, commandEnd)) return;
      const value = findExtrusion(text, start + 3, commandEnd);
      if (value !== null) this.current.lastAbsoluteE = value;
      return;
    }
    // G0, G1, G2 and G3 only; G10 and G11 are not moves.
    if (!(second >= 48 && second <= 51) || !atWordBoundary(text, start + 2, commandEnd)) return;
    const value = findExtrusion(text, start + 2, commandEnd);
    if (value === null) return;

    const state = this.current;
    let delta = value;
    if (!this.relativeExtrusion) {
      delta = value - state.lastAbsoluteE;
      state.lastAbsoluteE = value;
    }

    const debt = state.retractionDebt;
    if (delta < 0) {
      state.retractionDebt = debt + Math.abs(delta);
      return;
    }
    if (delta <= 0) return;

    const recovery = Math.min(debt, delta);
    state.retractionDebt = Math.max(0, debt - recovery);
    const consumed = delta - recovery;
    if (consumed <= 0) return;

    this.addExtrusion(state, consumed);
  }

  private addExtrusion(state: ToolState, consumed: number): void {
    let roles = state.roles;
    if (roles === null) {
      if (this.toolsWithExtrusion >= TOOLPATH_LIMITS.tools) throw new ToolpathLimitError('tools');
      this.toolsWithExtrusion += 1;
      roles = new Map();
      state.roles = roles;
    }
    roles.set(this.currentRole, this.addTo(roles, this.currentRole, consumed, TOOLPATH_LIMITS.rolesPerTool, 'roles'));

    if (this.currentLabel !== null) {
      let labels = state.labels;
      if (labels === null) {
        labels = new Map();
        state.labels = labels;
      }
      labels.set(
        this.currentLabel,
        this.addTo(labels, this.currentLabel, consumed, TOOLPATH_LIMITS.objects, 'objects'),
      );
    } else if (this.currentObject !== null) {
      let objects = state.objects;
      if (objects === null) {
        objects = new Map();
        state.objects = objects;
      }
      objects.set(
        this.currentObject,
        this.addTo(objects, this.currentObject, consumed, TOOLPATH_LIMITS.objects, 'objects'),
      );
    }
  }

  private addTo(
    amounts: Map<string, number>,
    name: string,
    consumed: number,
    maxNames: number,
    reason: ToolpathLimitReason,
  ): number {
    const previous = amounts.get(name);
    if (previous === undefined) {
      if (amounts.size >= maxNames) throw new ToolpathLimitError(reason);
      checkName(name);
    }
    const total = previous === undefined ? consumed : previous + consumed;
    // An amount that overflows would be sent as null.
    if (total === Infinity) throw new ToolpathLimitError('value');
    return total;
  }

  private addObjectName(name: string): void {
    if (this.objectNames.has(name)) return;
    if (this.objectNames.size >= TOOLPATH_LIMITS.objects) throw new ToolpathLimitError('objects');
    checkName(name);
    this.objectNames.add(name);
  }

  private addSupportRole(role: string): void {
    if (this.supportRoles.has(role)) return;
    if (this.supportRoles.size >= TOOLPATH_LIMITS.supportRoles) {
      throw new ToolpathLimitError('support_roles');
    }
    checkName(role);
    this.supportRoles.add(role);
  }
}

/** The JSON text sent to the server; refuses what the server would refuse. */
export const serializeToolpath = (value: ToolpathEvidence | Record<string, ToolpathEvidence>): string => {
  const json = JSON.stringify(value);
  if (new TextEncoder().encode(json).length > TOOLPATH_LIMITS.payloadBytes) {
    throw new ToolpathLimitError('size');
  }
  return json;
};
