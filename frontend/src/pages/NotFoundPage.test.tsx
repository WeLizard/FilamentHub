import type { ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotFoundPage } from './NotFoundPage';

const navigateMock = vi.fn();

vi.mock('react-router-dom', () => ({
  Link: ({ children, to, className }: { children: ReactNode; to: string; className?: string }) => (
    <a href={to} className={className}>{children}</a>
  ),
  useNavigate: () => navigateMock,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../components/Layout', () => ({
  Layout: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('../components/SEOHead', () => ({
  SEOHead: () => null,
}));

describe('NotFoundPage', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
  });

  it('renders localized recovery actions and the prepared mascot media', () => {
    render(
      <NotFoundPage />,
    );

    expect(screen.getByRole('heading', { name: 'notFound.title' })).toBeInTheDocument();
    expect(screen.getByText('notFound.subtitle')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'notFound.goHome' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('button', { name: 'notFound.goBack' })).toBeInTheDocument();

    const video = screen.getByTestId('not-found-mascot-video') as HTMLVideoElement;
    expect(video.autoplay).toBe(true);
    expect(video.loop).toBe(true);
    expect(video.muted).toBe(true);
    expect(video.playsInline).toBe(true);
    expect(video).toHaveAttribute('poster', '/not-found-poster.webp?v=1');
    expect(video.querySelectorAll('source')).toHaveLength(2);
    expect(video.querySelector('source[type="video/webm"]')).toHaveAttribute('src', '/404-mascot.webm?v=1');
    expect(video.querySelector('source[type="video/mp4"]')).toHaveAttribute('src', '/404-mascot.mp4?v=1');
    expect(screen.queryByRole('button', { name: 'notFound.soundOn' })).not.toBeInTheDocument();

    fireEvent.canPlay(video);
    const soundButton = screen.getByRole('button', { name: 'notFound.soundOn' });
    expect(soundButton).toHaveAttribute('aria-pressed', 'false');
    expect(soundButton).toHaveAttribute('title', 'notFound.soundOn');
    expect(soundButton).toHaveTextContent('');

    fireEvent.click(soundButton);
    expect(video.muted).toBe(false);
    const activeSoundButton = screen.getByRole('button', { name: 'notFound.soundOff' });
    expect(activeSoundButton).toHaveAttribute('aria-pressed', 'true');
    expect(activeSoundButton).toHaveAttribute('title', 'notFound.soundOff');
    expect(activeSoundButton).toHaveTextContent('');
  });

  it('keeps the poster fallback when the video cannot be loaded', () => {
    const { container } = render(
      <NotFoundPage />,
    );

    const video = screen.getByTestId('not-found-mascot-video');
    fireEvent.canPlay(video);
    expect(screen.getByRole('button', { name: 'notFound.soundOn' })).toBeInTheDocument();

    fireEvent.error(video);

    expect(screen.queryByTestId('not-found-mascot-video')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'notFound.soundOn' })).not.toBeInTheDocument();
    expect(container.querySelector('img[src="/not-found-poster.webp?v=1"]')).toBeInTheDocument();
  });

  it('renders only the static poster when reduced motion is requested', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });

    const { container } = render(
      <NotFoundPage />,
    );

    expect(screen.queryByTestId('not-found-mascot-video')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'notFound.soundOn' })).not.toBeInTheDocument();
    expect(container.querySelector('img[src="/not-found-poster.webp?v=1"]')).toBeInTheDocument();
  });
});
