import { describe, expect, it } from "vitest";
import { initialWizardState, wizardReducer } from "./wizardReducer";

describe("wizardReducer", () => {
  it("starts at step 1", () => {
    expect(initialWizardState.step).toBe(1);
  });

  it("advances to step 2 on IDENTITY_SUBMIT", () => {
    const next = wizardReducer(initialWizardState, {
      type: "IDENTITY_SUBMIT",
      identity: { id: "buddy", display_name: "Buddy", persona: "warm" },
    });
    expect(next.step).toBe(2);
    expect(next.identity.id).toBe("buddy");
  });

  it("rejects empty id", () => {
    const next = wizardReducer(initialWizardState, {
      type: "IDENTITY_SUBMIT",
      identity: { id: "", display_name: "X", persona: null },
    });
    expect(next.step).toBe(1);
    expect(next.error).toMatch(/id/i);
  });

  it("VOICE_SOURCE_SET advances to step 3", () => {
    const s2 = wizardReducer(initialWizardState, {
      type: "IDENTITY_SUBMIT",
      identity: { id: "x", display_name: "X", persona: null },
    });
    const next = wizardReducer(s2, {
      type: "VOICE_SOURCE_SET",
      source: { kind: "library", voiceId: "en_US-amy-medium" },
    });
    expect(next.step).toBe(3);
    expect(next.voiceSource?.kind).toBe("library");
  });

  it("CLONE_JOB_UPDATED transitions success to step 4", () => {
    const s = { ...initialWizardState, step: 3 as const };
    const next = wizardReducer(s, {
      type: "CLONE_JOB_UPDATED",
      job: { job_id: "j1", status: "succeeded", voice_ref: "char-buddy" },
    });
    expect(next.step).toBe(4);
  });

  it("CLONE_JOB_UPDATED failure stays on step 3 with error", () => {
    const s = { ...initialWizardState, step: 3 as const };
    const next = wizardReducer(s, {
      type: "CLONE_JOB_UPDATED",
      job: { job_id: "j1", status: "failed", error: "boom" },
    });
    expect(next.step).toBe(3);
    expect(next.error).toBe("boom");
  });

  it("BACK rewinds one step", () => {
    const s = { ...initialWizardState, step: 3 as const };
    expect(wizardReducer(s, { type: "BACK" }).step).toBe(2);
    expect(wizardReducer(initialWizardState, { type: "BACK" }).step).toBe(1);
  });
});
