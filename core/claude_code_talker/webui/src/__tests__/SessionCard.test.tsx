import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionCard } from "../components/SessionCard";
import type { Session } from "../types";

const fixture: Session = {
  session_id: "abc-123",
  cwd: "/tmp/x",
  project_slug: "codetalker",
  display_name: "Phase 22 work",
  last_modified: Date.now() / 1000 - 30,
  is_live: true,
  enabled: true,
  attached_profile: "alpha",
  has_persistent_settings: false,
};

describe("SessionCard", () => {
  it("renders project, profile, and display name with controls", () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/overlay")) {
        return Promise.resolve({ ok: true, json: async () => ({}) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ enabled: true, active_mode: "brief" }),
      });
    }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <SessionCard session={fixture} />
      </QueryClientProvider>
    );
    expect(screen.getByText("codetalker")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("Phase 22 work")).toBeInTheDocument();
  });
});
