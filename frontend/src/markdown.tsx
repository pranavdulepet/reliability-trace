import type { ReactNode } from "react";

type Block = { type: "paragraph"; text: string } | { type: "list"; items: string[] };

export function MarkdownText({ text }: { text: string }) {
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

function inlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*([^*]+)\*\*/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    nodes.push(<strong key={`${match.index}-${match[1]}`}>{match[1]}</strong>);
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}
