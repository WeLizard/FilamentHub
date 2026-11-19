import { useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy, ExternalLink } from 'lucide-react';
import { EDGE_INSTALL_GUIDE_URL } from '../../utils/edgeFirmware';
import { toast } from '../Toast';

/** Follows `edge-agent/pyproject.toml` and the Home Assistant app's `config.yaml`. */
export const EDGE_RUNTIME_VERSION = '0.1.0';
const HA_REPOSITORY = 'https://github.com/WeLizard/FilamentHub';
const HA_ADD_REPOSITORY = `https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=${encodeURIComponent(HA_REPOSITORY)}`;

const LINUX_INSTALL = `python3 -m venv "$HOME/.local/share/filamenthub-edge/venv"
"$HOME/.local/share/filamenthub-edge/venv/bin/pip" install ./edge-agent
install -d -m 700 "$HOME/.config/filamenthub-edge"`;
const LINUX_SERVICE = `install -d "$HOME/.config/systemd/user"
install -m 644 edge-agent/filamenthub-edge.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now filamenthub-edge.service`;
const DOCKER_BUILD = 'docker build -t filamenthub-edge:local ./edge-agent';
const DOCKER_RUN = `docker run -d --restart unless-stopped --stop-timeout 210 \\
  --name filamenthub-edge \\
  -v /absolute/path/options.json:/data/options.json:ro \\
  -v filamenthub-edge-data:/data \\
  filamenthub-edge:local`;
const OPTIONS_EXAMPLE = `{
  "filamenthub_url": "https://filamenthub.ru",
  "connections": [
    {
      "id": "workshop",
      "adapter": "moonraker",
      "pairing_code": "FH-XXXXX-XXXXX",
      "material_provider": "happy_hare",
      "moonraker_url": "http://192.168.1.20:7125"
    }
  ]
}`;

function Command({ value }: { value: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
    }
  };
  return (
    <div className="relative mt-2">
      <pre className="overflow-x-auto rounded-lg border border-white/10 bg-black/40 p-3 pr-12 text-xs leading-5 text-gray-100">{value}</pre>
      <button
        type="button"
        onClick={copy}
        title={t(copied ? 'presetSlots.pairing.copied' : 'presetSlots.pairing.copy')}
        className="absolute right-2 top-2 rounded-md border border-white/10 bg-white/5 p-1.5 text-gray-400 transition hover:bg-purple-500/15 hover:text-purple-200"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}

function Step({ index, title, children }: { index: number; title: string; children?: ReactNode }) {
  return (
    <li className="min-w-0">
      <p className="text-sm font-medium text-white">
        <span className="mr-2 text-cyan-300">{index}.</span>
        {title}
      </p>
      {children}
    </li>
  );
}

function RuntimeHeader({ id }: { id: RuntimeId }) {
  const { t } = useTranslation();
  return (
    <div className="mb-6 space-y-5">
      <div className="grid items-center gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <h3 className="text-xl font-semibold text-white md:text-2xl">{t(`edgeRuntime.${id}.title`)}</h3>
            <span className="rounded-full border border-fuchsia-300/40 bg-fuchsia-400/10 px-3 py-0.5 text-xs font-semibold text-fuchsia-200">
              {t('edgeRuntime.alpha', { version: EDGE_RUNTIME_VERSION })}
            </span>
          </div>
          <p className="text-sm leading-6 text-gray-300">{t(`edgeRuntime.${id}.lead`)}</p>
          <p className="mt-2 text-sm leading-6 text-gray-400">{t(`edgeRuntime.${id}.fits`)}</p>
        </div>
        <img
          src={`/edge-kit/runtime-${id === 'homeAssistant' ? 'home-assistant' : id}.webp`}
          alt={t(`edgeRuntime.${id}.photoAlt`)}
          width={1200}
          height={800}
          loading="lazy"
          className="aspect-[3/2] h-auto w-full rounded-xl object-cover"
        />
      </div>
      <RuntimeDiagram id={id} />
    </div>
  );
}

type RuntimeId = 'homeAssistant' | 'linux' | 'docker';

// The FilamentHub mark from public/logo.svg, in its 358 x 289 box.
const MARK_PATHS = [
  "M143.32,251.09c-58.21,0-105.57-47.72-105.57-106.37s47.36-106.37,105.57-106.37,105.57,47.72,105.57,106.37-47.36,106.37-105.57,106.37ZM143.32,54.35c-49.39,0-89.57,40.54-89.57,90.37s40.18,90.37,89.57,90.37,89.57-40.54,89.57-90.37-40.18-90.37-89.57-90.37Z",
  "M129.62,136.72h-39.82c3.28-21.9,19.8-40.14,41.68-44.86,4.32-.93,7.06-5.19,6.13-9.51-.93-4.32-5.19-7.06-9.51-6.13-31.82,6.87-54.91,35.68-54.91,68.5,0,13.89,4.03,27.32,11.65,38.83,1.54,2.32,4.08,3.58,6.68,3.58,1.52,0,3.05-.43,4.41-1.33,3.68-2.44,4.69-7.4,2.25-11.09-4.41-6.66-7.26-14.15-8.41-22h39.84c4.42,0,8-3.58,8-8s-3.58-8-8-8Z",
  "M204.09,109.86c-2.19-3.84-7.08-5.18-10.91-2.98-3.84,2.19-5.17,7.08-2.99,10.91,3.16,5.55,5.31,11.63,6.36,17.94h-36.24l-.06-51.98c0-4.97-4.03-8.99-9-8.99h-.01c-4.97,0-9,4.04-8.99,9.01l.15,121.56c0,4.97,4.03,8.99,9,8.99h.01c4.97,0,9-4.04,8.99-9.01l-.06-51.58h36.22c-1.24,7.49-4.03,14.63-8.25,21-2.44,3.68-1.43,8.65,2.25,11.09,1.36.9,2.89,1.33,4.41,1.33,2.59,0,5.14-1.26,6.68-3.58,7.62-11.51,11.65-24.94,11.65-38.83,0-12.24-3.19-24.3-9.21-34.86Z",
  "M144.15,289.05c-20.28,0-40.54-4.37-59.39-12.88-23.87-10.78-44.3-27.66-59.09-48.83C9.93,204.81,1.09,177.89.11,149.5-1.98,96.81,26.11,45.75,71.67,19.46,96.19,5.22,123.66-1.42,151.11.25c25.66,1.57,50.71,10.25,72.42,25.12,46.3,31.69,69.71,85.55,61.1,140.6-.41,3.03-.96,6.05-1.5,8.96-1.51,8.22-2.93,15.98-1.07,23.11l.04.14c2.18,9.05,8.87,16.95,17.45,20.6l.12.05c12.35,5.51,28.27,1.4,36.26-9.36l.14-.18c3.3-4.18,5.21-9.8,6.65-14.74,1.24-4.24,5.67-6.68,9.92-5.44,4.24,1.23,6.68,5.67,5.44,9.92-1.86,6.39-4.43,13.77-9.38,20.08-12.49,16.71-36.31,22.88-55.49,14.36-13.29-5.68-23.24-17.44-26.65-31.48-2.72-10.53-.83-20.85.84-29.95.53-2.88,1.03-5.61,1.39-8.29l.03-.18c7.68-48.92-13.13-96.81-54.32-125-40.75-27.88-92.4-29.9-134.81-5.27C39.19,56.68,14.24,102.05,16.1,148.9c1.7,49.34,30.54,92.5,75.25,112.69,45.01,20.32,94.75,13.66,133.04-17.82,3.41-2.8,8.46-2.31,11.26,1.1,2.81,3.41,2.31,8.46-1.1,11.26-21.79,17.91-47.62,28.99-74.7,32.04-5.22.59-10.46.88-15.7.88Z",
];

const glyphStroke = {
  fill: 'none',
  stroke: '#e9d5ff',
  strokeWidth: 3,
  strokeLinejoin: 'round' as const,
  strokeLinecap: 'round' as const,
};

function HostGlyph({ id }: { id: RuntimeId }) {
  if (id === 'homeAssistant') return <path d="M-22 4 L0 -18 L22 4 M-15 -3 V20 H15 V-3" {...glyphStroke} />;
  if (id === 'linux') {
    return (
      <g>
        <rect x={-24} y={-17} width={48} height={36} rx={5} {...glyphStroke} />
        <path d="M-15 -5 L-7 2 L-15 9 M-3 10 H10" {...glyphStroke} />
      </g>
    );
  }
  return (
    <g>
      {[-15, 0, 15].map((x) => <rect key={x} x={x - 6} y={2} width={12} height={12} rx={2} {...glyphStroke} />)}
      {[-7.5, 7.5].map((x) => <rect key={x} x={x - 6} y={-12} width={12} height={12} rx={2} {...glyphStroke} />)}
    </g>
  );
}

/** Where Edge runs: the printer on the local network, Edge on its host, FilamentHub over HTTPS. */
function RuntimeDiagram({ id }: { id: RuntimeId }) {
  const { t } = useTranslation();
  const arrow = `edge-arrow-${id}`;
  return (
    <figure className="max-w-2xl rounded-xl border border-white/10 p-3" style={{ backgroundColor: '#17112e' }}>
      <svg viewBox="0 0 600 290" role="img" aria-label={t(`edgeRuntime.${id}.imageAlt`)} className="h-auto w-full">
        <defs>
          <marker id={arrow} viewBox="0 0 10 10" refX={9} refY={5} markerWidth={6} markerHeight={6} orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 Z" fill="#a78bfa" />
          </marker>
        </defs>

        <rect x={16} y={76} width={150} height={132} rx={14} fill="#1d3a55" stroke="#4a6d8a" />
        <g transform="translate(91 120)" fill="none" stroke="#cfe3ea" strokeWidth={3} strokeLinejoin="round">
          <rect x={-26} y={-24} width={52} height={46} rx={4} />
          <path d="M-26 -10 H26 M-6 -10 V2 H6 V-10" />
        </g>
        <text x={91} y={176} fontSize={17} fontWeight={700} textAnchor="middle" fill="#fff">{t('edgeRuntime.diagram.printer')}</text>
        <text x={91} y={194} fontSize={13} textAnchor="middle" fill="#cfe3ea">Klipper · Moonraker</text>

        <rect x={206} y={58} width={188} height={170} rx={16} fill="#3b0764" stroke="#7c3aed" strokeWidth={2} />
        <g transform="translate(300 104)"><HostGlyph id={id} /></g>
        <text x={300} y={156} fontSize={17} fontWeight={700} textAnchor="middle" fill="#fff">{t(`edgeRuntime.${id}.host`)}</text>
        <text x={300} y={176} fontSize={13} textAnchor="middle" fill="#e9d5ff">{t(`edgeRuntime.${id}.hostDetail`)}</text>
        <rect x={252} y={194} width={96} height={20} rx={10} fill="#7c3aed" />
        <text x={300} y={208} fontSize={13} fontWeight={700} textAnchor="middle" fill="#fff">FH Edge</text>

        <rect x={434} y={76} width={150} height={132} rx={14} fill="#1f1636" stroke="#5b4a85" />
        <g transform="translate(481 94) scale(0.16)" fill="#fff">
          {MARK_PATHS.map((d) => <path key={d.slice(0, 16)} d={d} />)}
        </g>
        <text x={509} y={176} fontSize={17} fontWeight={700} textAnchor="middle" fill="#fff">FilamentHub</text>
        <text x={509} y={194} fontSize={13} textAnchor="middle" fill="#cfe3ea">{t('edgeRuntime.diagram.cloud')}</text>

        <line x1={172} y1={142} x2={200} y2={142} stroke="#a78bfa" strokeWidth={3} markerStart={`url(#${arrow})`} markerEnd={`url(#${arrow})`} />
        <line x1={186} y1={154} x2={186} y2={246} stroke="#5b4a85" strokeDasharray="3 4" />
        <text x={186} y={262} fontSize={13} textAnchor="middle" fill="#cfe3ea">{t('edgeRuntime.diagram.local')}</text>
        <line x1={400} y1={142} x2={428} y2={142} stroke="#a78bfa" strokeWidth={3} markerEnd={`url(#${arrow})`} />
        <line x1={414} y1={130} x2={414} y2={42} stroke="#5b4a85" strokeDasharray="3 4" />
        <text x={414} y={30} fontSize={13} textAnchor="middle" fill="#cfe3ea">{t('edgeRuntime.diagram.outbound')}</text>
      </svg>
    </figure>
  );
}

export function EdgeRuntimeInstall() {
  const { t } = useTranslation();
  const card = 'rounded-2xl border border-white/10 bg-white/[0.03] p-5 md:p-6';
  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm leading-6 text-amber-100/90">{t('edgeRuntime.alphaNote')}</p>

      <section id="edge-home-assistant" className={`${card} scroll-mt-24`}>
        <RuntimeHeader id="homeAssistant" />
        <ol className="space-y-4">
          <Step index={1} title={t('edgeRuntime.homeAssistant.steps.repository')}>
            <Command value={HA_REPOSITORY} />
            <a href={HA_ADD_REPOSITORY} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1.5 text-sm text-purple-300 underline">
              {t('edgeRuntime.homeAssistant.openInHa')}
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </Step>
          <Step index={2} title={t('edgeRuntime.homeAssistant.steps.install')} />
          <Step index={3} title={t('edgeRuntime.homeAssistant.steps.configure')} />
          <Step index={4} title={t('edgeRuntime.homeAssistant.steps.start')} />
        </ol>
      </section>

      <section id="edge-linux" className={`${card} scroll-mt-24`}>
        <RuntimeHeader id="linux" />
        <ol className="space-y-4">
          <Step index={1} title={t('edgeRuntime.linux.steps.install')}>
            <Command value={LINUX_INSTALL} />
          </Step>
          <Step index={2} title={t('edgeRuntime.linux.steps.options')}>
            <Command value={OPTIONS_EXAMPLE} />
          </Step>
          <Step index={3} title={t('edgeRuntime.linux.steps.service')}>
            <Command value={LINUX_SERVICE} />
          </Step>
          <Step index={4} title={t('edgeRuntime.linux.steps.clearCode')} />
        </ol>
      </section>

      <section id="edge-docker" className={`${card} scroll-mt-24`}>
        <RuntimeHeader id="docker" />
        <ol className="space-y-4">
          <Step index={1} title={t('edgeRuntime.docker.steps.build')}>
            <Command value={DOCKER_BUILD} />
          </Step>
          <Step index={2} title={t('edgeRuntime.docker.steps.options')} />
          <Step index={3} title={t('edgeRuntime.docker.steps.run')}>
            <Command value={DOCKER_RUN} />
          </Step>
        </ol>
      </section>

      <a
        href={EDGE_INSTALL_GUIDE_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-purple-500"
      >
        {t('edgeSection.installGuide')}
        <ExternalLink className="h-4 w-4" />
      </a>
    </div>
  );
}
