import type { ReactNode } from "react";
import type { AnswerCitation, CitationAnnotation } from "./types";

type TextPart = { text: string; offset: number };
type ListItem = { parts: TextPart[] };
type TableBlock = { headers: string[]; rows: string[][] };

type Block =
  | { type: "paragraph"; parts: TextPart[] }
  | { type: "heading"; level: 2 | 3 | 4; text: string; offset: number }
  | { type: "list"; ordered: boolean; items: ListItem[] }
  | { type: "quote"; parts: TextPart[] }
  | { type: "code"; text: string; language?: string }
  | { type: "rule" }
  | { type: "table"; table: TableBlock };

type SourceLine = {
  raw: string;
  trimmed: string;
  start: number;
  end: number;
};

export function MarkdownText({
  text,
  citations,
  citationLookup,
}: {
  text: string;
  citations?: CitationAnnotation[];
  citationLookup?: Map<string, AnswerCitation>;
}) {
  const blocks = parseBlocks(text);
  const lookup = citationLookup ?? new Map<string, AnswerCitation>();
  return (
    <div className="markdown-text">
      {blocks.map((block, index) => renderBlock(block, index, citations ?? [], lookup))}
    </div>
  );
}

function renderBlock(
  block: Block,
  index: number,
  citations: CitationAnnotation[],
  citationLookup: Map<string, AnswerCitation>,
): ReactNode {
  if (block.type === "heading") {
    const children = renderInline(block.text, block.offset, citations, citationLookup, `h-${index}`);
    if (block.level === 2) return <h2 key={index}>{children}</h2>;
    if (block.level === 3) return <h3 key={index}>{children}</h3>;
    return <h4 key={index}>{children}</h4>;
  }
  if (block.type === "paragraph") {
    return <p key={index}>{renderParts(block.parts, citations, citationLookup, `p-${index}`)}</p>;
  }
  if (block.type === "quote") {
    return <blockquote key={index}>{renderParts(block.parts, citations, citationLookup, `q-${index}`)}</blockquote>;
  }
  if (block.type === "list") {
    const ListTag = block.ordered ? "ol" : "ul";
    return (
      <ListTag key={index}>
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{renderParts(item.parts, citations, citationLookup, `li-${index}-${itemIndex}`)}</li>
        ))}
      </ListTag>
    );
  }
  if (block.type === "code") {
    return (
      <pre className="markdown-code" key={index}>
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.type === "table") {
    return (
      <div className="markdown-table-wrap" key={index}>
        <table className="markdown-table">
          <thead>
            <tr>{block.table.headers.map((header) => <th key={header}>{inlineSyntax(header, `th-${index}-${header}`)}</th>)}</tr>
          </thead>
          <tbody>
            {block.table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{inlineSyntax(cell, `td-${index}-${rowIndex}-${cellIndex}`)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <hr key={index} />;
}

function renderParts(
  parts: TextPart[],
  citations: CitationAnnotation[],
  citationLookup: Map<string, AnswerCitation>,
  keyPrefix: string,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  parts.forEach((part, index) => {
    if (index > 0) nodes.push(" ");
    nodes.push(...renderInline(part.text, part.offset, citations, citationLookup, `${keyPrefix}-${index}`));
  });
  return nodes;
}

function parseBlocks(text: string): Block[] {
  const lines = sourceLines(text);
  const blocks: Block[] = [];
  let paragraph: TextPart[] = [];
  let quote: TextPart[] = [];
  let list: { ordered: boolean; items: ListItem[] } | null = null;

  function flushParagraph() {
    if (paragraph.length > 0) blocks.push({ type: "paragraph", parts: paragraph });
    paragraph = [];
  }

  function flushQuote() {
    if (quote.length > 0) blocks.push({ type: "quote", parts: quote });
    quote = [];
  }

  function flushList() {
    if (list) blocks.push({ type: "list", ordered: list.ordered, items: list.items });
    list = null;
  }

  function flushTextBlocks() {
    flushParagraph();
    flushQuote();
    flushList();
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trimmed) {
      flushTextBlocks();
      continue;
    }

    const fence = line.trimmed.match(/^```([A-Za-z0-9_-]+)?\s*$/);
    if (fence) {
      flushTextBlocks();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trimmed.startsWith("```")) {
        codeLines.push(lines[index].raw);
        index += 1;
      }
      blocks.push({ type: "code", text: codeLines.join("\n"), language: fence[1] });
      continue;
    }

    if (isTableStart(lines, index)) {
      flushTextBlocks();
      const { table, nextIndex } = readTable(lines, index);
      blocks.push({ type: "table", table });
      index = nextIndex;
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trimmed)) {
      flushTextBlocks();
      blocks.push({ type: "rule" });
      continue;
    }

    const heading = line.raw.match(/^(\s{0,3})(#{1,4})\s+(.+)$/);
    if (heading) {
      flushTextBlocks();
      const level = Math.min(4, Math.max(2, heading[2].length)) as 2 | 3 | 4;
      const textStart = line.start + heading[1].length + heading[2].length + 1;
      blocks.push({ type: "heading", level, text: heading[3].trim(), offset: textStart });
      continue;
    }

    const unordered = line.raw.match(/^(\s*)([-*•])\s+(.+)$/);
    const ordered = line.raw.match(/^(\s*)(\d+)[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      flushQuote();
      const match = unordered ?? ordered;
      if (!match) continue;
      const isOrdered = Boolean(ordered);
      if (!list || list.ordered !== isOrdered) flushList();
      if (!list) list = { ordered: isOrdered, items: [] };
      const itemText = match[3].trim();
      const offset = line.start + match[0].indexOf(match[3]);
      list.items.push({ parts: [{ text: itemText, offset }] });
      continue;
    }

    const quoteMatch = line.raw.match(/^(\s*)>\s?(.*)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      quote.push({ text: quoteMatch[2].trim(), offset: line.start + quoteMatch[0].indexOf(quoteMatch[2]) });
      continue;
    }

    flushQuote();
    flushList();
    paragraph.push({ text: line.trimmed, offset: line.start + line.raw.indexOf(line.trimmed) });
  }

  flushTextBlocks();
  return blocks;
}

function sourceLines(text: string): SourceLine[] {
  const lines: SourceLine[] = [];
  let start = 0;
  while (start <= text.length) {
    const newline = text.indexOf("\n", start);
    const rawWithCarriage = newline === -1 ? text.slice(start) : text.slice(start, newline);
    const raw = rawWithCarriage.endsWith("\r") ? rawWithCarriage.slice(0, -1) : rawWithCarriage;
    lines.push({ raw, trimmed: raw.trim(), start, end: start + raw.length });
    if (newline === -1) break;
    start = newline + 1;
  }
  return lines;
}

function isTableStart(lines: SourceLine[], index: number): boolean {
  return Boolean(lines[index]?.raw.includes("|") && lines[index + 1] && isTableSeparator(lines[index + 1].trimmed));
}

function isTableSeparator(line: string): boolean {
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line);
}

function readTable(lines: SourceLine[], startIndex: number): { table: TableBlock; nextIndex: number } {
  const headers = splitTableCells(lines[startIndex].raw);
  const rows: string[][] = [];
  let index = startIndex + 2;
  while (index < lines.length && lines[index].raw.includes("|") && lines[index].trimmed) {
    rows.push(normalizeRow(splitTableCells(lines[index].raw), headers.length));
    index += 1;
  }
  return { table: { headers, rows }, nextIndex: index - 1 };
}

function splitTableCells(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function normalizeRow(row: string[], length: number): string[] {
  if (row.length === length) return row;
  if (row.length > length) return row.slice(0, length);
  return [...row, ...Array.from({ length: length - row.length }, () => "")];
}

function renderInline(
  text: string,
  baseOffset: number,
  citations: CitationAnnotation[],
  citationLookup: Map<string, AnswerCitation>,
  keyPrefix: string,
): ReactNode[] {
  if (citations.length === 0) return inlineSyntax(text, keyPrefix);
  const relevant = citations
    .filter((annotation) => annotation.end_index > baseOffset && annotation.end_index <= baseOffset + text.length)
    .sort((a, b) => a.end_index - b.end_index || a.start_index - b.start_index);
  const nodes: ReactNode[] = [];
  let cursor = 0;
  relevant.forEach((annotation, index) => {
    const end = Math.max(cursor, Math.min(text.length, annotation.end_index - baseOffset));
    if (end > cursor) nodes.push(...inlineSyntax(text.slice(cursor, end), `${keyPrefix}-text-${index}`));
    annotation.citation_ids.forEach((citationId) => {
      nodes.push(renderCitation(citationId, citationLookup.get(citationId), `${keyPrefix}-${citationId}-${index}`));
    });
    cursor = end;
  });
  if (cursor < text.length) nodes.push(...inlineSyntax(text.slice(cursor), `${keyPrefix}-tail`));
  return nodes;
}

function renderCitation(citationId: string, citation: AnswerCitation | undefined, key: string): ReactNode {
  const label = `[${citationId}]`;
  const title = citation?.title || citation?.url || citation?.snippet || "Source";
  if (citation?.url) {
    return (
      <a className="inline-citation" href={citation.url} key={key} rel="noreferrer" target="_blank" title={title}>
        {label}
      </a>
    );
  }
  return (
    <span className="inline-citation" key={key} title={title}>
      {label}
    </span>
  );
}

function inlineSyntax(text: string, keyPrefix = ""): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`[^`\n]+`|\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*([^*\n]+)\*\*|__([^_\n]+)__|\*([^*\n]+)\*|_([^_\n]+)_)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const token = match[0];
    if (token.startsWith("`")) {
      nodes.push(<code key={`${keyPrefix}-code-${match.index}`}>{token.slice(1, -1)}</code>);
    } else if (match[2] && safeHref(match[3])) {
      nodes.push(
        <a className="markdown-link" href={match[3]} key={`${keyPrefix}-link-${match.index}`} rel="noreferrer" target="_blank">
          {match[2]}
        </a>,
      );
    } else if (match[4] || match[5]) {
      nodes.push(<strong key={`${keyPrefix}-strong-${match.index}`}>{inlineSyntax(match[4] ?? match[5], `${keyPrefix}-strong-inner-${match.index}`)}</strong>);
    } else if (match[6] || match[7]) {
      nodes.push(<em key={`${keyPrefix}-em-${match.index}`}>{inlineSyntax(match[6] ?? match[7], `${keyPrefix}-em-inner-${match.index}`)}</em>);
    } else {
      nodes.push(token);
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function safeHref(value: string | undefined): boolean {
  if (!value) return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
