export interface Segment {
  start: number;
  end: number;
  text: string;
  speaker: string;
}

export interface Meeting {
  id: string;
  filename: string;
  agenda: string;
  status: string;
  created_at: string;
  updated_at: string;
  error: string | null;
  duration: number | null;
  segments: Segment[];
  analysis: {
    summary: string;
    minutes: string;
    decisions: string[];
    actions: { task: string; owner: string | null; deadline: string | null }[];
    effectiveness_score: number;
    explanation: string;
    percent: Record<string, number>;
    agenda_provided: boolean;
    topics: {
      title: string;
      category: string;
      explanation: string;
      ranges: { start: number; end: number }[];
    }[];
  } | null;
}
