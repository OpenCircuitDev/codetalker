import { describe, expect, it, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { usePreferences } from "../hooks/usePreferences";

describe("usePreferences", () => {
  beforeEach(() => localStorage.clear());

  it("defaults sound effects off", () => {
    const { result } = renderHook(() => usePreferences());
    expect(result.current.prefs.soundEffects).toBe(false);
  });

  it("persists changes to localStorage", () => {
    const { result } = renderHook(() => usePreferences());
    act(() => result.current.setPref("soundEffects", true));
    const raw = localStorage.getItem("cct.prefs");
    expect(raw).toContain("\"soundEffects\":true");
  });

  it("loads persisted prefs on mount", () => {
    localStorage.setItem(
      "cct.prefs",
      JSON.stringify({ soundEffects: true, density: "compact" })
    );
    const { result } = renderHook(() => usePreferences());
    expect(result.current.prefs.soundEffects).toBe(true);
    expect(result.current.prefs.density).toBe("compact");
  });
});
