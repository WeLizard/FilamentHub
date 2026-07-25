import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Home, Volume2, VolumeX } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Layout } from '../components/Layout';
import { SEOHead } from '../components/SEOHead';
import './NotFoundPage.css';

const NOT_FOUND_MEDIA_VERSION = '1';
const NOT_FOUND_MEDIA = {
  poster: `/not-found-poster.webp?v=${NOT_FOUND_MEDIA_VERSION}`,
  webm: `/404-mascot.webm?v=${NOT_FOUND_MEDIA_VERSION}`,
  mp4: `/404-mascot.mp4?v=${NOT_FOUND_MEDIA_VERSION}`,
} as const;

export function NotFoundPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoReady, setVideoReady] = useState(false);
  const [videoFailed, setVideoFailed] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(
    () => typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handleChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        setSoundEnabled(false);
      }
      setPrefersReducedMotion(event.matches);
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  const handleGoBack = () => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }

    navigate('/');
  };

  const handleSoundToggle = () => {
    const video = videoRef.current;
    if (!video) {
      return;
    }

    const enableSound = video.muted;
    video.muted = !enableSound;
    setSoundEnabled(enableSound);
  };

  return (
    <Layout>
      <SEOHead
        title={t('notFound.title')}
        description={t('notFound.subtitle')}
        url={typeof window === 'undefined' ? undefined : window.location.pathname}
        allowAI={false}
      />
      <section
        className="not-found-page relative isolate mx-auto flex min-h-[68vh] w-full max-w-7xl items-center py-5 sm:py-8 lg:py-10"
        aria-labelledby="not-found-title"
      >
        <div className="not-found-page__panel relative grid w-full lg:grid-cols-[0.86fr_1.14fr]">
          <div className="not-found-page__copy relative z-10 flex flex-col justify-center px-6 py-9 sm:px-10 sm:py-12 lg:px-14 lg:py-16">
            <p className="mb-5 flex items-center gap-3 text-xs font-bold uppercase tracking-[0.3em] text-fuchsia-200/90">
              <span className="h-px w-9 bg-gradient-to-r from-fuchsia-300 to-transparent" aria-hidden="true" />
              404
            </p>

            <h1
              id="not-found-title"
              className="max-w-xl text-4xl font-black leading-[0.98] tracking-[-0.04em] text-white sm:text-5xl lg:text-6xl"
            >
              {t('notFound.title')}
            </h1>

            <p className="mt-5 max-w-lg text-base leading-7 text-slate-300 sm:text-lg">
              {t('notFound.subtitle')}
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                to="/"
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-fuchsia-500 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-fuchsia-950/30 transition duration-200 hover:-translate-y-0.5 hover:bg-fuchsia-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-200 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
              >
                <Home className="h-4 w-4" aria-hidden="true" />
                {t('notFound.goHome')}
              </Link>

              <button
                type="button"
                onClick={handleGoBack}
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-5 py-3 text-sm font-bold text-slate-100 transition duration-200 hover:-translate-y-0.5 hover:border-white/30 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                {t('notFound.goBack')}
              </button>
            </div>
          </div>

          <div className="not-found-page__art relative flex min-h-[22rem] items-center justify-center px-0 py-4 sm:min-h-[29rem] sm:px-2 lg:min-h-[36rem] lg:py-8">
            <div className="not-found-page__media relative z-10 aspect-square" aria-hidden="true">
              <img
                src={NOT_FOUND_MEDIA.poster}
                alt=""
                className={`not-found-page__poster absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${videoReady ? 'motion-safe:opacity-0' : 'opacity-100'}`}
              />

              {!videoFailed && !prefersReducedMotion && (
                <video
                  ref={videoRef}
                  data-testid="not-found-mascot-video"
                  className={`not-found-page__video absolute inset-0 h-full w-full object-cover transition-opacity duration-500 motion-reduce:hidden ${videoReady ? 'opacity-100' : 'opacity-0'}`}
                  autoPlay
                  loop
                  muted={!soundEnabled}
                  playsInline
                  preload="metadata"
                  poster={NOT_FOUND_MEDIA.poster}
                  tabIndex={-1}
                  onCanPlay={() => setVideoReady(true)}
                  onError={() => {
                    setVideoReady(false);
                    setVideoFailed(true);
                    setSoundEnabled(false);
                  }}
                >
                  <source src={NOT_FOUND_MEDIA.webm} type="video/webm" />
                  <source src={NOT_FOUND_MEDIA.mp4} type="video/mp4" />
                </video>
              )}
            </div>

            {videoReady && !videoFailed && !prefersReducedMotion && (
              <button
                type="button"
                className="not-found-page__sound-control"
                aria-label={t(soundEnabled ? 'notFound.soundOff' : 'notFound.soundOn')}
                aria-pressed={soundEnabled}
                title={t(soundEnabled ? 'notFound.soundOff' : 'notFound.soundOn')}
                onClick={handleSoundToggle}
              >
                {soundEnabled
                  ? <Volume2 className="h-4 w-4" aria-hidden="true" />
                  : <VolumeX className="h-4 w-4" aria-hidden="true" />}
              </button>
            )}
          </div>
        </div>
      </section>
    </Layout>
  );
}
