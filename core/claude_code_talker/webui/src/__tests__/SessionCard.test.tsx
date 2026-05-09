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
  title: "fix auth bug",
  attached_character: {
    id: "robin",
    display_name: "Robin",
    persona: "warm",
    voice_ref: "char-robin",
  },
  is_speaking: true,
  events: [{ id: "1", kind: "speak", text: "Working", ts: Date.now() }],
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

  it("renders ticker when events present", () => {
    render(withClient(<SessionCard session={withCharacter} />));
    expect(screen.getByText("Working")).toBeInTheDocument();
  });
});
