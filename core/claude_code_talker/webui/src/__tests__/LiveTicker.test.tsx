import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LiveTicker } from "../components/LiveTicker";

const events = [
  { id: "1", kind: "speak", text: "Hello there", ts: 1234 },
  { id: "2", kind: "tool", text: "Bash succeeded", ts: 1235 },
  { id: "3", kind: "speak", text: "Phase complete", ts: 1236 },
];

describe("LiveTicker", () => {
  it("renders all events when no filter", () => {
    render(<LiveTicker events={events} />);
    expect(screen.getByText(/hello there/i)).toBeInTheDocument();
    expect(screen.getByText(/bash succeeded/i)).toBeInTheDocument();
  });

  it("filters to only speak events", () => {
    render(<LiveTicker events={events} />);
    fireEvent.click(screen.getByRole("button", { name: /^speak$/i }));
    expect(screen.queryByText(/bash succeeded/i)).not.toBeInTheDocument();
    expect(screen.getByText(/hello there/i)).toBeInTheDocument();
  });

  it("shows empty state when no events", () => {
    render(<LiveTicker events={[]} />);
    expect(screen.getByText(/quiet/i)).toBeInTheDocument();
  });

  it("scrolls to most recent on update", () => {
    const { rerender } = render(<LiveTicker events={events} />);
    rerender(
      <LiveTicker
        events={[...events, { id: "4", kind: "speak", text: "Latest", ts: 1237 }]}
      />
    );
    expect(screen.getByText("Latest")).toBeInTheDocument();
  });
});
