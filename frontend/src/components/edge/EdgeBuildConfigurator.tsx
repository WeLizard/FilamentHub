import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Download } from 'lucide-react';
import {
  composeEdgeBuild,
  EDGE_ENCLOSURE_FILES,
  EDGE_ENCLOSURE_IMAGES,
  EDGE_ENCLOSURE_INSIDE_IMAGES,
  EDGE_PRESETS,
  edgeFixOptions,
  edgeOptionProblem,
  edgePresetFor,
  type EdgeBuildOptions,
} from './edgeBuilds';
import { EdgeBuildWiring, EdgePowerPath } from './EdgeBuildWiring';

const FILES = '/edge-kit/';
const subheading = 'mb-3 text-xl font-semibold text-white';
const chip = 'rounded-full border px-3 py-0.5 text-xs font-semibold';

type Choice<K extends keyof EdgeBuildOptions> = { key: K; values: EdgeBuildOptions[K][] };
const CHOICES: [Choice<'mcu'>, Choice<'display'>, Choice<'power'>] = [
  { key: 'mcu', values: ['c3', 's3'] },
  { key: 'display', values: ['none', 'oled', 'touch'] },
  { key: 'power', values: ['usb', 'battery', 'printer'] },
];
const TOGGLES = ['feedback', 'keys', 'climate'] as const;

function Segment({ active, disabled, title, onClick, children }: {
  active: boolean;
  disabled?: boolean;
  title?: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      title={title}
      onClick={onClick}
      className={`rounded-lg border px-3 py-1.5 text-sm transition-all ${
        active
          ? 'border-cyan-300/60 bg-cyan-400/15 text-white'
          : `border-white/15 bg-white/5 text-gray-200 hover:bg-white/10 ${disabled ? 'opacity-50' : ''}`
      }`}
    >
      {children}
    </button>
  );
}

export function EdgeBuildConfigurator() {
  const { t } = useTranslation();
  const [options, setOptions] = useState<EdgeBuildOptions>(EDGE_PRESETS[0].options);
  const [inside, setInside] = useState(false);
  const build = useMemo(() => composeEdgeBuild(options), [options]);
  const preset = edgePresetFor(options);
  const status = preset?.status ?? 'design';

  const choose = <K extends keyof EdgeBuildOptions>(key: K, value: EdgeBuildOptions[K]) => {
    setOptions((current) => edgeFixOptions({ ...current, [key]: value }, key));
  };
  // An option that would force another one to change is marked, not hidden.
  const forces = <K extends keyof EdgeBuildOptions>(key: K, value: EdgeBuildOptions[K]) =>
    edgeOptionProblem({ ...options, [key]: value });

  return (
    <div id="edge-builds" className="scroll-mt-24">
      <h3 className="mb-2 text-2xl font-bold text-white">{t('edgeBuilds.title')}</h3>
      <p className="mb-6 max-w-3xl text-base leading-7 text-gray-300">{t('edgeBuilds.lead')}</p>

      <div className="mb-4 flex flex-wrap gap-2">
        {EDGE_PRESETS.map((item) => (
          <Segment key={item.id} active={preset?.id === item.id} onClick={() => setOptions(item.options)}>
            {t(`edgeBuilds.presets.${item.id}.name`)}
          </Segment>
        ))}
      </div>

      <div className="mb-8 grid gap-4 rounded-xl border border-white/10 bg-white/[0.03] p-4 md:grid-cols-2">
        {CHOICES.map(({ key, values }) => (
          <fieldset key={key}>
            <legend className="mb-2 text-sm font-medium text-gray-300">{t(`edgeBuilds.options.${key}.label`)}</legend>
            <div className="flex flex-wrap gap-2">
              {values.map((value) => {
                const problem = forces(key, value);
                return (
                  <Segment
                    key={value}
                    active={options[key] === value}
                    disabled={Boolean(problem)}
                    title={problem ? t(`edgeBuilds.problems.${problem}`) : undefined}
                    onClick={() => choose(key, value)}
                  >
                    {t(`edgeBuilds.options.${key}.${value}`)}
                  </Segment>
                );
              })}
            </div>
          </fieldset>
        ))}
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-gray-300">{t('edgeBuilds.options.extras')}</legend>
          <div className="flex flex-wrap gap-2">
            {TOGGLES.map((key) => {
              const problem = forces(key, !options[key]);
              return (
                <Segment
                  key={key}
                  active={options[key] || (key === 'feedback' && options.keys)}
                  disabled={Boolean(problem) || (key === 'feedback' && options.keys)}
                  title={problem ? t(`edgeBuilds.problems.${problem}`) : key === 'feedback' && options.keys ? t('edgeBuilds.options.feedbackWithKeys') : undefined}
                  onClick={() => { if (!(key === 'feedback' && options.keys)) choose(key, !options[key]); }}
                >
                  {t(`edgeBuilds.options.${key}`)}
                </Segment>
              );
            })}
          </div>
        </fieldset>
        <p className="text-xs leading-5 text-gray-400 md:col-span-2">{t('edgeBuilds.options.rules')}</p>
      </div>

      <div className="mb-10 grid items-start gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <h4 className="text-xl font-semibold text-white">
              {preset ? t(`edgeBuilds.presets.${preset.id}.name`) : t('edgeBuilds.custom')}
            </h4>
            <span className={`${chip} ${status === 'prototype' ? 'border-amber-300/40 bg-amber-400/10 text-amber-200' : 'border-sky-300/40 bg-sky-400/10 text-sky-200'}`}>
              {t(`edgeBuilds.status.${status}`)}
            </span>
          </div>
          <p className="mb-3 text-sm leading-6 text-gray-200">
            {preset ? t(`edgeBuilds.presets.${preset.id}.text`) : t('edgeBuilds.customText')}
          </p>
          <p className="text-sm leading-6 text-gray-400">
            {build.firmware ? t('edgeBuilds.firmware.ready') : t('edgeBuilds.firmware.later')}
          </p>
        </div>
        {build.enclosure ? (
          <figure>
            {/* Both pictures share one box, so switching the view never moves the page. */}
            <div className="aspect-[16/10]">
              <img
                src={FILES + (inside ? EDGE_ENCLOSURE_INSIDE_IMAGES : EDGE_ENCLOSURE_IMAGES)[build.enclosure]}
                alt={inside
                  ? t('edgeBuilds.view.insideAlt', { name: t(`edgeBuilds.presets.${build.enclosure}.name`) })
                  : t(`edgeBuilds.enclosures.${build.enclosure}.alt`)}
                width={1600}
                height={1000}
                loading="lazy"
                className="h-full w-full object-contain"
              />
            </div>
            <figcaption className="mt-2 flex justify-center gap-2" role="group" aria-label={t('edgeBuilds.view.label')}>
              <Segment active={!inside} onClick={() => setInside(false)}>{t('edgeBuilds.view.outside')}</Segment>
              <Segment active={inside} onClick={() => setInside(true)}>{t('edgeBuilds.view.inside')}</Segment>
            </figcaption>
          </figure>
        ) : (
          <p className="rounded-xl border border-dashed border-white/15 p-6 text-sm leading-6 text-gray-400">{t('edgeBuilds.enclosures.none')}</p>
        )}
      </div>

      <div className="grid gap-10 lg:grid-cols-2">
        <div>
          <h4 className={subheading}>{t('edgeBuilds.partsTitle')}</h4>
          <ul className="space-y-1.5 text-sm leading-6 text-gray-200">
            {build.parts.map((part) => (
              <li key={part.key} className="flex gap-3">
                <span className="w-8 shrink-0 text-right font-mono text-cyan-300">{part.qty}×</span>
                <span>{t(`edgeBuilds.parts.${part.key}`)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className={subheading}>{t('edgeBuilds.powerTitle')}</h4>
          <EdgePowerPath stages={build.powerPath} />
          {build.notes.length > 0 && (
            <ul className="mt-6 space-y-2 text-sm leading-6 text-amber-100/90">
              {build.notes.map((note) => (
                <li key={note} className="border-l-2 border-amber-300/50 pl-3">{t(note)}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-10">
        <h4 className={subheading}>{t('edgeBuilds.wiring.title')}</h4>
        <EdgeBuildWiring build={build} />
      </div>

      <div className="mt-10">
        <h4 className={subheading}>{t('edgeBuilds.filesTitle')}</h4>
        {build.enclosure ? (
          <>
            <p className="mb-4 max-w-3xl text-sm leading-6 text-gray-300">{t(`edgeBuilds.enclosures.${build.enclosure}.text`)}</p>
            <p className="mb-4 max-w-3xl text-sm leading-6 text-gray-400">{t('edgeBuilds.enclosures.note')}</p>
            <ul className="flex flex-wrap gap-2">
              {EDGE_ENCLOSURE_FILES[build.enclosure].map(({ key, file }) => (
                <li key={file}>
                  <a
                    href={FILES + file}
                    download
                    className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-gray-100 transition-all hover:bg-white/10"
                  >
                    <Download className="h-4 w-4 text-cyan-300" />
                    {t(`edgeBuilds.files.${key}`)}
                  </a>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="max-w-3xl text-sm leading-6 text-gray-400">{t('edgeBuilds.enclosures.none')}</p>
        )}
      </div>
    </div>
  );
}
