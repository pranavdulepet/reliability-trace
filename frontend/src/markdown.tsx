import type { ReactNode } from "react";
import type { AnswerCitation, CitationAnnotation } from "./types";

type Block = { type: "paragraph"; text: string } | { type: "list"; items: string[] };

export function MarkdownText({
  text,
  citations,
  citationLookup,
}: {
  text: string;
  citations?: CitationAnnotation[];
  citationLookup?: Map<string, AnswerCitation>;
}) {
  if (citations?.length) {
    return <div className="markdown-text cited-answer">{inlineCitations(text, citations, citationLookup ?? new Map())}</div>;
  }
  const blocks = parseBlocks(text);
  return (
    <div className="markdown-text">
      {blocks.map((block, index) =>
        block.type === "list" ? (
          <ul key={index}>
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex}>{inlineMarkdown(item)}</li>
            ))}
          </ul>
        ) : (
          <p key={index}>{inlineMarkdown(block.text)}</p>
        ),
      )}
    </div>
  );
}

function inlineCitations(text: string, annotations: CitationAnnotation[], citationLookup: Map<string, AnswerCitation>): ReactNode[] {
  const nodes: ReactNode[] = [];
  const sorted = [...annotations].sort((a, b) => a.end_index - b.end_index || a.start_index - b.start_index);
  let cursor = 0;
  sorted.forEach((annotation, index) => {
    const end = Math.max(0, Math.min(text.length, annotation.end_index));
    if (end < cursor) return;
    if (end > cursor) nodes.push(...inlineMarkdown(text.slice(cursor, end), `text-${index}`));
    annotation.citation_ids.forEach((citationId) => {
      const citation = citationLookup.get(citationId);
      const label = `[${citationId}]`;
      const title = citation?.title || citation?.url || citation?.snippet || "Source";
      nodes.push(
        citation?.url ? (
          <a className="inline-citation" href={citation.url} key={`${citationId}-${index}`} rel="noreferrer" target="_blank" title={title}>
            {label}
          </a>
        ) : (
          <span className="inline-citation" key={`${citationId}-${index}`} title={title}>
            {label}
          </span>
        ),
      );
    });
    cursor = end;
  });
  if (cursor < text.length) nodes.push(...inlineMarkdown(text.slice(cursor), "tail"));
  return nodes;
}

function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  function flushParagraph() {
    if (paragraph.length === 0) return;
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  }

  function flushList() {
    if (list.length === 0) return;
    blocks.push({ type: "list", items: list });
    list = [];
  }

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    const item = line.match(/^[-*]\s+(.+)$/);
    if (item) {
      flushParagraph();
      list.push(item[1]);
    } else {
      flushList();
      paragraph.push(line);
    }
  }
  flushParagraph();
  flushList();
  return blocks;
}

function inlineMarkdown(text: string, keyPrefix = ""): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*([^*]+)\*\*/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    nodes.push(<strong key={`${keyPrefix}-${match.index}-${match[1]}`}>{match[1]}</strong>);
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}
