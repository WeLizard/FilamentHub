/// <reference types="w3c-web-serial" />
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle, Circle, Cpu, Loader2, Nfc, Usb } from 'lucide-react';
import { edgeNodesAPI } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { ConfirmModal } from '../ConfirmModal';
import { EDGE_NODES_QUERY_KEY } from './EdgeNodesPanel';
import { isPairingAccessDenied } from '../presetSlots/pairingPolling';
import {
  EdgeBootloaderSession,
  EdgeConsole,
  EdgeDeviceError,
  isEdgeSerialSupported,
  requestEdgePort,
  type EdgeBoardInfo,
} from '../../utils/edgeDevice';
import {
  buildEdgeProvisionLine,
  downloadEdgeImages,
  EdgeFirmwareError,
  type EdgeDeviceMessage,
  type EdgeFlashImage,
  type EdgeKit,
} from '../../utils/edgeFirmware';

type ErrorCode =
  | EdgeFirmwareError['code']
  | EdgeDeviceError['code']
  | 'no_answer'
  | 'lost';

type Phase =
  | { name: 'idle' }
  | { name: 'working'; step: 'download' | 'connect' | 'start' }
  | { name: 'board'; info: EdgeBoardInfo }
  | { name: 'writing'; progress: number }
  | { name: 'device'; firmware: string; configured: boolean; ready: boolean; nfc: boolean }
  | { name: 'error'; code: ErrorCode };

type LinkFailure = 'settings' | 'wifi_password' | 'wifi_not_found' | 'wifi_other' | 'code' | 'timeout' | 'server';

type LinkState =
  | { name: 'idle' }
  | { name: 'waiting'; pairingId: number; settings: boolean; wifi: boolean }
  | { name: 'linked'; nodeName: string }
  | { name: 'failed'; reason: LinkFailure };

type ReadState =
  | { name: 'idle' }
  | { name: 'waiting' }
  | { name: 'tag'; type: string; uid: string; uri: string | null }
  | { name: 'failure'; error: string };

const KNOWN_READ_ERRORS = [
  'no_tag_or_io_error',
  'multiple_tags_or_collision',
  'reader_disabled',
  'reader_unavailable',
];
const PIN_ORDER = ['sck', 'miso', 'mosi', 'nss', 'busy', 'rst'] as const;
const ANSWER_TIMEOUT_MS = 12000;
const LINK_POLL_MS = 3000;
const LINK_TIMEOUT_MS = 180000;

const primaryButton = 'inline-flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50';
const secondaryButton = 'inline-flex items-center justify-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-gray-200 transition-all hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50';
const textInput = 'w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-gray-500';

function errorCode(error: unknown): ErrorCode {
  if (error instanceof EdgeFirmwareError || error instanceof EdgeDeviceError) return error.code;
  return 'connection';
}

export function EdgeKitInstaller({ kit }: { kit: EdgeKit }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>({ name: 'idle' });
  const [link, setLink] = useState<LinkState>({ name: 'idle' });
  const [linkedBefore, setLinkedBefore] = useState(false);
  const [read, setRead] = useState<ReadState>({ name: 'idle' });
  const [confirm, setConfirm] = useState<'clean' | 'replace-settings' | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [nodeName, setNodeName] = useState(() => t('edgeKit.link.nameDefault'));
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const bootloader = useRef<EdgeBootloaderSession | null>(null);
  const images = useRef<EdgeFlashImage[]>([]);
  const port = useRef<SerialPort | null>(null);
  const deviceConsole = useRef<EdgeConsole | null>(null);
  const answerTimer = useRef<number | undefined>(undefined);
  // A settings line waiting for the kit to restart into its settings window.
  const lineOnBoot = useRef<string | null>(null);

  const expectAnswer = useCallback((onSilence: () => void) => {
    window.clearTimeout(answerTimer.current);
    answerTimer.current = window.setTimeout(onSilence, ANSWER_TIMEOUT_MS);
  }, []);

  const letGo = useCallback(async () => {
    window.clearTimeout(answerTimer.current);
    lineOnBoot.current = null;
    const session = bootloader.current;
    const open = deviceConsole.current;
    bootloader.current = null;
    deviceConsole.current = null;
    await session?.release();
    await open?.close();
  }, []);

  useEffect(() => () => { void letGo(); }, [letGo]);

  const fail = useCallback(async (error: unknown) => {
    await letGo();
    setPhase({ name: 'error', code: typeof error === 'string' ? error as ErrorCode : errorCode(error) });
  }, [letGo]);

  const failLink = useCallback((reason: LinkFailure) => {
    setLink((current) => (current.name === 'waiting' ? { name: 'failed', reason } : current));
  }, []);

  // While the kit is joining, the account is the one that knows when it has.
  // The watch ends on an answer or after three minutes, whichever comes first.
  const pairingId = link.name === 'waiting' ? link.pairingId : null;
  useEffect(() => {
    if (pairingId === null) return undefined;
    const startedAt = Date.now();
    const timer = window.setInterval(async () => {
      try {
        const status = await edgeNodesAPI.pairingStatus(pairingId);
        if (status.state === 'activated' && status.node) {
          setLink({ name: 'linked', nodeName: status.node.name });
          void queryClient.invalidateQueries({ queryKey: EDGE_NODES_QUERY_KEY });
        } else if (status.state === 'expired') {
          failLink('code');
        } else if (Date.now() - startedAt > LINK_TIMEOUT_MS) {
          failLink('timeout');
        }
      } catch (error) {
        // A session that ended will not come back by asking again.
        if (isPairingAccessDenied(error)) failLink('server');
        else if (Date.now() - startedAt > LINK_TIMEOUT_MS) failLink('timeout');
      }
    }, LINK_POLL_MS);
    return () => window.clearInterval(timer);
  }, [pairingId, failLink, queryClient]);

  const onMessage = useCallback((message: EdgeDeviceMessage) => {
    if (message.kind === 'boot') {
      window.clearTimeout(answerTimer.current);
      setRead({ name: 'idle' });
      setPhase({
        name: 'device', firmware: message.firmware, configured: message.configured, ready: false, nfc: false,
      });
      const line = lineOnBoot.current;
      if (line && (message.provisionWindowMs > 0 || !message.configured)) {
        lineOnBoot.current = null;
        void deviceConsole.current?.send(line).catch(() => fail('connection'));
      }
    } else if (message.kind === 'provision') {
      if (message.ok) {
        setLink((current) => (current.name === 'waiting' ? { ...current, settings: true } : current));
        // An accepted line restarts the kit; the next `boot` continues from there.
        expectAnswer(() => void fail('no_answer'));
      } else {
        failLink('settings');
      }
    } else if (message.kind === 'ready') {
      setPhase((current) => (
        current.name === 'device' ? { ...current, ready: true, nfc: message.nfc } : current
      ));
    } else if (message.kind === 'wifi') {
      if (message.connected) {
        setLink((current) => (current.name === 'waiting' ? { ...current, wifi: true } : current));
      } else {
        failLink(`wifi_${message.reason ?? 'other'}`);
      }
    } else if (message.kind === 'node') {
      if (message.state === 'linked') setLinkedBefore(true);
      if (message.state === 'code_rejected') failLink('code');
      if (message.state === 'removed') setLinkedBefore(false);
    } else {
      window.clearTimeout(answerTimer.current);
      setRead(message.kind === 'tag'
        ? { name: 'tag', type: message.type, uid: message.uid, uri: message.uri }
        : { name: 'failure', error: message.error });
    }
  }, [expectAnswer, fail, failLink]);

  const openConsole = useCallback(async (selected: SerialPort) => {
    setPhase({ name: 'working', step: 'start' });
    setRead({ name: 'idle' });
    setLinkedBefore(false);
    try {
      expectAnswer(() => void fail('no_answer'));
      deviceConsole.current = await EdgeConsole.open(selected, onMessage, () => void fail('lost'));
    } catch (error) {
      await fail(error);
    }
  }, [expectAnswer, fail, onMessage]);

  const connectForFirmware = async () => {
    const selected = await requestEdgePort();
    if (!selected) return;
    port.current = selected;
    setLog([]);
    setLink({ name: 'idle' });
    try {
      setPhase({ name: 'working', step: 'download' });
      images.current = await downloadEdgeImages(kit);
      setPhase({ name: 'working', step: 'connect' });
      bootloader.current = await EdgeBootloaderSession.open(
        selected, kit, images.current, (line) => setLog((lines) => [...lines.slice(-199), line]),
      );
      setPhase({ name: 'board', info: bootloader.current.info });
    } catch (error) {
      await fail(error);
    }
  };

  const connectInstalled = async () => {
    const selected = await requestEdgePort();
    if (!selected) return;
    port.current = selected;
    setLink({ name: 'idle' });
    await openConsole(selected);
  };

  const write = async (clean: boolean) => {
    const session = bootloader.current;
    const selected = port.current;
    if (!session || !selected) return;
    // Same layout: the application alone is replaced and the settings stay.
    const applicationOnly = session.info.layout === 'same' && !clean;
    bootloader.current = null;
    setPhase({ name: 'writing', progress: 0 });
    try {
      await session.write(
        applicationOnly
          ? images.current.filter((image) => image.address === kit.firmware.appOffset)
          : images.current,
        clean,
        (progress) => setPhase({ name: 'writing', progress }),
      );
      await openConsole(selected);
    } catch (error) {
      await fail(error);
    }
  };

  /** Asks the account for a one-time code and hands it to the kit with the network. */
  const linkToAccount = async () => {
    if (phase.name !== 'device') return;
    setSubmitting(true);
    let line: string;
    try {
      const pairing = await edgeNodesAPI.createPairing({
        name: nodeName.trim(), kind: 'esp_kit', kit_id: kit.id,
      });
      line = buildEdgeProvisionLine(kit, window.location.origin, {
        ssid, password, pairingCode: pairing.pairing_code,
      });
      setLink({ name: 'waiting', pairingId: pairing.pairing_id, settings: false, wifi: false });
    } catch {
      setLink({ name: 'failed', reason: 'server' });
      return;
    } finally {
      setSubmitting(false);
      // The password has gone into the line; the form does not keep it.
      setPassword('');
    }
    try {
      if (phase.configured) {
        // A configured kit takes settings only in the window after a restart.
        lineOnBoot.current = line;
        expectAnswer(() => void fail('no_answer'));
        await deviceConsole.current?.restart();
      } else {
        await deviceConsole.current?.send(line);
      }
    } catch (error) {
      await fail(error);
    }
  };

  const submitLink = (event: React.FormEvent) => {
    event.preventDefault();
    if (phase.name !== 'device' || !nodeName.trim() || !ssid) return;
    if (phase.configured) setConfirm('replace-settings');
    else void linkToAccount();
  };

  const readTag = async () => {
    setRead({ name: 'waiting' });
    expectAnswer(() => setRead({ name: 'failure', error: 'no_answer' }));
    try {
      await deviceConsole.current?.send('{"command":"read"}');
    } catch (error) {
      await fail(error);
    }
  };

  const reset = async () => {
    await letGo();
    setPhase({ name: 'idle' });
  };

  const onConfirm = () => {
    const pending = confirm;
    setConfirm(null);
    if (pending === 'clean') void write(true);
    if (pending === 'replace-settings') void linkToAccount();
  };

  if (!isEdgeSerialSupported()) {
    return (
      <p className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-4 text-sm text-amber-100">
        {t('edgeKit.unsupportedBrowser')}
      </p>
    );
  }

  const linkSteps = link.name === 'waiting'
    ? [
      { key: 'settings', done: link.settings },
      { key: 'wifi', done: link.wifi },
      { key: 'account', done: false },
    ]
    : [];

  return (
    <div className="space-y-5">
      <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_auto]">
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
          <dt className="text-gray-400">{t('edgeKit.board')}</dt>
          <dd className="text-white">{kit.board}</dd>
          <dt className="text-gray-400">{t('edgeKit.reader')}</dt>
          <dd className="text-white">{kit.reader}</dd>
          <dt className="text-gray-400">{t('edgeKit.firmware')}</dt>
          <dd className="text-white">{kit.firmware.version}</dd>
        </dl>
        <table className="self-start text-sm">
          <caption className="mb-1 text-left text-gray-400">{t('edgeKit.wiring')}</caption>
          <tbody>
            {PIN_ORDER.map((pin) => (
              <tr key={pin}>
                <th scope="row" className="pr-4 text-left font-medium uppercase text-gray-300">{pin}</th>
                <td className="font-mono text-white">GPIO{kit.nfcPins[pin]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {phase.name === 'idle' && (
        <div className="flex flex-wrap gap-3">
          <button type="button" className={primaryButton} onClick={() => void connectForFirmware()}>
            <Usb className="h-4 w-4" />
            {t('edgeKit.install')}
          </button>
          <button type="button" className={secondaryButton} onClick={() => void connectInstalled()}>
            <Nfc className="h-4 w-4" />
            {t('edgeKit.checkInstalled')}
          </button>
        </div>
      )}

      {phase.name === 'working' && (
        <p className="flex items-center gap-2 text-sm text-gray-200" role="status">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t(`edgeKit.working.${phase.step}`)}
        </p>
      )}

      {phase.name === 'board' && (
        <div className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-4">
          <p className="flex items-center gap-2 text-sm text-white">
            <Cpu className="h-4 w-4 text-cyan-300" />
            {t('edgeKit.boardFound', { chip: phase.info.chip, megabytes: phase.info.flashBytes >> 20 })}
          </p>
          <p className={`text-sm ${phase.info.layout === 'other' ? 'text-amber-200' : 'text-gray-300'}`}>
            {t(`edgeKit.layout.${phase.info.layout}`)}
          </p>
          <div className="flex flex-wrap gap-3">
            {phase.info.layout === 'other' ? (
              <button type="button" className={primaryButton} onClick={() => setConfirm('clean')}>
                {t('edgeKit.eraseAndInstall')}
              </button>
            ) : (
              <button type="button" className={primaryButton} onClick={() => void write(false)}>
                {t(phase.info.layout === 'same' ? 'edgeKit.update' : 'edgeKit.installNow')}
              </button>
            )}
            {phase.info.layout === 'same' && (
              <button type="button" className={secondaryButton} onClick={() => setConfirm('clean')}>
                {t('edgeKit.cleanInstall')}
              </button>
            )}
            <button type="button" className={secondaryButton} onClick={() => void reset()}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      {phase.name === 'writing' && (
        <div className="space-y-2" role="status">
          <p className="text-sm text-gray-200">{t('edgeKit.writing')}</p>
          <progress className="h-2 w-full max-w-md" value={phase.progress} max={1} />
          <p className="text-xs text-gray-400">{t('edgeKit.keepConnected')}</p>
        </div>
      )}

      {phase.name === 'device' && (
        <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-4">
          <p className="flex items-center gap-2 text-sm text-white">
            <CheckCircle className="h-4 w-4 text-emerald-300" />
            {t('edgeKit.running', { version: phase.firmware })}
          </p>

          {(link.name === 'idle' || link.name === 'failed') && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold text-white">{t('edgeKit.link.title')}</h3>
              {linkedBefore && (
                <p className="text-sm text-emerald-200">{t('edgeKit.link.alreadyLinked')}</p>
              )}
              {!user ? (
                <p className="text-sm text-gray-300">
                  {t('edgeKit.link.signIn')}{' '}
                  <Link to={`${location.pathname}?auth=login`} className="text-purple-300 underline">
                    {t('edgeKit.link.signInAction')}
                  </Link>
                </p>
              ) : (
                <form className="max-w-sm space-y-3" onSubmit={submitLink}>
                  <label className="block space-y-1 text-sm text-gray-300">
                    <span>{t('edgeKit.link.name')}</span>
                    <input
                      className={textInput}
                      value={nodeName}
                      maxLength={100}
                      required
                      onChange={(event) => setNodeName(event.target.value)}
                    />
                  </label>
                  <label className="block space-y-1 text-sm text-gray-300">
                    <span>{t('edgeKit.link.ssid')}</span>
                    <input
                      className={textInput}
                      value={ssid}
                      maxLength={32}
                      required
                      autoComplete="off"
                      onChange={(event) => setSsid(event.target.value)}
                    />
                  </label>
                  <label className="block space-y-1 text-sm text-gray-300">
                    <span>{t('edgeKit.link.password')}</span>
                    <input
                      className={textInput}
                      type="password"
                      value={password}
                      maxLength={64}
                      autoComplete="off"
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </label>
                  <p className="text-xs text-gray-400">{t('edgeKit.link.hint')}</p>
                  <button type="submit" className={primaryButton} disabled={submitting}>
                    {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                    {t('edgeKit.link.submit')}
                  </button>
                </form>
              )}
            </div>
          )}

          {phase.ready && phase.nfc && (
            <div className="space-y-2 border-t border-white/10 pt-3">
              <h3 className="text-lg font-semibold text-white">{t('edgeKit.readerTitle')}</h3>
              <p className="text-sm text-gray-300">{t('edgeKit.readHint')}</p>
              <button
                type="button"
                className={secondaryButton}
                disabled={read.name === 'waiting'}
                onClick={() => void readTag()}
              >
                {read.name === 'waiting' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Nfc className="h-4 w-4" />}
                {t('edgeKit.readTag')}
              </button>
              {read.name === 'tag' && (
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
                  <dt className="text-gray-400">{t('edgeKit.tagUid')}</dt>
                  <dd className="font-mono text-white">{read.uid}</dd>
                  <dt className="text-gray-400">{t('edgeKit.tagType')}</dt>
                  <dd className="text-white">{read.type}</dd>
                  {read.uri && (
                    <>
                      <dt className="text-gray-400">{t('edgeKit.tagLink')}</dt>
                      <dd className="break-all text-white">{read.uri}</dd>
                    </>
                  )}
                </dl>
              )}
              {read.name === 'failure' && (
                <p className="text-sm text-amber-200">
                  {KNOWN_READ_ERRORS.includes(read.error) || read.error === 'no_answer'
                    ? t(`edgeKit.readErrors.${read.error}`)
                    : t('edgeKit.readErrors.other', { code: read.error })}
                </p>
              )}
            </div>
          )}

          <div className="border-t border-white/10 pt-3">
            <button type="button" className={secondaryButton} onClick={() => void reset()}>
              {t('edgeKit.disconnect')}
            </button>
          </div>
        </div>
      )}

      {link.name === 'waiting' && (
        <ul className="space-y-2 rounded-xl border border-white/10 bg-white/5 p-4" role="status">
          {linkSteps.map((step, index) => {
            const current = !step.done && linkSteps.slice(0, index).every((earlier) => earlier.done);
            return (
              <li key={step.key} className={`flex items-center gap-2 text-sm ${step.done ? 'text-white' : 'text-gray-400'}`}>
                {step.done && <CheckCircle className="h-4 w-4 text-emerald-300" />}
                {current && <Loader2 className="h-4 w-4 animate-spin text-purple-300" />}
                {!step.done && !current && <Circle className="h-4 w-4" />}
                {t(`edgeKit.link.steps.${step.key}`)}
              </li>
            );
          })}
        </ul>
      )}

      {link.name === 'linked' && (
        <div className="space-y-2 rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-4">
          <p className="flex items-start gap-2 text-sm text-emerald-100">
            <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {t('edgeKit.link.done', { name: link.nodeName })}
          </p>
          <p className="text-sm text-gray-300">{t('edgeKit.link.usbFree')}</p>
          <Link to="/profile?tab=printer-profiles" className="inline-block text-sm text-purple-300 underline">
            {t('edgeKit.link.openProfile')}
          </Link>
        </div>
      )}

      {link.name === 'failed' && (
        <p className="flex items-start gap-2 rounded-xl border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-100">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {t(`edgeKit.link.errors.${link.reason}`)}
        </p>
      )}

      {phase.name === 'error' && (
        <div className="space-y-3 rounded-xl border border-red-400/30 bg-red-500/10 p-4">
          <p className="flex items-start gap-2 text-sm text-red-100">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {t(`edgeKit.errors.${phase.code}`)}
          </p>
          <button type="button" className={secondaryButton} onClick={() => setPhase({ name: 'idle' })}>
            {t('edgeKit.startOver')}
          </button>
        </div>
      )}

      {log.length > 0 && (
        <details className="text-xs text-gray-400">
          <summary className="cursor-pointer">{t('edgeKit.technicalLog')}</summary>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-black/40 p-3">{log.join('\n')}</pre>
        </details>
      )}

      <ConfirmModal
        isOpen={confirm !== null}
        onClose={() => setConfirm(null)}
        onConfirm={onConfirm}
        variant="warning"
        title={t(confirm === 'replace-settings' ? 'edgeKit.link.submit' : 'edgeKit.cleanInstall')}
        message={t(confirm === 'replace-settings' ? 'edgeKit.link.replaceWarning' : 'edgeKit.cleanInstallWarning')}
      />
    </div>
  );
}
