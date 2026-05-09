import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PreferencesPanel } from "../components/PreferencesPanel";

describe("PreferencesPanel", () => {
  beforeEach(() => localStorage.clear());

  it("renders sound effects toggle off by default", () => {
    render(<PreferencesPanel />);
    const toggle = screen.getByLabelText(/sound effects/i) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
  });

  it("toggling sound effects persists", () => {
    render(<PreferencesPanel />);
    const toggle = screen.getByLabelText(/sound effects/i);
    fireEvent.click(toggle);
    expect(localStorage.getItem("cct.prefs")).toContain("\"soundEffects\":true");
  });

  it("density radio updates pref", () => {
    render(<PreferencesPanel />);
    fireEvent.click(screen.getByLabelText(/compact/i));
    expect(localStorage.getItem("cct.prefs")).toContain("\"density\":\"compact\"");
  });
});
