// CCT-28 cat 4: CadencePicker render + change-PUT-overlay coverage.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CadencePicker } from "../components/CadencePicker";
import { SessionControls } from "../components/SessionControls";
import type { SessionConfig } from "../types";

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe("CadencePicker", () => {
  it("renders all five canonical cadence options", () => {
    render(<CadencePicker value="periodic" onChange={() => {}} />);
    const select = screen.getByLabelText(/cadence/i) as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toEqual([
      "periodic",
      "per_tool_call",
      "per_cluster",
      "significant_only",
      "hybrid",
    ]);
  });

  it("shows an (unknown) option when value is not in the canonical list", () => {
    render(<CadencePicker value="weird-value" onChange={() => {}} />);
    const select = screen.getByLabelText(/cadence/i) as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(screen.getByText("(unknown)")).toBeInTheDocument();
  });

  it("calls onChange with the new cadence when user selects", () => {
    const onChange = vi.fn();
    render(<CadencePicker value="periodic" onChange={onChange} />);
    const select = screen.getByLabelText(/cadence/i) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "hybrid" } });
    expect(onChange).toHaveBeenCalledWith("hybrid");
  });
});

describe("SessionControls cadence wiring", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (typeof url === "string" && url.endsWith("/api/voices")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (typeof url === "string" && url.includes("/overlay") && init?.method === "PUT") {
        return Promise.resolve({ ok: true, json: async () => ({ resolved_cfg: {} }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("changing cadence PUTs { live: { cadence } } to the overlay endpoint", async () => {
    const cfg: SessionConfig = {
      enabled: true,
      active_mode: "live",
      live: { cadence: "periodic" },
    };
    render(withClient(<SessionControls sessionId="sid-99" config={cfg} />));
    const select = screen.getByLabelText(/cadence/i) as HTMLSelectElement;
    expect(select.value).toBe("periodic");
    fireEvent.change(select, { target: { value: "hybrid" } });
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        (c) =>
          typeof c[0] === "string" &&
          c[0].includes("/api/sessions/sid-99/overlay") &&
          c[1]?.method === "PUT",
      );
      expect(call).toBeTruthy();
      const body = JSON.parse(call![1].body as string);
      expect(body.live.cadence).toBe("hybrid");
    });
  });
});
