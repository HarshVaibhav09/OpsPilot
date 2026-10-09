# OpsPilot Generation Evaluation (RAGAS)

Scored 5 of 50 gold-set queries. Retrieval mode: hybrid. Judge: `openai/gpt-oss-120b`.

Answers were generated through the live chat pipeline, and the contexts scored here are the exact chunks that produced each answer, not a separate retrieval pass.

## Overall

| Metric | Score | Scored | What it measures |
|---|---|---|---|
| Faithfulness | 0.875 | 4/5 | Every claim in the answer is supported by the retrieved context. The direct hallucination measure. |
| Answer relevancy | n/a | 0/5 | The answer addresses the question asked, rather than being true but beside the point. |
| Context precision | 0.711 | 5/5 | Retrieved chunks are relevant, rather than padding context with noise. |
| Context recall | 1.0 | 3/5 | Retrieval surfaced everything the ground-truth answer needed. |

Faithfulness and answer relevancy are generation-side; context precision and recall are retrieval-side. Keeping both in view separates a hallucinating generator from one that was handed the wrong context.

## By query style

| Query style | n | Faithfulness | Answer relevancy | Context precision | Context recall |
|---|---|---|---|---|---|
| identifier | 2 | 0.5 | n/a | 0.486 | 1.0 |
| paraphrase | 2 | 1.0 | n/a | 1.0 | n/a |
| table_lookup | 1 | 1.0 | n/a | 0.583 | 1.0 |

## By document type

| Document type | n | Faithfulness | Answer relevancy | Context precision | Context recall |
|---|---|---|---|---|---|
| sop | 5 | 0.875 | n/a | 0.711 | 1.0 |

## Lowest faithfulness scores

Worth reading by hand: these are where the generator drifted furthest from its context.

| Query | Faithfulness | Answer relevancy |
|---|---|---|
| Q02: what is form VFL-LC-02 used for | 0.5 | n/a |
| Q01: how much weight can we put on a truck before it coun | 1.0 | n/a |
| Q03: how far can the temperature drift before someone has | 1.0 | n/a |
| Q05: how long do we have to keep cold chain temperature l | 1.0 | n/a |

## Known limitations

- The judge is `openai/gpt-oss-120b`, a mid-size open model rather than a frontier one. RAGAS scores are judge-dependent, so these are not directly comparable to published benchmarks run with GPT-4-class judges. They are internally consistent, which is what makes them useful for tracking change over time.
- Faithfulness measures grounding in the retrieved context, not truth. An answer faithfully derived from a wrong chunk still scores well. Retrieval quality is measured separately in RESULTS.md.
- Ground truths are short factual statements written by hand from the source documents. Context recall is therefore stricter on multi-part answers, where one missing detail lowers the score.
- The scorer runs in a separate virtual environment (.venv-eval) because ragas pins an older LangChain than the application. See eval/requirements-eval.txt for the exact set.
