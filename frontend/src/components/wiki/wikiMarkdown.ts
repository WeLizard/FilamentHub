export function withoutLeadingArticleHeading(content: string): string {
  return content.replace(/^\s{0,3}#\s+[^\r\n]+\r?\n(?:\s*\r?\n)?/, '');
}

export function plainWikiSummary(value: string): string {
  const paragraph: string[] = [];
  for (const rawLine of value.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      if (paragraph.length) break;
      continue;
    }
    if (/^#{1,6}\s+/.test(line) || /^!\[[^\]]*\]\([^)]*\)$/.test(line)) {
      if (paragraph.length) break;
      continue;
    }
    const plain = line
      .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      .replace(/`([^`]*)`/g, '$1')
      .replace(/[*_~]+/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (plain) paragraph.push(plain);
  }
  return paragraph.join(' ') || value.replace(/[#*_~`]+/g, '').replace(/\s+/g, ' ').trim();
}
