import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionCard } from "../components/SessionCard";
import type { Session } from "../types";

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const baseFixture: Session = {
  session_id: "abc-123",
  cwd: "/repos/myapp",
  project_slug: "codetalker",
  display_name: "Phase 22 work",
  last_modified: Date.now() / 1000 - 30,
  is_live: true,
  enabled: true,
  attached_profile: "alpha",
  has_persistent_settings: false,
};

const withCharacter: Session = {
  ...baseFixture,
  display_name: "fix auth bug",
  title: "fix auth bug",
  attached_character: {
    id: "robin",
    display_name: "Robin",
    persona: "warm",
    voice_ref: "char-robin",
  },
  is_speaking: true,
};

describe("SessionCard", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (typeof url === "string" && url.endsWith("/overlay")) {
          return Promise.resolve({ ok: true, json: async () => ({}) });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ enabled: true, active_mode: "brief" }),
        });
      })
    );
  });

  it("renders project, profile, and display name with controls", () => {
    render(withClient(<SessionCard session={baseFixture} />));
    expect(screen.getByText("codetalker")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("Phase 22 work")).toBeInTheDocument();
  });

  it("renders identity zone with title and cwd when attached_character present", () => {
    render(withClient(<SessionCard session={withCharacter} />));
    expect(screen.getByText(/fix auth bug/i)).toBeInTheDocument();
    expect(screen.getByText(/myapp/i)).toBeInTheDocument();
  });

  it("renders character avatar when attached", () => {
    render(withClient(<SessionCard session={withCharacter} />));
    expect(screen.getByTitle("Robin")).toBeInTheDocument();
  });

  it("speaking dot is active when is_speaking=true", () => {
    const { container } = render(withClient(<SessionCard session={withCharacter} />));
    const dot = container.querySelector("[class*='accent-live']");
    expect(dot).toBeTruthy();
  });

  // CCT-28 cat 3 cleanup: SessionCard no longer renders a per-card LiveTicker
  // because the backend never populates `session.events`. The dead block was
  // removed; the ActivityTab feeds the global LiveTicker from the SSE stream.
  it("does not render the dead per-card ticker", () => {
    render(withClient(<SessionCard session={withCharacter} />));
    expect(screen.queryByText("Working")).not.toBeInTheDocument();
  });

  // CCT-28 regression: when display_name and title disagree (user ran /title
  // after Claude Code emitted an ai-title), the headline must follow
  // display_name. Previously the frontend read `session.title || session.display_name`
  // which inverted the backend's resolved precedence, causing the headline
  // to flip from the user's customTitle to the auto-title on every catalog
  // rescan.
  it("CCT-28: headline follows display_name even when title disagrees", () => {
    const conflicting: Session = {
      ...baseFixture,
      display_name: "Customer rename",
      title: "auto-generated label",
    };
    render(withClient(<SessionCard session={conflicting} />));
    expect(screen.getByText("Customer rename")).toBeInTheDocument();
    expect(screen.queryByText("auto-generated label")).not.toBeInTheDocument();
  });
});
