export interface TocItem {
  id: string;
  text: string;
  level: number;
  sourceLine: number;
}

interface ParsedHeading {
  text: string;
  level: number;
  sourceLine: number;
}

function headingSlug(text: string): string {
  const words = text
    .normalize('NFKC')
    .toLocaleLowerCase()
    .match(/[\p{L}\p{N}]+/gu);

  return words?.join('-') || 'section';
}

function parseHeadings(content: string): ParsedHeading[] {
  const headings: ParsedHeading[] = [];
  const lines = content.split('\n');
  let fence: '`' | '~' | null = null;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (fenceMatch) {
      const marker = fenceMatch[1][0] as '`' | '~';
      fence = fence === marker ? null : (fence ?? marker);
      continue;
    }
    if (fence) continue;

    const atxMatch = line.match(/^ {0,3}(#{1,3})(?:[ \t]+|$)(.*?)(?:[ \t]+#+)?[ \t]*$/);
    if (atxMatch) {
      headings.push({
        level: atxMatch[1].length,
        text: atxMatch[2].trim(),
        sourceLine: index + 1,
      });
      continue;
    }

    const underline = lines[index + 1]?.match(/^ {0,3}(=+|-+)[ \t]*$/);
    if (line.trim() && underline) {
      headings.push({
        level: underline[1][0] === '=' ? 1 : 2,
        text: line.trim(),
        sourceLine: index + 1,
      });
      index += 1;
    }
  }

  return headings;
}

export function generateHeadingId(text: string): string {
  return headingSlug(text);
}

export function extractHeadings(content: string): TocItem[] {
  const occurrences = new Map<string, number>();

  return parseHeadings(content).map((heading) => {
    const baseId = headingSlug(heading.text);
    const occurrence = (occurrences.get(baseId) ?? 0) + 1;
    occurrences.set(baseId, occurrence);

    return {
      ...heading,
      id: occurrence === 1 ? baseId : `${baseId}-${occurrence}`,
    };
  });
}

export function headingIdsBySourceLine(content: string): ReadonlyMap<number, string> {
  return new Map(extractHeadings(content).map(({ sourceLine, id }) => [sourceLine, id]));
}
