export interface WikiGuideImage {
  alt: string;
  src: string;
  callouts: WikiGuideCallout[];
}

export interface WikiGuideCallout {
  label: string;
  x: number;
  y: number;
}

export interface WikiGuideStep {
  id: string;
  title: string;
  content: string;
  image: WikiGuideImage | null;
}

export interface ParsedWikiGuide {
  intro: string;
  steps: WikiGuideStep[];
}

const STEP_HEADING = /^##\s+(.+?)\s*$/gm;
const MARKDOWN_IMAGE = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/;
const GUIDE_CALLOUT = /<!--\s*guide-callout\s+x=(\d+(?:\.\d+)?)\s+y=(\d+(?:\.\d+)?)\s*:\s*(.*?)\s*-->/g;

function extractCallouts(body: string): WikiGuideCallout[] {
  return Array.from(body.matchAll(GUIDE_CALLOUT), (match) => ({
    x: Math.min(100, Math.max(0, Number(match[1]))),
    y: Math.min(100, Math.max(0, Number(match[2]))),
    label: match[3].trim(),
  })).filter((callout) => callout.label.length > 0);
}

function stepId(title: string, index: number): string {
  const normalized = title
    .toLocaleLowerCase()
    .normalize('NFKD')
    .replace(/[^\p{Letter}\p{Number}]+/gu, '-')
    .replace(/^-+|-+$/g, '');

  return normalized || `step-${index + 1}`;
}

function extractStep(title: string, body: string, index: number): WikiGuideStep {
  const imageMatch = body.match(MARKDOWN_IMAGE);
  const callouts = extractCallouts(body);
  const image = imageMatch
    ? { alt: imageMatch[1]?.trim() || title, src: imageMatch[2], callouts }
    : null;
  const bodyWithoutImage = imageMatch
    ? `${body.slice(0, imageMatch.index)}${body.slice((imageMatch.index ?? 0) + imageMatch[0].length)}`.trim()
    : body.trim();
  const content = bodyWithoutImage.replace(GUIDE_CALLOUT, '').trim();

  return {
    id: stepId(title, index),
    title: title.trim(),
    content,
    image,
  };
}

export function parseWikiGuide(content: string): ParsedWikiGuide {
  const normalized = content.replace(/\r\n?/g, '\n').trim();
  const headings = Array.from(normalized.matchAll(STEP_HEADING));

  if (headings.length === 0) {
    return { intro: normalized, steps: [] };
  }

  const intro = normalized
    .slice(0, headings[0].index)
    .trim()
    .replace(/^#\s+.+?(?:\n+|$)/, '')
    .trim();
  const steps = headings.map((heading, index) => {
    const bodyStart = (heading.index ?? 0) + heading[0].length;
    const bodyEnd = headings[index + 1]?.index ?? normalized.length;
    return extractStep(heading[1], normalized.slice(bodyStart, bodyEnd), index);
  });

  return { intro, steps };
}
