import { useEffect, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

interface AnalysisReport {
  filename: string;
  label: string | null;
  size: number;
  modified: number;
}

interface MarkdownNode {
  type: "h1" | "h2" | "h3" | "p" | "table" | "code" | "list" | "blockquote";
  content: string | MarkdownNode[];
  align?: "left" | "center" | "right";
  rows?: string[][];
}

/**
 * Simple markdown parser for MARKET_ANALYSIS_*.md files.
 * Handles: headings, paragraphs, code blocks, tables, lists, bold/italic.
 */
function parseMarkdown(text: string): MarkdownNode[] {
  const lines = text.split("\n");
  const nodes: MarkdownNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Headings
    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      nodes.push({
        type: (["h1", "h2", "h3"][level - 1] as any) || "p",
        content: headingMatch[2],
      });
      i++;
      continue;
    }

    // Code fences
    if (line.startsWith("```")) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      nodes.push({
        type: "code",
        content: codeLines.join("\n"),
      });
      continue;
    }

    // Tables (simple markdown table detection)
    if (line.includes("|")) {
      const tableLines: string[] = [line];
      i++;
      // Check for separator line
      if (i < lines.length && lines[i].match(/^\|[\s\-:]+\|/)) {
        tableLines.push(lines[i]);
        i++;
        // Collect table rows
        while (
          i < lines.length &&
          lines[i].trim().startsWith("|") &&
          !lines[i].match(/^#{1,3}/)
        ) {
          tableLines.push(lines[i]);
          i++;
        }
        // Parse table
        const rows = tableLines.map((l) =>
          l.split("|").slice(1, -1).map((c) => c.trim())
        );
        nodes.push({
          type: "table",
          content: "",
          rows: rows,
        });
        continue;
      }
    }

    // Lists
    if (line.match(/^\s*[-*]\s+/) || line.match(/^\s*\d+\.\s+/)) {
      const listItems: string[] = [];
      while (
        i < lines.length &&
        (lines[i].match(/^\s*[-*]\s+/) || lines[i].match(/^\s*\d+\.\s+/))
      ) {
        listItems.push(lines[i].replace(/^\s*[-*\d.]+\s+/, ""));
        i++;
      }
      nodes.push({
        type: "list",
        content: JSON.stringify(listItems),
      });
      continue;
    }

    // Blockquotes
    if (line.startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) {
        quoteLines.push(lines[i].substring(1).trim());
        i++;
      }
      nodes.push({
        type: "blockquote",
        content: quoteLines.join("\n"),
      });
      continue;
    }

    // Regular paragraphs
    if (line.trim()) {
      nodes.push({
        type: "p",
        content: line,
      });
    }
    i++;
  }

  return nodes;
}

/**
 * Render inline markdown within text (bold, italic, inline code, links).
 */
function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let lastIdx = 0;
  const regex = /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\((.+?)\)/g;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIdx) {
      parts.push(text.substring(lastIdx, match.index));
    }

    // Handle bold
    if (match[1]) {
      parts.push(
        <strong key={`bold-${parts.length}`} className="font-bold">
          {match[1]}
        </strong>
      );
    }
    // Handle italic
    else if (match[2]) {
      parts.push(
        <em key={`italic-${parts.length}`} className="italic">
          {match[2]}
        </em>
      );
    }
    // Handle inline code
    else if (match[3]) {
      parts.push(
        <code
          key={`code-${parts.length}`}
          className="bg-zinc-800 px-1 py-0.5 rounded text-xs font-mono text-cyan-300"
        >
          {match[3]}
        </code>
      );
    }
    // Handle links
    else if (match[4] && match[5]) {
      parts.push(
        <a
          key={`link-${parts.length}`}
          href={match[5]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan-400 hover:underline"
        >
          {match[4]}
        </a>
      );
    }

    lastIdx = regex.lastIndex;
  }

  // Add remaining text
  if (lastIdx < text.length) {
    parts.push(text.substring(lastIdx));
  }

  return parts.length > 0 ? parts : text;
}

/**
 * Render a parsed markdown node as React.
 */
function renderNode(node: MarkdownNode, idx: number): React.ReactNode {
  const contentStr = typeof node.content === 'string' ? node.content : '';

  switch (node.type) {
    case "h1":
      return (
        <h1
          key={idx}
          className="text-2xl font-bold text-[var(--color-text-1)] mt-6 mb-4"
        >
          {renderInline(contentStr)}
        </h1>
      );
    case "h2":
      return (
        <h2
          key={idx}
          className="text-xl font-bold text-[var(--color-text-1)] mt-5 mb-3"
        >
          {renderInline(contentStr)}
        </h2>
      );
    case "h3":
      return (
        <h3
          key={idx}
          className="text-lg font-bold text-[var(--color-text-1)] mt-4 mb-2"
        >
          {renderInline(contentStr)}
        </h3>
      );
    case "p":
      return (
        <p
          key={idx}
          className="text-[var(--color-text-2)] mb-3 leading-relaxed"
        >
          {renderInline(contentStr)}
        </p>
      );
    case "code":
      return (
        <pre
          key={idx}
          className="bg-zinc-900 border border-zinc-700 rounded p-3 mb-3 overflow-x-auto"
        >
          <code className="text-xs font-mono text-cyan-300">
            {contentStr}
          </code>
        </pre>
      );
    case "table":
      const rows = node.rows || [];
      if (rows.length < 2) return null;
      const headerRow = rows[0];
      const bodyRows = rows.slice(2); // skip header + separator
      return (
        <div key={idx} className="overflow-x-auto mb-4">
          <table className="text-sm border-collapse">
            <thead>
              <tr className="border-b border-zinc-600">
                {headerRow.map((cell, ci) => (
                  <th
                    key={ci}
                    className="px-3 py-2 text-left text-[var(--color-text-1)] font-semibold bg-zinc-900"
                  >
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((row, ri) => (
                <tr key={ri} className="border-b border-zinc-700">
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      className="px-3 py-2 text-[var(--color-text-2)] text-xs"
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "list":
      const items = JSON.parse(contentStr);
      return (
        <ul key={idx} className="list-disc list-inside mb-3 text-[var(--color-text-2)]">
          {items.map((item: string, li: number) => (
            <li key={li} className="mb-1">
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
    case "blockquote":
      return (
        <blockquote
          key={idx}
          className="border-l-4 border-cyan-600 pl-4 py-2 mb-3 italic text-[var(--color-text-3)]"
        >
          {renderInline(contentStr)}
        </blockquote>
      );
    default:
      return null;
  }
}

export function AnalysisTab() {
  const [reports, setReports] = useState<AnalysisReport[]>([]);
  const [selectedReport, setSelectedReport] = useState<AnalysisReport | null>(
    null
  );
  const [markdown, setMarkdown] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch list of reports on mount
  useEffect(() => {
    const fetchReports = async () => {
      try {
        const res = await fetch("/api/analysis-reports");
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        setReports(data);
        if (data.length > 0) {
          setSelectedReport(data[0]);
        }
      } catch (e) {
        setError(`Failed to load analysis reports: ${e}`);
      }
    };
    fetchReports();
  }, []);

  // Fetch markdown when selected report changes
  useEffect(() => {
    if (!selectedReport) return;

    const fetchMarkdown = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/analysis-reports/${encodeURIComponent(selectedReport.filename)}`
        );
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const text = await res.text();
        setMarkdown(text);
      } catch (e) {
        setError(`Failed to load report: ${e}`);
      } finally {
        setLoading(false);
      }
    };
    fetchMarkdown();
  }, [selectedReport]);

  const parsedNodes = markdown ? parseMarkdown(markdown) : [];

  return (
    <PanelGroup direction="horizontal" autoSaveId="cct.analysis.split">
      <Panel defaultSize={20} minSize={15}>
        <div className="h-full flex flex-col bg-[var(--color-surface-1)] border-r border-zinc-800">
          <header className="px-4 py-3 border-b border-zinc-800">
            <h2 className="text-sm font-bold text-[var(--color-text-1)]">
              Analysis Reports
            </h2>
            <p className="text-xs text-[var(--color-text-3)] mt-1">
              {reports.length} report{reports.length !== 1 ? "s" : ""}
            </p>
          </header>
          <div className="flex-1 overflow-y-auto">
            {error && !reports.length && (
              <div className="p-3 text-xs text-red-400">{error}</div>
            )}
            {reports.length === 0 && !error && (
              <div className="p-3 text-xs text-[var(--color-text-3)]">
                No analysis reports found.
              </div>
            )}
            {reports.map((report) => (
              <button
                key={report.filename}
                onClick={() => setSelectedReport(report)}
                className={
                  "w-full text-left px-4 py-3 border-b border-zinc-700 transition-colors " +
                  (selectedReport?.filename === report.filename
                    ? "bg-cyan-700 bg-opacity-30 border-l-2 border-l-cyan-500"
                    : "hover:bg-zinc-800")
                }
              >
                <div className="text-xs font-mono text-[var(--color-text-2)]">
                  {report.filename}
                </div>
                {report.label && (
                  <div className="text-xs text-cyan-400 mt-1">
                    Label: {report.label}
                  </div>
                )}
                <div className="text-xs text-[var(--color-text-3)] mt-1">
                  {new Date(report.modified * 1000).toLocaleDateString()}
                </div>
              </button>
            ))}
          </div>
        </div>
      </Panel>
      <PanelResizeHandle className="w-1 bg-zinc-800 hover:bg-cyan-600 transition-colors" />
      <Panel defaultSize={80} minSize={40}>
        <div className="h-full flex flex-col bg-[var(--color-surface-0)]">
          {selectedReport && (
            <header className="px-6 py-4 border-b border-zinc-800 bg-[var(--color-surface-1)]">
              <h2 className="text-lg font-bold text-[var(--color-text-1)]">
                {selectedReport.filename}
              </h2>
              {selectedReport.label && (
                <p className="text-xs text-cyan-400 mt-1">
                  Iteration: {selectedReport.label}
                </p>
              )}
            </header>
          )}
          <div className="flex-1 overflow-y-auto">
            {error && selectedReport && (
              <div className="p-6 text-sm text-red-400">{error}</div>
            )}
            {loading && (
              <div className="p-6 text-sm text-[var(--color-text-3)]">
                Loading...
              </div>
            )}
            {!loading && !error && selectedReport && markdown && (
              <article className="px-6 py-6 max-w-4xl">
                {parsedNodes.map((node, idx) => renderNode(node, idx))}
              </article>
            )}
            {!loading && !selectedReport && (
              <div className="p-6 text-sm text-[var(--color-text-3)]">
                Select a report to view
              </div>
            )}
          </div>
        </div>
      </Panel>
    </PanelGroup>
  );
}
