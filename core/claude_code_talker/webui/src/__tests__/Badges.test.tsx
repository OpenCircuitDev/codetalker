import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProjectBadge } from "../components/ProjectBadge";
import { ProfileBadge } from "../components/ProfileBadge";

describe("ProjectBadge", () => {
  it("shows project slug and relative time", () => {
    const tenSecAgo = Date.now() / 1000 - 10;
    render(<ProjectBadge slug="codetalker" lastModified={tenSecAgo} />);
    expect(screen.getByText("codetalker")).toBeInTheDocument();
    expect(screen.getByText(/seconds? ago/)).toBeInTheDocument();
  });
});

describe("ProfileBadge", () => {
  it("shows profile name when attached", () => {
    render(<ProfileBadge profile="alpha" />);
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });
  it("shows 'no profile' when null", () => {
    render(<ProfileBadge profile={null} />);
    expect(screen.getByText(/no profile/i)).toBeInTheDocument();
  });
});
