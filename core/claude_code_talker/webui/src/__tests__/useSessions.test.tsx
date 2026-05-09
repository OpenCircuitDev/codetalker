import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSessions } from "../hooks/useSessions";

const fixture = [
  {
    session_id: "abc",
    cwd: "/tmp/x",
    project_slug: "x",
    display_name: "X",
    last_modified: 0,
    is_live: true,
    enabled: true,
    attached_profile: null,
    has_persistent_settings: false,
  },
];

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => fixture,
  }));
});

describe("useSessions", () => {
  it("returns the live session list", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: any) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useSessions(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(fixture));
  });
});
