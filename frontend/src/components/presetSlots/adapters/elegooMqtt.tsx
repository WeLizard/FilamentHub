import {
  configureProfileLanBridgeInPlugin,
  requestProfileLanObservationRefresh,
} from '../../../utils/pluginBridge';
import { CANVAS_TOPOLOGIES, centauriGeneration } from './canvas';
import type { FeedAdapter } from './types';
import { LanBridgeSetup } from './LanBridgeSetup';
import type { LanBridgeRoute } from './LanBridgeSetup';

// The plugin reads the printer's address and access code from its connection
// settings in OrcaSlicer.
const ROUTE: LanBridgeRoute = {
  provider: 'elegoo_mqtt',
  capability: 'elegoo_mqtt-lan-bridge',
  textKey: 'elegooMqtt',
  // Looked up when used, like every other call into the plugin bridge.
  configure: (...args) => configureProfileLanBridgeInPlugin('elegoo_mqtt', ...args),
  refresh: (...args) => requestProfileLanObservationRefresh('elegoo_mqtt', ...args),
};

// Elegoo's own MQTT API, spoken by the Centauri Carbon 2 (not SDCP). The
// printer tells the print state and lists its CANVAS slots, or its spool holder
// without one, with material and colour. It counts no filament used and names
// no spool, and neither the plugin nor FH Edge sends it anything, so an
// assignment is saved on the site only.
export const elegooMqttAdapter: FeedAdapter = {
  id: 'elegoo_mqtt',
  onboarding: {
    connectionProviders: ['elegoo_mqtt'],
    connectionLabelKey: 'printerSetup.connections.elegooMqtt',
    connectionHintKey: 'printerSetup.connections.elegooMqttHint',
    methods: ['orca', 'edge'],
    matchesModel: (model) => centauriGeneration(model) === 2,
    topologies: CANVAS_TOPOLOGIES,
  },
  labelKey: 'presetSlots.feedSystem.elegoo_mqtt',
  fixedSlots: null,
  capabilities: ['read', 'presence'],
  supportsEdge: true,
  edgeKinds: ['mmu', 'direct_feed'],
  orcaBridge: true,
  link: null,
  renderSetup: (context) => <LanBridgeSetup route={ROUTE} {...context} />,
};
