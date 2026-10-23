export const STEPS = ["Upload", "Scanning", "Reading", "Analysis", "Validation", "Outcome"] as const;

const BY_CODE: Record<string, number> = {
  QUEUED: 0,
  READING: 0,
  EXTRACTING_TEXT: 1,
  FINGERPRINTING: 1,
  EXTRACTING_FIELDS: 2,
  AI_EXTRACTION: 3,
  INTEGRITY: 3,
  VERIFYING: 4,
  RULES: 4,
  ROUTING: 5,
  DONE: 5,
};

const BY_TEXT: [RegExp, number][] = [
  [/reading file|queued/i, 0],
  [/extracting text|fingerprint/i, 1],
  [/extracting fields/i, 2],
  [/ai-assisted|integrity/i, 3],
  [/verifying|rule pack|re-validating/i, 4],
  [/recommending|done/i, 5],
];

export function stepOf(job: { stage_code?: string | null; stage: string; state?: string }): number {
  if (job.state === "DONE") return 5;
  if (job.stage_code && job.stage_code in BY_CODE) return BY_CODE[job.stage_code];
  return BY_TEXT.find(([re]) => re.test(job.stage))?.[1] ?? 0;
}

export function isAiStage(job: { stage_code?: string | null; stage: string }): boolean {
  return job.stage_code === "AI_EXTRACTION" || /ai-assisted/i.test(job.stage);
}
