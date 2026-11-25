/**
 * One drawing language for the Edge schematics.
 *
 * Parts are outlined in a single ink on the same ground, so the only colour in
 * a drawing is the thing it explains: the chain between modules, or the wires
 * of a harness, where each colour names one net.
 */
export const DIAGRAM_GROUND = '#17112e';
/** A board or a module: a shade above the ground, opaque so wires end at its edge. */
export const DIAGRAM_PART = '#211a3d';
/** A detail drawn on a part: a connector, a chip, a button. */
export const DIAGRAM_DETAIL = '#2c2450';
export const DIAGRAM_INK = '#e9e6f5';
export const DIAGRAM_MUTED = '#9a93b8';
export const DIAGRAM_SIGNAL = '#67e8f9';

/** Power nets keep the colours people expect from a harness. */
export const DIAGRAM_POWER = { v5: '#f0665e', v33: '#f0a13a', gnd: '#a3b1bd' } as const;
