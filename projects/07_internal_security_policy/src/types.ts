export interface Excerpt {
  id: string;
  text: string;
}

export interface AskInput {
  question: string;
  excerpts: Excerpt[]; // at most 5
}

export interface AskResult {
  answer: string;
  citations: string[]; // excerpt ids
  refused: boolean;
}
