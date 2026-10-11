import type { ReactNode } from 'react';

/**
 * Renders the memo's small Markdown subset as React elements (never as raw HTML). Claim IDs in square
 * brackets, issue IDs in backticks and cited review IDs become links to the evidence behind them.
 */
export function Markdown({ text, claimIssue }: { text: string; claimIssue: Record<string, string> }) {
  const blocks: ReactNode[] = [];
  const lines = text.split('\n');
  let list: ReactNode[] = [];
  let table: string[][] = [];
  const flush = () => {
    if (list.length) { blocks.push(<ul key={blocks.length}>{list}</ul>); list = []; }
    if (table.length) {
      const [head, ...body] = table;
      blocks.push(
        <div className="scroll-x" key={blocks.length}><table className="data"><thead><tr>{head.map((c, i) => <th key={i}>{inline(c, claimIssue)}</th>)}</tr></thead>
          <tbody>{body.map((row, r) => <tr key={r}>{row.map((c, i) => <td key={i}>{inline(c, claimIssue)}</td>)}</tr>)}</tbody></table></div>);
      table = [];
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith('|')) {
      const cells = line.slice(1, line.endsWith('|') ? -1 : undefined).split('|').map((c) => c.trim());
      if (!cells.every((c) => /^:?-+:?$/.test(c))) { if (list.length) flush(); table.push(cells); }
      continue;
    }
    const bullet = /^(\s*)- (.*)$/.exec(line);
    if (bullet) {
      if (table.length) flush();
      // A nested bullet keeps its place in the same list, indented under its parent.
      list.push(<li key={list.length} style={bullet[1].length ? { marginLeft: 20, listStyleType: 'circle' } : undefined}>{inline(bullet[2], claimIssue)}</li>);
      continue;
    }
    flush();
    if (!line.trim()) continue;
    if (line.startsWith('# ')) blocks.push(<h1 key={blocks.length} className="text-[20px] font-semibold mb-2">{inline(line.slice(2), claimIssue)}</h1>);
    else if (line.startsWith('## ')) blocks.push(<h2 key={blocks.length}>{inline(line.slice(3), claimIssue)}</h2>);
    else if (line === '---') blocks.push(<hr key={blocks.length} />);
    else blocks.push(<p key={blocks.length}>{inline(line, claimIssue)}</p>);
  }
  flush();
  return <div className="prose">{blocks}</div>;
}

const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`|\[C\d{3}\])/g;

function inline(text: string, claimIssue: Record<string, string>): ReactNode[] {
  return text.split(TOKEN).map((part, i) => {
    if (part.startsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (/^\[C\d{3}\]$/.test(part)) {
      const id = part.slice(1, -1);
      return claimIssue[id]
        ? <a key={i} className="chip" href={`#/issues/${claimIssue[id]}`} title={`Claim ${id}: open the issue this number comes from`}>{id}</a>
        : <span key={i} className="chip">{id}</span>;
    }
    if (part.startsWith('`')) {
      const code = part.slice(1, -1);
      if (/^[a-z_]+\.[a-z0-9-]+$/.test(code)) return <a key={i} href={`#/issues/${code}`}><code>{code}</code></a>;
      if (/^[0-9a-f]{8}-[0-9a-f-]{27}$/.test(code)) return <a key={i} href={`#/reviews/${code}`} title="Open this review's trace"><code>{code.slice(0, 8)}</code></a>;
      return <code key={i}>{code}</code>;
    }
    return part;
  });
}
