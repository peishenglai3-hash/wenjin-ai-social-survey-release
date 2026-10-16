export interface Hint {
  id: string;
  text: string;
  category?: "follow_up" | "rapport" | "redirect" | "probe" | "wrap_up" | "general";
  urgency?: "low" | "medium" | "high";
  timestamp: number;
}
