import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle, Download, Loader2 } from 'lucide-react';
import { feedbackAPI } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { apiErrorDetail } from '../../utils/apiErrorDetail';
import { translateApiError } from '../../utils/translateApiError';
import type { EdgeKit } from '../../utils/edgeFirmware';
import { toast } from '../Toast';
import { EdgeKitInstaller } from './EdgeKitInstaller';
import { boardWiringFits, EdgeKitBoardWiring } from './EdgeKitBoardWiring';
import { EdgeKitWiring } from './EdgeKitWiring';

const FILES = '/edge-kit/';
const ENCLOSURE_SOURCE_URL = 'https://github.com/WeLizard/FilamentHub/tree/main/edge-agent/hardware/enclosure';
const PARTS = ['board', 'reader', 'screws', 'wire', 'cable', 'tags', 'filament'] as const;
const DOWNLOADS = [
  { key: 'shell', file: 'fh-edge-kit-shell.stl' },
  { key: 'base', file: 'fh-edge-kit-base.stl' },
  { key: 'mark', file: 'fh-edge-kit-mark.stl' },
  { key: 'shellStep', file: 'fh-edge-kit-shell.step' },
  { key: 'baseStep', file: 'fh-edge-kit-base.step' },
] as const;
const STEPS = [
  { key: 'print', image: 'step-print.webp' },
  { key: 'boards', image: 'step-boards.webp' },
  { key: 'close', image: 'step-close.webp' },
  { key: 'connect', image: 'kit-back.webp' },
] as const;

const subheading = 'mb-3 text-xl font-semibold text-white';

/** Tells the team that somebody wants the kit ready-made; nothing is sold here. */
function ReadyMadeRequest() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const location = useLocation();
  const [sent, setSent] = useState(false);
  const request = useMutation({
    mutationFn: () => feedbackAPI.create({
      type: 'feature',
      subject: t('edgeKit.guide.ready.subject'),
      message: t('edgeKit.guide.ready.message'),
      source: 'edge_kit_ready_made',
    }),
    onSuccess: () => setSent(true),
    onError: (error: unknown) => {
      toast.error(translateApiError(t, apiErrorDetail(error), t('common.error')));
    },
  });

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5">
      <h3 className={subheading}>{t('edgeKit.guide.ready.title')}</h3>
      <p className="mb-4 max-w-2xl text-sm leading-6 text-gray-300">{t('edgeKit.guide.ready.text')}</p>
      {sent ? (
        <p className="flex items-center gap-2 text-sm text-emerald-200">
          <CheckCircle className="h-4 w-4" />
          {t('edgeKit.guide.ready.sent')}
        </p>
      ) : user ? (
        <button
          type="button"
          disabled={request.isPending}
          onClick={() => request.mutate()}
          className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-gray-100 transition-all hover:bg-white/10 disabled:opacity-50"
        >
          {request.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          {t('edgeKit.guide.ready.action')}
        </button>
      ) : (
        <Link to={`${location.pathname}?auth=login`} className="text-sm text-purple-300 underline">
          {t('edgeKit.guide.ready.signIn')}
        </Link>
      )}
    </div>
  );
}

const TAG_WRITE_STEPS = ['place', 'open', 'connect'] as const;
const TAG_ADD_STEPS = ['read', 'material', 'save'] as const;
const TAG_USES = ['phone', 'station', 'happyHare', 'unlink'] as const;

function GuideSteps({ prefix, steps }: { prefix: string; steps: readonly string[] }) {
  const { t } = useTranslation();
  return (
    <ol className="space-y-2 text-sm leading-6 text-gray-300">
      {steps.map((step, index) => (
        <li key={step} className="flex gap-2">
          <span className="font-semibold text-cyan-300">{index + 1}.</span>
          <span>{t(`${prefix}.${step}`)}</span>
        </li>
      ))}
    </ol>
  );
}

/** Writing spool tags with the finished kit and what the tags are for. */
function EdgeKitTagsGuide() {
  const { t } = useTranslation();
  const { hash } = useLocation();
  const section = useRef<HTMLDivElement>(null);
  // The spool tags dialog links here; the page renders after the browser has
  // already looked for the anchor.
  useEffect(() => {
    if (hash === '#edge-kit-tags') section.current?.scrollIntoView({ block: 'start' });
  }, [hash]);
  const card = 'rounded-xl border border-white/10 bg-white/5 p-5';
  const cardTitle = 'mb-3 text-base font-semibold text-white';

  return (
    <div id="edge-kit-tags" ref={section} className="mt-10 scroll-mt-24">
      <h3 className={subheading}>{t('edgeKit.guide.tags.title')}</h3>
      <p className="mb-5 max-w-3xl text-sm leading-6 text-gray-300">{t('edgeKit.guide.tags.lead')}</p>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className={card}>
          <h4 className={cardTitle}>{t('edgeKit.guide.tags.write.title')}</h4>
          <GuideSteps prefix="edgeKit.guide.tags.write.steps" steps={TAG_WRITE_STEPS} />
          <p className="mt-3 text-sm leading-6 text-gray-400">{t('edgeKit.guide.tags.write.note')}</p>
        </div>
        <div className={card}>
          <h4 className={cardTitle}>{t('edgeKit.guide.tags.add.title')}</h4>
          <GuideSteps prefix="edgeKit.guide.tags.add.steps" steps={TAG_ADD_STEPS} />
        </div>
        <div className={card}>
          <h4 className={cardTitle}>{t('edgeKit.guide.tags.use.title')}</h4>
          <ul className="space-y-2 text-sm leading-6 text-gray-300">
            {TAG_USES.map((use) => (
              <li key={use} className="flex gap-3">
                <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-300" />
                {t(`edgeKit.guide.tags.use.items.${use}`)}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export function EdgeKitGuide({ kit }: { kit: EdgeKit }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  // Firmware for a kit that has not passed hardware acceptance is offered to administrators only.
  const canInstall = kit.status === 'released' || user?.role === 'admin';

  return (
    <section id="edge-kit-c3" className="mb-12 scroll-mt-24 border-t border-white/10 pt-12">
      <div className="mb-10 grid items-center gap-6 md:grid-cols-[minmax(0,0.85fr)_minmax(0,1.25fr)]">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-bold text-white md:text-3xl">{t('edgeKit.guide.title')}</h2>
            {kit.status !== 'released' && (
              <span className="rounded-full border border-amber-300/40 bg-amber-400/10 px-3 py-0.5 text-xs font-semibold text-amber-200">
                {t(`edgeSection.kitStatus.${kit.status}`)}
              </span>
            )}
          </div>
          <p className="mb-3 text-base leading-7 text-gray-200">{t('edgeKit.guide.lead')}</p>
          <p className="text-sm leading-6 text-gray-400">{t('edgeKit.guide.status')}</p>
        </div>
        <img
          src={`${FILES}kit-front.webp`}
          alt={t('edgeKit.guide.renderAlt')}
          width={1600}
          height={1000}
          loading="lazy"
          className="h-auto w-full"
        />
      </div>

      <div>
        <h3 className={subheading}>{t('edgeKit.guide.partsTitle')}</h3>
        <ul className="grid gap-x-10 gap-y-2 text-sm leading-6 text-gray-200 sm:grid-cols-2">
          {PARTS.map((part) => (
            <li key={part} className="flex gap-3">
              <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-300" />
              {t(`edgeKit.guide.parts.${part}`, { board: kit.board, reader: kit.reader })}
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-10">
        <h3 className={subheading}>{t('edgeKit.guide.wiring.title')}</h3>
        {/* The board drawing needs width to be read; a phone gets the plain list. */}
        {boardWiringFits(kit.nfcPins) && (
          <div className="hidden md:block">
            <EdgeKitBoardWiring pins={kit.nfcPins} />
          </div>
        )}
        <div className={boardWiringFits(kit.nfcPins) ? 'md:hidden' : undefined}>
          <EdgeKitWiring pins={kit.nfcPins} />
          <p className="mt-3 max-w-xl text-sm leading-6 text-gray-400">{t('edgeKit.guide.wiring.unused')}</p>
        </div>
      </div>

      <div className="mt-10">
        <h3 className={subheading}>{t('edgeKit.guide.filesTitle')}</h3>
        <p className="mb-4 max-w-3xl text-sm leading-6 text-gray-300">{t('edgeKit.guide.filesNote')}</p>
        <ul className="flex flex-wrap gap-2">
          {DOWNLOADS.map(({ key, file }) => (
            <li key={key}>
              <a
                href={FILES + file}
                download
                className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-gray-100 transition-all hover:bg-white/10"
              >
                <Download className="h-4 w-4 text-cyan-300" />
                {t(`edgeKit.guide.files.${key}`)}
              </a>
            </li>
          ))}
        </ul>
        <a href={ENCLOSURE_SOURCE_URL} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block text-sm text-purple-300 underline">
          {t('edgeKit.guide.filesSource')}
        </a>
      </div>

      <div className="mt-10">
        <h3 className={subheading}>{t('edgeKit.guide.assemblyTitle')}</h3>
        <ol className="grid gap-6 md:grid-cols-2">
          {STEPS.map(({ key, image }, index) => (
            <li key={key} className="flex flex-col">
              <img
                src={FILES + image}
                alt=""
                width={1200}
                height={800}
                loading="lazy"
                className="mb-3 aspect-[3/2] w-full rounded-xl bg-white/5 object-contain"
              />
              <p className="text-base font-semibold text-white">
                <span className="mr-2 text-cyan-300">{index + 1}.</span>
                {t(`edgeKit.guide.steps.${key}.title`)}
              </p>
              <p className="mt-1 text-sm leading-6 text-gray-300">{t(`edgeKit.guide.steps.${key}.text`)}</p>
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-10">
        <h3 className={subheading}>{t('edgeKit.guide.firmwareTitle')}</h3>
        {canInstall ? (
          <>
            {kit.status !== 'released' && (
              <p className="mb-4 max-w-3xl text-sm leading-6 text-amber-200/90">{t('edgeSection.kitAdminOnly')}</p>
            )}
            <EdgeKitInstaller kit={kit} />
          </>
        ) : (
          <p className="max-w-3xl text-sm leading-6 text-gray-300">{t('edgeKit.guide.firmwareLater')}</p>
        )}
      </div>

      {canInstall && <EdgeKitTagsGuide />}

      <div className="mt-10">
        <ReadyMadeRequest />
      </div>
    </section>
  );
}
