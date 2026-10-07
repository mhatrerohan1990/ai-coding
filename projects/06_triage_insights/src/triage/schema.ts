import { z } from 'zod';

export const CATEGORIES = ['bug', 'billing', 'access', 'how_to', 'other'] as const;

export const SEVERITIES = ['low', 'medium', 'high'] as const;

export const PLANS = ['free', 'pro', 'enterprise'] as const;

export const triageRequestSchema = z.object({
  id: z.string().trim().min(1).max(100),
  subject: z.string().trim().min(1).max(300),
  body: z.string().trim().min(1).max(10_000),
  customerPlan: z.enum(PLANS),
});

export const triageInsightSchema = z.object({
  category: z.enum(CATEGORIES),
  severity: z.enum(SEVERITIES),
  rationale: z.string(),
});

export type TriageRequest = z.infer<typeof triageRequestSchema>;
export type TriageInsight = z.infer<typeof triageInsightSchema>;
