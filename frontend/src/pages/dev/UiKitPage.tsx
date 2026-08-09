import { useState } from 'react';
import {
  AlertTriangle,
  Bell,
  Check,
  ChevronDown,
  CircleAlert,
  CloudUpload,
  ImagePlus,
  Inbox,
  Info,
  Loader2,
  Palette,
  RefreshCw,
  Save,
  Search,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';

import { ConfirmModal } from '../../components/ConfirmModal';
import { Dropdown } from '../../components/Dropdown';
import { FilamentPreview } from '../../components/FilamentPreview';
import { InfoHint } from '../../components/InfoHint';
import { ModalOverlay } from '../../components/ModalOverlay';
import { StarRating } from '../../components/StarRating';
import { toast } from '../../components/Toast';

const scrollRows = [
  ['Catalog sync', 'Ready'],
  ['Printer profiles', '3 updated'],
  ['Filament presets', '12 available'],
  ['Spool assignments', 'Connected'],
  ['Wiki drafts', '2 awaiting review'],
  ['Brand workspace', 'Verified'],
  ['Production calculator', 'Ready'],
  ['Notifications', '4 unread'],
  ['OctoPrint Bridge', 'Connected'],
  ['Happy Hare', 'Data received'],
];

function SectionTitle({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <div className="mb-5">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300/80">{eyebrow}</p>
      <h2 className="mt-1 text-xl font-semibold text-white">{title}</h2>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{description}</p>
    </div>
  );
}

function StatusBadge({ tone, children }: { tone: 'success' | 'warning' | 'info' | 'neutral'; children: React.ReactNode }) {
  const styles = {
    success: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
    warning: 'border-amber-400/20 bg-amber-400/10 text-amber-300',
    info: 'border-cyan-400/20 bg-cyan-400/10 text-cyan-300',
    neutral: 'border-white/10 bg-white/5 text-slate-300',
  };

  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${styles[tone]}`}>
      {children}
    </span>
  );
}

function ScrollPreview({ compact = false }: { compact?: boolean }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/15 bg-slate-950/65 shadow-2xl shadow-black/20">
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
        <div>
          <p className="font-semibold text-white">Contained scroll area</p>
          <p className="mt-0.5 text-xs text-slate-500">The frame stays still; only its content scrolls.</p>
        </div>
        <StatusBadge tone="info">Firefox-safe</StatusBadge>
      </div>
      <div className={`scrollbar-contained overflow-y-auto p-3 ${compact ? 'h-52' : 'h-72'}`}>
        <div className="space-y-2 pr-1">
          {scrollRows.map(([label, value], index) => (
            <div
              key={label}
              className="flex items-center justify-between gap-4 rounded-xl border border-white/8 bg-white/[0.035] px-4 py-3 transition hover:border-purple-400/25 hover:bg-purple-400/[0.06]"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/5 text-xs font-semibold text-slate-400">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className="truncate text-sm text-slate-200">{label}</span>
              </div>
              <span className="shrink-0 text-xs text-slate-500">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function UiKitModal({ onClose }: { onClose: () => void }) {
  return (
    <ModalOverlay onClose={onClose}>
      <div className="max-h-[82vh] w-full max-w-xl overflow-hidden rounded-2xl border border-white/20 bg-slate-950 shadow-2xl shadow-purple-950/40">
        <div className="scrollbar-contained max-h-[calc(82vh-2px)] overflow-y-auto">
          <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-white/10 bg-slate-950/95 px-6 py-5 backdrop-blur-xl">
            <div>
              <p className="text-lg font-semibold text-white">Canonical modal surface</p>
              <p className="mt-1 text-sm text-slate-400">Rounded frame outside, scroll viewport inside.</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-xl border border-white/10 bg-white/5 p-2 text-slate-400 transition hover:bg-white/10 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-6 px-6 py-5">
            <div className="rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.06] p-4">
              <div className="flex gap-3">
                <Info className="mt-0.5 h-5 w-5 shrink-0 text-cyan-300" />
                <div>
                  <p className="text-sm font-semibold text-cyan-100">A calm informational block</p>
                  <p className="mt-1 text-sm leading-6 text-slate-400">
                    It explains an important consequence without competing with the primary action.
                  </p>
                </div>
              </div>
            </div>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-200">Display name</span>
              <input
                defaultValue="Voron 2.4 350"
                className="w-full rounded-xl border border-white/15 bg-white/[0.045] px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/15"
              />
              <span className="mt-1.5 block text-xs text-slate-500">Short help belongs next to the field it explains.</span>
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-200">Connection provider</span>
              <div className="relative">
                <select className="w-full rounded-xl border border-white/15 bg-white/[0.045] px-4 py-3 text-sm text-white outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/15">
                  <option>OctoPrint Bridge</option>
                  <option>Happy Hare</option>
                  <option>Bambu MQTT</option>
                </select>
                <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              </div>
            </label>

            <ScrollPreview compact />
          </div>

          <div className="sticky bottom-0 flex justify-end gap-3 border-t border-white/10 bg-slate-950/95 px-6 py-4 backdrop-blur-xl">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-white/12 bg-white/5 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-white/10"
            >
              Cancel
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-950/30 transition hover:brightness-110"
            >
              <Save className="h-4 w-4" />
              Save changes
            </button>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
}

export function UiKitPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [material, setMaterial] = useState<string | number>('petg');
  const [filterableMaterial, setFilterableMaterial] = useState<string | number>('');
  const [selectedEffects, setSelectedEffects] = useState<(string | number)[]>(['glitter', 'glossy']);
  const [rating, setRating] = useState(4);
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');

  const materialOptions = [
    { value: 'pla', label: 'PLA' },
    { value: 'petg', label: 'PETG' },
    { value: 'abs', label: 'ABS' },
    { value: 'asa', label: 'ASA' },
    { value: 'pa-cf', label: 'PA-CF' },
    { value: 'pc', label: 'PC' },
    { value: 'pva', label: 'PVA' },
    { value: 'tpu', label: 'TPU' },
  ];

  const effectOptions = [
    { value: 'glossy', label: 'Glossy' },
    { value: 'glitter', label: 'Glitter' },
    { value: 'transparent', label: 'Transparent' },
    { value: 'carbon', label: 'Carbon fiber' },
  ];

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-slate-950/45 p-6 shadow-2xl shadow-purple-950/20 sm:p-8">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-purple-500/15 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <StatusBadge tone="warning">DEV ONLY</StatusBadge>
              <StatusBadge tone="neutral">Visual reference</StatusBadge>
            </div>
            <div className="flex items-center gap-4">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-purple-500 shadow-lg shadow-purple-500/20">
                <Palette className="h-7 w-7 text-white" />
              </span>
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">FilamentHub UI Kit</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400 sm:text-base">
                  A live inventory of the interface language. This route exists only in the Vite development build.
                </p>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="inline-flex w-fit items-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-purple-950/30 transition hover:-translate-y-0.5 hover:brightness-110"
          >
            <Sparkles className="h-4 w-4" />
            Open modal reference
          </button>
        </div>
      </div>

      <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1.25fr)_minmax(340px,0.75fr)]">
        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6">
          <SectionTitle
            eyebrow="01 · Scroll behavior"
            title="Scrollbars belong inside the surface"
            description="This is the actual project scrollbar rendered by your browser. The outer radius never becomes the scroll viewport."
          />
          <ScrollPreview />
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6">
          <SectionTitle
            eyebrow="02 · Status language"
            title="Badges and notices"
            description="Color communicates state, while the text remains understandable on its own."
          />
          <div className="flex flex-wrap gap-2">
            <StatusBadge tone="success">Connected</StatusBadge>
            <StatusBadge tone="info">Synchronizing</StatusBadge>
            <StatusBadge tone="warning">Data delayed</StatusBadge>
            <StatusBadge tone="neutral">Not configured</StatusBadge>
          </div>
          <div className="mt-5 space-y-3">
            {[
              [Info, 'Information', 'A neutral explanation of what happens next.', 'border-cyan-400/15 bg-cyan-400/[0.05] text-cyan-300'],
              [AlertTriangle, 'Needs attention', 'The action is available, but the user should review this state.', 'border-amber-400/15 bg-amber-400/[0.05] text-amber-300'],
              [CircleAlert, 'Action failed', 'Say what happened and provide a recoverable next step.', 'border-rose-400/15 bg-rose-400/[0.05] text-rose-300'],
            ].map(([Icon, title, copy, classes]) => {
              const NoticeIcon = Icon as typeof Info;
              return (
                <div key={String(title)} className={`rounded-2xl border p-4 ${classes}`}>
                  <div className="flex gap-3">
                    <NoticeIcon className="mt-0.5 h-5 w-5 shrink-0" />
                    <div>
                      <p className="text-sm font-semibold text-white">{title as string}</p>
                      <p className="mt-1 text-xs leading-5 text-slate-400">{copy as string}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6 xl:col-span-2">
          <SectionTitle
            eyebrow="03 · Controls"
            title="Actions and form states"
            description="A compact comparison prevents every new screen from inventing its own radius, padding, border, and focus state."
          />

          <div className="grid gap-8 lg:grid-cols-2">
            <div>
              <p className="mb-3 text-sm font-semibold text-slate-200">Buttons</p>
              <div className="flex flex-wrap items-center gap-3">
                <button type="button" className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-950/30 transition hover:brightness-110">
                  <Check className="h-4 w-4" /> Primary
                </button>
                <button type="button" className="rounded-xl border border-white/12 bg-white/5 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-white/10">
                  Secondary
                </button>
                <button type="button" className="inline-flex items-center gap-2 rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-2.5 text-sm font-semibold text-rose-300 transition hover:bg-rose-400/15">
                  <Trash2 className="h-4 w-4" /> Destructive
                </button>
                <button type="button" aria-label="Notifications" className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-300 transition hover:bg-white/10 hover:text-white">
                  <Bell className="h-4 w-4" />
                </button>
                <button type="button" disabled className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-semibold text-slate-300">
                  Disabled
                </button>
              </div>
            </div>

            <div>
              <p className="mb-3 text-sm font-semibold text-slate-200">Fields</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate-300">Default input</span>
                  <input placeholder="Filament name" className="w-full rounded-xl border border-white/15 bg-slate-950/45 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/15" />
                  <span className="mt-1.5 block text-xs text-slate-500">Helpful context stays close.</span>
                </label>
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate-300">Error input</span>
                  <input defaultValue="Invalid value" className="w-full rounded-xl border border-rose-400/50 bg-rose-400/[0.04] px-4 py-3 text-sm text-white outline-none ring-2 ring-rose-500/10" />
                  <span className="mt-1.5 block text-xs text-rose-300">Explain how to correct the value.</span>
                </label>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6 xl:col-span-2">
          <SectionTitle
            eyebrow="04 · Surfaces"
            title="Cards should share structure, not identical content"
            description="The hierarchy remains stable: identity, useful state, primary content, then actions."
          />
          <div className="grid gap-4 md:grid-cols-3">
            {[
              [Settings2, 'Printer connection', 'Voron 2.4 350', 'Connected', 'success'],
              [Palette, 'Material profile', 'PETG · Transparent', 'Draft', 'neutral'],
              [Sparkles, 'Production calculation', 'Batch #FH-204', 'Ready', 'info'],
            ].map(([Icon, title, subtitle, status, tone]) => {
              const CardIcon = Icon as typeof Settings2;
              return (
                <article key={String(title)} className="rounded-2xl border border-white/12 bg-slate-950/45 p-5 transition hover:-translate-y-0.5 hover:border-purple-400/25 hover:bg-purple-400/[0.045]">
                  <div className="flex items-start justify-between gap-4">
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-400/10 text-purple-300">
                      <CardIcon className="h-5 w-5" />
                    </span>
                    <StatusBadge tone={tone as 'success' | 'warning' | 'info' | 'neutral'}>{status as string}</StatusBadge>
                  </div>
                  <h3 className="mt-5 font-semibold text-white">{title as string}</h3>
                  <p className="mt-1 text-sm text-slate-400">{subtitle as string}</p>
                  <button type="button" className="mt-5 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium text-slate-200 transition hover:bg-white/10">
                    Open details
                  </button>
                </article>
              );
            })}
          </div>
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6 xl:col-span-2">
          <SectionTitle
            eyebrow="05 · Real controls"
            title="Controls already used by FilamentHub"
            description="These are imported production components, not visual copies made specifically for this page."
          />

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-5">
              <Dropdown
                label={
                  <span className="inline-flex items-center gap-1.5">
                    Material type
                    <InfoHint text="The shared Dropdown is the preferred selector for searchable and grouped data." />
                  </span>
                }
                value={material}
                options={materialOptions}
                onChange={setMaterial}
              />
              <p className="mt-3 text-xs leading-5 text-slate-500">Standard single-value selector with clear action.</p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-5">
              <Dropdown
                label="Searchable selector"
                value={filterableMaterial}
                options={materialOptions}
                onChange={setFilterableMaterial}
                filterable
                emptyMessage="No matching materials"
              />
              <p className="mt-3 text-xs leading-5 text-slate-500">The same component switches to filtering for long lists.</p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-5">
              <Dropdown
                label="Multiple values"
                value=""
                options={effectOptions}
                onChange={() => undefined}
                multiple
                selectedValues={selectedEffects}
                onMultiChange={setSelectedEffects}
              />
              <p className="mt-3 text-xs leading-5 text-slate-500">Used when several independent properties may coexist.</p>
            </div>
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1fr_0.8fr]">
            <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-white">Binary setting</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">Label and consequence remain visible beside the switch.</p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={syncEnabled}
                  onClick={() => setSyncEnabled((value) => !value)}
                  className={`relative mt-0.5 h-7 w-12 shrink-0 rounded-full border transition ${
                    syncEnabled
                      ? 'border-cyan-300/30 bg-cyan-400/25'
                      : 'border-white/15 bg-white/5'
                  }`}
                >
                  <span
                    className={`absolute left-1 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-white shadow transition-transform ${
                      syncEnabled ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
              <p className={`mt-4 text-xs font-medium ${syncEnabled ? 'text-cyan-300' : 'text-slate-500'}`}>
                {syncEnabled ? 'Synchronization enabled' : 'Synchronization disabled'}
              </p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-5">
              <p className="text-sm font-semibold text-white">Segmented choice</p>
              <div className="mt-4 inline-flex rounded-xl border border-white/10 bg-black/15 p-1">
                {(['comfortable', 'compact'] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={density === value}
                    onClick={() => setDensity(value)}
                    className={`rounded-lg px-4 py-2 text-sm font-medium capitalize transition ${
                      density === value
                        ? 'bg-purple-500 text-white shadow'
                        : 'text-slate-400 hover:bg-white/5 hover:text-white'
                    }`}
                  >
                    {value}
                  </button>
                ))}
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">For two to four mutually exclusive visible options.</p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-5">
              <p className="text-sm font-semibold text-white">Rating</p>
              <div className="mt-4">
                <StarRating rating={rating} onChange={setRating} />
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">The real interactive rating component.</p>
            </div>
          </div>
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6 xl:col-span-2">
          <SectionTitle
            eyebrow="06 · Material identity"
            title="Filament visuals and technical chips"
            description="The material preview is a domain component: color, finish, transparency, fillers, and cut face belong to one visual language."
          />

          <div className="grid gap-4 md:grid-cols-3">
            {[
              {
                title: 'Matte PLA',
                color: '#8B5CF6',
                settings: { color_type: 'single' as const, colors: ['#8B5CF6'], finish: 'matte' as const },
                chips: ['PLA', '190–220 °C', 'Matte'],
              },
              {
                title: 'Glossy gradient',
                color: '#22D3EE',
                settings: { color_type: 'gradient' as const, colors: ['#22D3EE', '#8B5CF6', '#EC4899'], finish: 'glossy' as const },
                chips: ['PETG', '225–250 °C', 'Gradient'],
              },
              {
                title: 'Carbon composite',
                color: '#64748B',
                settings: { color_type: 'single' as const, colors: ['#64748B'], finish: 'matte' as const, filler: 'carbon', effects: ['carbon'] },
                chips: ['PA-CF', 'Hardened nozzle', 'Carbon fiber'],
              },
            ].map((sample) => (
              <article key={sample.title} className="overflow-hidden rounded-2xl border border-white/12 bg-slate-950/45">
                <div className="flex min-h-40 items-center justify-center border-b border-white/10 bg-gradient-to-br from-white/[0.045] to-purple-400/[0.035] p-6">
                  <FilamentPreview colorHex={sample.color} visualSettings={sample.settings} size="large" />
                </div>
                <div className="p-5">
                  <h3 className="font-semibold text-white">{sample.title}</h3>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {sample.chips.map((chip) => (
                      <span key={chip} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">
                        {chip}
                      </span>
                    ))}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6">
          <SectionTitle
            eyebrow="07 · Feedback"
            title="Toasts and confirmation"
            description="Short outcomes use the shared toast system. Consequential actions require the shared confirmation modal."
          />

          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => toast.success('Changes saved successfully.', 3500, 'ui-kit-feedback')}
              className="rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-300 transition hover:bg-emerald-400/15"
            >
              Success toast
            </button>
            <button
              type="button"
              onClick={() => toast.info('Synchronization has started.', 3500, 'ui-kit-feedback')}
              className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm font-semibold text-cyan-300 transition hover:bg-cyan-400/15"
            >
              Info toast
            </button>
            <button
              type="button"
              onClick={() => toast.warning('Some data needs your attention.', 3500, 'ui-kit-feedback')}
              className="rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm font-semibold text-amber-300 transition hover:bg-amber-400/15"
            >
              Warning toast
            </button>
            <button
              type="button"
              onClick={() => toast.error('The action could not be completed.', 3500, 'ui-kit-feedback')}
              className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm font-semibold text-rose-300 transition hover:bg-rose-400/15"
            >
              Error toast
            </button>
          </div>

          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm font-semibold text-rose-300 transition hover:bg-rose-400/15"
          >
            <Trash2 className="h-4 w-4" />
            Open confirmation modal
          </button>
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6">
          <SectionTitle
            eyebrow="08 · Data states"
            title="Loading, empty, error, and upload"
            description="A screen is not complete until its non-happy states look intentional too."
          />

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex min-h-32 flex-col items-center justify-center rounded-2xl border border-white/10 bg-slate-950/35 p-4 text-center">
              <Loader2 className="h-6 w-6 animate-spin text-purple-300" />
              <p className="mt-3 text-sm font-semibold text-white">Loading data</p>
              <p className="mt-1 text-xs text-slate-500">Keep the existing layout stable.</p>
            </div>
            <div className="flex min-h-32 flex-col items-center justify-center rounded-2xl border border-dashed border-white/15 bg-slate-950/25 p-4 text-center">
              <Inbox className="h-6 w-6 text-slate-500" />
              <p className="mt-3 text-sm font-semibold text-white">Nothing here yet</p>
              <p className="mt-1 text-xs text-slate-500">Explain the useful next action.</p>
            </div>
            <div className="flex min-h-32 flex-col items-center justify-center rounded-2xl border border-rose-400/15 bg-rose-400/[0.04] p-4 text-center">
              <CircleAlert className="h-6 w-6 text-rose-300" />
              <p className="mt-3 text-sm font-semibold text-white">Could not load data</p>
              <button type="button" className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-rose-300 hover:text-rose-200">
                <RefreshCw className="h-3.5 w-3.5" /> Retry
              </button>
            </div>
            <button type="button" className="flex min-h-32 flex-col items-center justify-center rounded-2xl border border-dashed border-purple-400/30 bg-purple-400/[0.04] p-4 text-center transition hover:border-purple-400/50 hover:bg-purple-400/[0.07]">
              <CloudUpload className="h-6 w-6 text-purple-300" />
              <p className="mt-3 text-sm font-semibold text-white">Drop a file or browse</p>
              <p className="mt-1 text-xs text-slate-500">State accepted types and limits nearby.</p>
            </button>
          </div>
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 sm:p-6 xl:col-span-2">
          <SectionTitle
            eyebrow="09 · Collections"
            title="Toolbar, table, and progressive loading"
            description="Dense administrative data and user-facing collections need different density, but share the same controls and states."
          />

          <div className="overflow-hidden rounded-2xl border border-white/12 bg-slate-950/40">
            <div className="flex flex-col gap-3 border-b border-white/10 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="relative min-w-0 flex-1 sm:max-w-md">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input
                  placeholder="Search records..."
                  className="w-full rounded-xl border border-white/12 bg-white/[0.045] py-2.5 pl-10 pr-4 text-sm text-white outline-none placeholder:text-slate-600 focus:border-purple-400/50 focus:ring-2 focus:ring-purple-500/10"
                />
              </div>
              <div className="flex items-center gap-2">
                <button type="button" className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-slate-300 transition hover:bg-white/10">
                  <SlidersHorizontal className="h-4 w-4" /> Filters
                </button>
                <button type="button" className="inline-flex items-center gap-2 rounded-xl bg-purple-500 px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-purple-400">
                  <ImagePlus className="h-4 w-4" /> Add item
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-sm">
                <thead className="border-b border-white/10 bg-white/[0.025] text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Type</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Updated</th>
                    <th className="px-4 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/8">
                  {[
                    ['PLA Basic', 'Material', 'Published', '2 min ago'],
                    ['Voron 2.4', 'Printer', 'Verified', '18 min ago'],
                    ['PETG Fast', 'Preset', 'Draft', 'Yesterday'],
                  ].map(([name, type, status, updated], index) => (
                    <tr key={name} className="transition hover:bg-white/[0.035]">
                      <td className="px-4 py-3.5 font-medium text-white">{name}</td>
                      <td className="px-4 py-3.5 text-slate-400">{type}</td>
                      <td className="px-4 py-3.5">
                        <StatusBadge tone={index === 2 ? 'neutral' : 'success'}>{status}</StatusBadge>
                      </td>
                      <td className="px-4 py-3.5 text-slate-500">{updated}</td>
                      <td className="px-4 py-3.5 text-right">
                        <button type="button" className="rounded-lg p-2 text-slate-400 transition hover:bg-white/10 hover:text-white" aria-label={`Open ${name}`}>
                          <Settings2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-center border-t border-white/10 p-4">
              <button type="button" className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-300 transition hover:bg-white/10 hover:text-white">
                <RefreshCw className="h-4 w-4" /> Load more
              </button>
            </div>
          </div>
        </section>
      </div>

      {modalOpen && <UiKitModal onClose={() => setModalOpen(false)} />}
      <ConfirmModal
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => {
          setConfirmOpen(false);
          toast.success('The example action was confirmed.', 3500, 'ui-kit-confirmation');
        }}
        variant="danger"
        title="Delete this example?"
        message="This preview demonstrates the shared confirmation flow. No real data will be changed."
        confirmText="Delete example"
        cancelText="Keep it"
      />
    </div>
  );
}
