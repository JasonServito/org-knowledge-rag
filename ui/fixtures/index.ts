// The saved answers and stored chains (S17-R1 c14; README.md records how they were copied),
// typed with the API's types so `tsc` checks them: a field the types name that the data lacks,
// or holds with another type, fails the typecheck.

import type { Answer, Chain, DecisionSummary } from "../lib/types";
import answersJson from "./answers.json";
import kep2572Json from "./chains/kep-2572.json";
import kep3015Json from "./chains/kep-3015.json";

// TypeScript types a JSON file loosely: "answered" as any string, ["1.24", null] as an array of
// any length. So the files are checked against Json<T>: T's fields, nesting and nulls, with its
// string literals and tuples loosened the same way. The casts below then restore T, which
// TypeScript allows because every T fits its Json<T>.
type Json<T> = T extends string
  ? string
  : T extends readonly (infer Item)[]
    ? Json<Item>[]
    : T extends object
      ? { [Key in keyof T]: Json<T[Key]> }
      : T;

const checkedAnswers: Record<string, Json<Answer>> = answersJson;
const checkedChains: Record<string, Json<Chain>> = {
  "kep:2572": kep2572Json,
  "kep:3015": kep3015Json,
};

// The 43 saved answers, keyed by question id (q01 ... q48).
export const answers = checkedAnswers as Record<string, Answer>;
// The 2 stored chains, keyed by seed.
export const chains = checkedChains as Record<string, Chain>;
// `GET /decisions`' 200 for the 2 stored chains, by seed: each chain's seed, title and built_at.
export const decisions: DecisionSummary[] = Object.values(chains).map(
  ({ seed, title, built_at }) => ({ seed, title, built_at }),
);
