import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ModeIndicator } from "../components/ModeIndicator";
import { MuteIndicator } from "../components/MuteIndicator";

describe("ModeIndicator", () => {
  it("renders the mode name", () => {
    render(<ModeIndicator mode="brief" />);
    expect(screen.getByText("brief")).toBeInTheDocument();
  });
  it("renders 'unknown' when mode is undefined", () => {
    render(<ModeIndicator mode={undefined} />);
    expect(screen.getByText(/unknown/i)).toBeInTheDocument();
  });
});

describe("MuteIndicator", () => {
  it("shows muted state", () => {
    render(<MuteIndicator muted={true} />);
    expect(screen.getByText(/muted/i)).toBeInTheDocument();
  });
  it("shows audible state", () => {
    render(<MuteIndicator muted={false} />);
    expect(screen.getByText(/audible/i)).toBeInTheDocument();
  });
});
