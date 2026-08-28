import { Fragment, type ReactNode } from "react";

function inlineMarkdown(value: string): ReactNode[] {
  return value.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : <Fragment key={index}>{part}</Fragment>,
  );
}

export default function MarkdownSummary({
  children,
}: {
  children?: string | null;
}) {
  if (!children || typeof children !== "string") {
    return null;
  }

  const lines = children.replace(/\r\n/g, "\n").split(/\r?\n/);
  const blocks: ReactNode[] = [];

  for (let index = 0; index < lines.length;) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      blocks.push(<h2 key={index}>{inlineMarkdown(heading[2])}</h2>);
      index += 1;
      continue;
    }
    if (/^[-*+]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (index < lines.length && /^[-*+]\s+/.test(lines[index].trim())) {
        const item = lines[index].trim().replace(/^[-*+]\s+/, "");
        items.push(<li key={index}><span aria-hidden="true" /><span>{inlineMarkdown(item)}</span></li>);
        index += 1;
      }
      blocks.push(<ul key={`list-${index}`}>{items}</ul>);
      continue;
    }
    blocks.push(<p key={index}>{inlineMarkdown(line)}</p>);
    index += 1;
  }

  return <div className="markdown-summary">{blocks}</div>;
}
