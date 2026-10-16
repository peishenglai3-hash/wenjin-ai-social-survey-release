import type { Hint } from "../types/hints";

export function parseHints(raw: string[], category?: string): Hint[] {
  return raw.map((text, index) => ({
    id: `hint_${Date.now()}_${index}`,
    text,
    category: (category || "general") as Hint["category"],
    urgency: "medium",
    timestamp: Date.now(),
  }));
}
