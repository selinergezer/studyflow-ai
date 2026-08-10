import { Fragment, type ReactNode } from "react";

function inlineMarkdown(value: string): ReactNode[] {
  return value.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index} className="font-semibold text-gray-950">{part.slice(2, -2)}</strong>
      : <Fragment key={index}>{part}</Fragment>,
  );
}

export default function MarkdownSummary({ children }: { children: string }) {
  const lines = children.replace(/\\n/g, "\n").split(/\r?\n/);
  const blocks: ReactNode[] = [];

  for (let index = 0; index < lines.length;) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      blocks.push(<h2 key={index} className="mt-6 text-lg font-semibold text-gray-950">{inlineMarkdown(heading[2])}</h2>);
      index += 1;
      continue;
    }
    if (/^[-*+]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (index < lines.length && /^[-*+]\s+/.test(lines[index].trim())) {
        const item = lines[index].trim().replace(/^[-*+]\s+/, "");
        items.push(<li key={index} className="flex gap-3"><span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-blue-600" /><span>{inlineMarkdown(item)}</span></li>);
        index += 1;
      }
      blocks.push(<ul key={`list-${index}`} className="mt-4 space-y-3 text-sm leading-6 text-gray-600">{items}</ul>);
      continue;
    }
    blocks.push(<p key={index} className="mt-3 text-[15px] leading-7 text-gray-600">{inlineMarkdown(line)}</p>);
    index += 1;
  }

  return <div>{blocks}</div>;
}
