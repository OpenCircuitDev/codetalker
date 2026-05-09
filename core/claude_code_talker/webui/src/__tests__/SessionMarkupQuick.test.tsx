import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionMarkupQuick } from "../components/SessionMarkupQuick";

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const FAKE_GLOBAL_CONFIG = {
  code_fence: { kind: "describe" },
  tool_output: { kind: "describe" },
  inline_code: { kind: "identifier_only" },
  file_path: { kind: "filename" },
  todo_update: { kind: "itemize" },
  plan_block: { kind: "summarize" },
  audible_block: { kind: "speak" },
  system_reminder: { kind: "skip" },
  long_numeral: { kind: "describe" },
  subagent_dispatch: { kind: "describe" },
};

describe("SessionMarkupQuick", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (typeof url === "string" && url === "/api/markup/config") {
        return Promise.resolve({ ok: true, json: async () => FAKE_GLOBAL_CONFIG });
      }
      if (typeof url === "string" && url.includes("/overlay")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ state: {}, resolved_cfg: {} }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("renders three category headings", async () => {
    render(withClient(<SessionMarkupQuick sessionId="sid-1" />));
    fireEvent.click(screen.getByText("Markup"));
    expect(screen.getByText(/listen density/i)).toBeInTheDocument();
    expect(screen.getByText(/inline detail/i)).toBeInTheDocument();
    expect(screen.getByText(/structural pauses/i)).toBeInTheDocument();
  });

  it("renders six form rows total", async () => {
    render(withClient(<SessionMarkupQuick sessionId="sid-1" />));
    fireEvent.click(screen.getByText("Markup"));
    expect(screen.getByText("Code blocks")).toBeInTheDocument();
    expect(screen.getByText("Tool output")).toBeInTheDocument();
    expect(screen.getByText("Inline `code`")).toBeInTheDocument();
    expect(screen.getByText("File paths")).toBeInTheDocument();
    expect(screen.getByText("Todo updates")).toBeInTheDocument();
    expect(screen.getByText("Plan blocks")).toBeInTheDocument();
  });

  it("includes link to full markup panel", async () => {
    render(withClient(<SessionMarkupQuick sessionId="sid-1" />));
    fireEvent.click(screen.getByText("Markup"));
    const link = screen.getByText(/full markup panel/i);
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toBe("/ui/#markup");
  });

  it("changing a dropdown PUTs to /api/sessions/{sid}/overlay", async () => {
    render(withClient(<SessionMarkupQuick sessionId="sid-42" />));
    fireEvent.click(screen.getByText("Markup"));
    await waitFor(() => {
      const cfgCall = fetchMock.mock.calls.find(
        (c) => typeof c[0] === "string" && c[0] === "/api/markup/config"
      );
      expect(cfgCall).toBeTruthy();
    });
    const select = screen.getByLabelText(/code blocks treatment/i) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "skip" } });
    await waitFor(() => {
      const overlayCall = fetchMock.mock.calls.find(
        (c) => typeof c[0] === "string" && c[0].includes("/api/sessions/sid-42/overlay")
      );
      expect(overlayCall).toBeTruthy();
      expect(overlayCall![1].method).toBe("PUT");
      const body = JSON.parse(overlayCall![1].body as string);
      expect(body.markup.code_fence.kind).toBe("skip");
    });
  });

  it("dropdowns reflect the global resolved kinds as defaults", async () => {
    render(withClient(<SessionMarkupQuick sessionId="sid-1" />));
    fireEvent.click(screen.getByText("Markup"));
    await waitFor(() => {
      const select = screen.getByLabelText(/code blocks treatment/i) as HTMLSelectElement;
      expect(select.value).toBe("describe");
    });
    const todoSelect = screen.getByLabelText(/todo updates treatment/i) as HTMLSelectElement;
    expect(todoSelect.value).toBe("itemize");
  });
});
