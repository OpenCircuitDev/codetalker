// v0.1.0 unification — locks in the workspace-grouping label contract
// so the webui and Pro Android produce the SAME label for any given
// session. Source-of-truth heuristic lives in
// companion-android/.../ui/SessionListScreen.kt :humanizeProjectDir.
// If the Android side changes its rules, these tests drift first.
import { describe, expect, it } from "vitest";
import {
  groupLabelFor,
  groupSessions,
  humanizeProjectDir,
} from "../components/WorkspaceGroupSection";
import type { Session } from "../types";

function mkSession(overrides: Partial<Session>): Session {
  return {
    session_id: "sid",
    cwd: "",
    project_slug: "",
    display_name: "",
    last_modified: 0,
    is_live: true,
    enabled: true,
    attached_profile: null,
    has_persistent_settings: false,
    ...overrides,
  };
}

describe("humanizeProjectDir", () => {
  it("returns the last segment for a non-generic tail", () => {
    expect(
      humanizeProjectDir("C--Users-brand-Dropbox-OCR-Open-Circuit-codetalker")
    ).toBe("codetalker");
  });

  it("includes the prior segment when the last is a generic tail", () => {
    // "Workspace" is in GENERIC_TAILS — without context it would be
    // ambiguous across multiple BF/OCR projects.
    expect(
      humanizeProjectDir(
        "C--Users-brand-Dropbox-OCR-Open-Circuit-BF-Workspace"
      )
    ).toBe("BF / Workspace");
  });

  it("handles the BlueprintForge Workbench case (3 generics)", () => {
    expect(
      humanizeProjectDir(
        "C--Users-brand-Documents-Unreal-Projects-BlueprintForge-Workbench"
      )
    ).toBe("BlueprintForge / Workbench");
  });

  it("handles lowercase drive letter prefix", () => {
    expect(
      humanizeProjectDir(
        "c--Users-brand-Dropbox-OCR-Open-Circuit-Unreal-Games-OpenCircuitRacing"
      )
    ).toBe("OpenCircuitRacing");
  });

  it("falls back to the raw dir when nothing parses", () => {
    expect(humanizeProjectDir("")).toBe("");
    expect(humanizeProjectDir("C")).toBe("C");
  });

  it("treats `Web` and `Dev` as generic tails (need context)", () => {
    expect(humanizeProjectDir("a-b-c-OCR-Web")).toBe("OCR / Web");
    expect(humanizeProjectDir("a-b-c-OCR-Dev")).toBe("OCR / Dev");
  });
});

describe("groupLabelFor — priority order", () => {
  it("workspace_group wins over everything else", () => {
    const s = mkSession({
      workspace_group: "OCRacing",
      project_dir: "C--something",
      cwd: "/proj/something",
      project_slug: "slug",
    } as Partial<Session> & { project_slug?: string });
    expect(groupLabelFor(s)).toBe("OCRacing");
  });

  it("falls through workspace_group when blank", () => {
    const s = mkSession({
      workspace_group: "   ",
      project_dir: "C--Users-brand-Dropbox-OCR-Open-Circuit-codetalker",
    });
    expect(groupLabelFor(s)).toBe("codetalker");
  });

  it("uses project_dir when workspace_group is null", () => {
    const s = mkSession({
      project_dir: "C--Users-brand-Dropbox-OCR-Open-Circuit-BF-Workspace",
      cwd: "/some/path",
    });
    expect(groupLabelFor(s)).toBe("BF / Workspace");
  });

  it("falls through to cwd leaf when no project_dir", () => {
    const s = mkSession({
      cwd: "C:\\Users\\brand\\OCR\\codetalker",
    });
    expect(groupLabelFor(s)).toBe("codetalker");
  });

  it("handles forward-slash cwds", () => {
    const s = mkSession({ cwd: "/Users/x/Projects/MyApp" });
    expect(groupLabelFor(s)).toBe("MyApp");
  });

  it("uses project_slug as the next fallback", () => {
    const s = {
      ...mkSession({ cwd: "" }),
      project_slug: "my-project-slug",
    };
    expect(groupLabelFor(s)).toBe("my-project-slug");
  });

  it("returns Ungrouped when nothing identifies the session", () => {
    const s = mkSession({});
    expect(groupLabelFor(s)).toBe("Ungrouped");
  });
});

describe("pinned-first sort (within-group ordering)", () => {
  // Mirrors the SessionGrid sort in components/SessionGrid.tsx. Pinned
  // wins over is_live wins over last_modified desc. Group bucketing is
  // separate (groupSessions preserves source-array order), so a global
  // sort by these keys produces correct per-group ordering.
  function pinSort(sessions: Session[]): Session[] {
    return [...sessions].sort((a, b) => {
      const ap = !!a.pinned;
      const bp = !!b.pinned;
      if (ap !== bp) return ap ? -1 : 1;
      if (a.is_live !== b.is_live) return a.is_live ? -1 : 1;
      return b.last_modified - a.last_modified;
    });
  }

  it("places pinned ahead of unpinned within the same liveness", () => {
    const a = mkSession({ session_id: "a", pinned: false, last_modified: 100 });
    const b = mkSession({ session_id: "b", pinned: true, last_modified: 50 });
    const c = mkSession({ session_id: "c", pinned: false, last_modified: 90 });
    expect(pinSort([a, b, c]).map((s) => s.session_id)).toEqual(["b", "a", "c"]);
  });

  it("places live pinned ahead of dormant pinned", () => {
    const livePinned = mkSession({
      session_id: "lp",
      pinned: true,
      is_live: true,
      last_modified: 1,
    });
    const dormantPinned = mkSession({
      session_id: "dp",
      pinned: true,
      is_live: false,
      last_modified: 999,
    });
    expect(pinSort([dormantPinned, livePinned]).map((s) => s.session_id)).toEqual([
      "lp",
      "dp",
    ]);
  });

  it("places dormant-pinned ahead of live-unpinned (pin wins over live)", () => {
    const dormantPinned = mkSession({
      session_id: "dp",
      pinned: true,
      is_live: false,
      last_modified: 1,
    });
    const liveUnpinned = mkSession({
      session_id: "lu",
      pinned: false,
      is_live: true,
      last_modified: 999,
    });
    expect(pinSort([liveUnpinned, dormantPinned]).map((s) => s.session_id)).toEqual([
      "dp",
      "lu",
    ]);
  });

  it("falls back to last_modified desc when pin + liveness tie", () => {
    const older = mkSession({
      session_id: "o",
      pinned: true,
      last_modified: 100,
    });
    const newer = mkSession({
      session_id: "n",
      pinned: true,
      last_modified: 200,
    });
    expect(pinSort([older, newer]).map((s) => s.session_id)).toEqual(["n", "o"]);
  });
});

describe("groupSessions", () => {
  it("buckets sessions into groups by their resolved label", () => {
    const a = mkSession({ session_id: "a", workspace_group: "OCR" });
    const b = mkSession({ session_id: "b", workspace_group: "OCR" });
    const c = mkSession({ session_id: "c", workspace_group: "CodeTalker" });
    const groups = groupSessions([a, b, c]);
    expect([...groups.keys()]).toEqual(["OCR", "CodeTalker"]);
    expect(groups.get("OCR")?.length).toBe(2);
    expect(groups.get("CodeTalker")?.length).toBe(1);
  });

  it("preserves source-array ordering inside each group", () => {
    const a = mkSession({ session_id: "first", workspace_group: "X" });
    const b = mkSession({ session_id: "second", workspace_group: "X" });
    const groups = groupSessions([a, b]);
    expect(groups.get("X")?.map((s) => s.session_id)).toEqual([
      "first",
      "second",
    ]);
  });

  it("respects the priority order across mixed sessions", () => {
    // workspace_group set + project_dir set: workspace_group wins
    const labeled = mkSession({
      session_id: "a",
      workspace_group: "MyTeam",
      project_dir: "C--Users-foo-bar",
    });
    // workspace_group missing: project_dir wins
    const projectDir = mkSession({
      session_id: "b",
      project_dir: "C--Users-brand-Dropbox-OCR-Open-Circuit-codetalker",
    });
    // both missing: cwd leaf wins
    const cwdOnly = mkSession({
      session_id: "c",
      cwd: "/proj/leftovers",
    });
    const groups = groupSessions([labeled, projectDir, cwdOnly]);
    expect([...groups.keys()].sort()).toEqual(
      ["MyTeam", "codetalker", "leftovers"].sort()
    );
  });
});
