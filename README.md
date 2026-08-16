# OpsPilot

A document intelligence assistant for logistics ops teams. Upload your rate cards, SOPs, vendor contracts, compliance circulars, incident logs, or fleet reports, and just ask questions instead of digging through PDFs by hand — by typing, or by talking.

- **Live app:** https://ops-pilot-phi.vercel.app
- **Backend API:** https://opspilot-production-427d.up.railway.app
- **Repo:** https://github.com/HarshVaibhav09/OpsPilot

Built by Harsh Vaibhav.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Architecture](#architecture)
3. [Setup](#setup)
4. [Chunking and Retrieval — What I Did and Why](#chunking-and-retrieval--what-i-did-and-why)
5. [Voice Mode — What I Did and Why](#voice-mode--what-i-did-and-why)
6. [Known Limitations](#known-limitations-honestly)
7. [What I'd Build Next With One More Week](#what-id-build-next-with-one-more-week)
8. [Tech Stack](#tech-stack)

---

## What It Does

- Upload 2-3+ PDFs. Each one gets classified by type, then chunked using a strategy that actually fits that type, embedded, and stored for retrieval.
- Ask questions in a chat interface, grounded strictly in the uploaded documents.
- **Ask by voice.** Hit the mic, speak your question, and stop talking — it detects the pause, sends the query, and speaks the answer back while the full written answer with citations appears on screen. Typing still works exactly as before; voice is an input mode, not a separate app.
- Follow-up questions work. Ask "what's the vehicle damage cost of incident INC00000015" then "what's the incident type for that one" and it resolves correctly. This works across channels too — ask by voice, follow up by typing, then follow up again by voice, all in the same session.
- Every answer comes with citations back to the source file, page, and section.
- Uploads run in the background. You get a job ID immediately and see live per-file progress, instead of the page freezing while a big PDF gets processed.
- Each document gets an automatic contradiction check — if two sections of the same doc disagree on a date, amount, or name, it gets flagged. This runs after the document is already usable, not before.
- A developer mode toggle shows what actually got retrieved: similarity scores, the rewritten query, and chunk-level detail (section, content type, snippet). Built this mostly to debug my own retrieval quality, kept it because it's genuinely useful.
- The retrieval API can filter by document type (rate card, contract, SOP, and so on) if you're calling it directly. It's not wired into the chat UI yet — the "Known Limitations" section explains why that's a deliberate choice, not an oversight.

---

## Architecture

Diagram attached below (hand-drawn — I worked from the SVG version in the repo if it's hard to read).

Frontend (React, Vercel) talks to a FastAPI backend (Railway). The backend splits into two pipelines:

**Ingestion pipeline** — a PDF comes in, gets validated against a page limit up front (fails fast instead of grinding for minutes on something too big), then the whole thing runs as a background job so the upload request returns instantly with a job ID. In the background: PyMuPDF pulls text and tables per page. The first handful of pages get buffered just long enough to classify the document (rate card, contract, SOP, invoice, or a data log like an incident register), and from there the matching chunking strategy streams through the rest of the file one page at a time — so an 80-page file doesn't cost meaningfully more memory to process than an 8-page one. Tables are pulled out as their own chunks on every page regardless of the document's overall type, with the header row repeated on any table too big to fit in one chunk. Everything gets embedded with fastembed and lands in Chroma, with a BM25 index sitting alongside it for keyword search. Once the document is marked ready, contradiction analysis kicks off separately in the background — it doesn't block the document from being usable.

**Chat pipeline** — a message comes in, gets rewritten into a standalone query if there's prior history, hits hybrid retrieval (dense + BM25, fused), the top chunks get formatted into context, and Groq generates the answer. Retrieval can be scoped to a single uploaded document, or, via the API, to a document type. The turn gets saved to SQLite so the next follow-up has something to work with.

**Voice sits on top of the chat pipeline rather than beside it.** Speech-to-text happens in the browser and produces a plain string; by the time it reaches the backend it's indistinguishable from something typed, so it hits the exact same rewrite → retrieve → generate path. The only backend addition is a separate `/voice/speak` endpoint that turns a finished answer into audio. Text and voice share one brain and one session; they differ only at the edges.

**Diagram:**

<img width="2417" height="3004" alt="OpsPilot" src="https://github.com/user-attachments/assets/074624fe-8a96-487a-a0a8-ad1f5ff74340" />

---

## Setup

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file:

```env
LLM_PROVIDER=groq
LLM_API_KEY=your_groq_api_key
LLM_MODEL=openai/gpt-oss-120b

EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

CHUNK_SIZE=700
CHUNK_OVERLAP=120

TOP_K_RETRIEVAL=8
TOP_K_FINAL=5

MAX_PAGES=50

CHROMA_PERSIST_DIR=./data/chroma
SESSION_DB_PATH=./data/sessions.db

CORS_ORIGINS=https://your-frontend-url.vercel.app

# Voice
TTS_PROVIDER=edge
TTS_SUMMARY_MODEL=openai/gpt-oss-20b
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=your_voice_id
```

`LLM_MODEL` has no default and is required — a missing value fails at startup rather than falling back silently.

`TTS_PROVIDER` accepts `edge` or `elevenlabs`. Use `edge` locally (free, unlimited, no key needed) and `elevenlabs` in deployment — see the Voice Mode section for why they differ.

Run it:

```bash
uvicorn app.main:app --reload
```

Note that `--reload` watches `.py` files but not `.env` — restart the process fully after changing environment variables.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Point it at your backend:

```env
VITE_API_URL=http://localhost:8080
```

Voice input needs Chrome or Edge, and it needs HTTPS in production — microphone access is blocked on plain HTTP. The app feature-detects and shows a notice rather than failing silently on unsupported browsers, and text chat works everywhere regardless.

### 3. Docker (optional)

There's a `Dockerfile` for both frontend and backend if you'd rather not set up the environment locally.

---

## Chunking and Retrieval — What I Did and Why

### The problem I actually hit

My first version of this used one chunking strategy for everything — detect headings, split under them, done. It worked fine on well-structured SOPs and contracts. It fell apart on a real logistics document: an 85-page truck utilization report that's basically a giant table with almost no prose headings. Most of it collapsed into one generic "General" bucket, and retrieval got noticeably worse on exactly that document. Given the whole point of this tool is handling messy real-world logistics paperwork, that felt like the wrong thing to leave unfixed.

### What I do now: classify first, then stream through a matching chunker

Before chunking, each document gets classified into one of five types: **rate card**, **contract**, **SOP**, **invoice**, or **data log** (registers like incident logs or fleet reports — very common in logistics but not something the original brief called out explicitly). Classification is mostly heuristic — keyword scoring plus table density, with a structural check for record-ID patterns (things like `TRK00001` or `INC00000015`) that catches data logs even when they have zero descriptive keywords. If nothing scores confidently, it falls back to one LLM call to classify. I did it this way instead of always calling an LLM to classify, because that's one more Groq call per upload for something a handful of regex checks usually nails for free.

Classification itself only looks at the first few pages — enough signal without holding the whole document in memory. Once a type is picked, the matching chunker takes over and streams through every page of the file one at a time, carrying just a small amount of state between pages (the current heading or clause label, a running chunk counter). That's what keeps memory flat regardless of document size, whether it's 5 pages or 80.

Each type gets its own chunking approach:
- **SOPs/contracts** — heading or clause-pattern based, keeping sections whole where possible. Contract clause detection also treats things like `ANNEXURE A`, `SCHEDULE B`, or `EXHIBIT C` as section boundaries — real vendor contracts very often embed a rate schedule as an annexure rather than shipping it as a separate document, and without this the pricing table would just dissolve into unlabeled legal prose.
- **Rate cards** — skip heading detection entirely, since it just produces false splits on numbers-heavy pages. Tables get pulled out as their own chunks, page context stays separate.
- **Invoices** — pull out `Key: Value` style fields as one chunk, everything else as a second.
- **Data logs** — this is the one I'm most proud of getting right. Instead of splitting on newlines, it splits on the record-ID pattern itself, directly in the raw character stream. That matters because PyMuPDF sometimes extracts dense tabular PDFs with rows fused together, no space or line break between them at all. Splitting on newlines would silently cut through the middle of a record. Splitting on the ID pattern survives that. Every resulting chunk also gets the column header line prepended to it, not just the first chunk, so a chunk retrieved from page 40 still tells the model what each number actually means.

Tables get pulled out identically regardless of document type — a table is a table, and splitting one mid-row destroys it for retrieval no matter what kind of document it's in. If a single table is too big for one chunk, the header row gets repeated on every split piece, so a fragment landing deep in a big table still carries its column names instead of turning into an unlabeled pile of numbers.

### Where this still breaks: whole-document classification on mixed content

Classification produces exactly one label for the entire file, based on a sample from the first few pages. That's fine for a document that actually is one thing end to end. It's not fine for a document that isn't. I tested this against a real 41-page "annual operations package" — one PDF stacking an SOP page, a rate card, a 300-row incident log, a vendor directory, an invoice summary, a shipment tracking log, a driver roster, and a compliance audit all into a single file. The classifier — reasonably, based on what it could actually see in the first five pages — tagged the entire document `rate_card`. Every chunk downstream, including all 309 incident records, inherited that label.

The good news: the mislabeling didn't hurt the chunks themselves. Table extraction runs independently per page regardless of the document's overall type, so the incident log still came through with every record intact, correctly bounded, nothing bisected — I checked this row by row. The label is wrong; the content and its boundaries are right. But it means a `document_type` filter on this file would be actively misleading, which is exactly why that filter doesn't show up anywhere in the UI. Showing a label I can't stand behind felt worse than not showing one.

### Retrieval

Hybrid: dense vector search (Chroma, cosine similarity) fused with BM25 keyword search, combined with reciprocal rank fusion. Went hybrid because logistics documents are full of exact identifiers — truck IDs, incident IDs, clause numbers — where dense retrieval alone sometimes misses an exact match that BM25 catches instantly, and vice versa for more paraphrased questions.

Retrieval also supports an optional `document_type` filter alongside the existing single-document filter, at the API level. Given the mislabeling risk above, I've deliberately kept it out of the frontend for now — it's there for direct API use and as groundwork for a smarter, section-aware version of classification later, not for a user to filter on today.

I originally had a cross-encoder reranker planned between retrieval and generation, with scores meant to show up in developer mode. I pulled it — more on why below.

### Query rewriting for follow-ups

Before retrieval, if there's conversation history, the question gets rewritten into a standalone query by the LLM. I hit a real bug here during testing: the rewrite prompt didn't explicitly protect exact identifiers, so a follow-up like "what's the incident type for that one" sometimes got rewritten without carrying the actual incident ID forward, and retrieval landed on the wrong chunks. Fixed by being explicit in the rewrite instruction that identifiers, codes, and numbers must be preserved exactly, never paraphrased.

### Embeddings

Switched from sentence-transformers/torch to fastembed partway through. Two reasons: it's noticeably faster on CPU since it runs on ONNX Runtime instead of a full training framework doing inference as an afterthought, and it drops the torch dependency entirely, which was the direct cause of a RAM-related crash on Render's free tier. Also fixed a real correctness bug in the process — fastembed exposes separate methods for embedding documents versus queries, which properly handles the fact that BGE models are trained asymmetrically. My first pass at this used the same method for both and technically worked, just less accurately.

---

## Voice Mode — What I Did and Why

### The design decision: side by side, not voice-only

The obvious way to build this is to make voice its own mode — you talk, it talks back, done. I deliberately didn't. A voice turn renders as a normal message in the same chat, tagged as spoken, and the assistant's answer appears in full on screen with citations and confidence score intact while a shorter version is read aloud.

Two reasons. First, citations are the most defensible thing this app does, and "trust me, I said it out loud" is not an acceptable substitute for showing which page a number came from. Second, it keeps one session and one history — you can ask by voice, follow up by typing, then follow up again by voice, and query rewriting resolves references across all of it, because by the time a transcript reaches the backend it's just a string.

### Speech-to-text runs in the browser, not on the server

I used the browser's built-in `SpeechRecognition` API rather than a server-side model like Whisper. Three reasons: it's free with no quota, it adds zero load to a free-tier backend, and — the deciding one — I'd already had to drop torch once for a RAM crash on Render. Adding a self-hosted speech model would have walked straight back into the same wall.

The tradeoff is real and I'd change it in production: browser STT is Chrome/Edge only, behaves inconsistently in Safari, and doesn't exist at all for a phone call. Anything telephony-shaped needs server-side STT.

### Endpointing: I wrote my own instead of using the browser's

The browser's own end-of-speech detection fires unpredictably — sometimes cutting you off mid-thought, sometimes hanging for seconds. So recognition runs with `continuous: true` and I time the gap since the last result myself, firing the query after 1.5 seconds of silence.

That number is a product decision, not a constant. Too short and it cuts off anyone who pauses to think; too long and every turn feels dead. 1.5s is tuned for how I speak. For a real deployment — especially anything serving people who are elderly, unwell, or speaking a second language — I'd want it configurable and tuned against actual usage data rather than hardcoded.

Two guards came out of testing. An empty transcript closes the mic silently instead of sending a blank query. And a manual stop mid-sentence merges the *interim* transcript into what gets sent — without that, everything said since the last finalised result was being silently dropped, which was a real bug I hit and fixed. Losing a user's most recent words is worse than sending slightly less-refined text.

### The spoken answer is not the written answer

A RAG answer full of markdown bullets, bold labels, and `(Source: filename, page 12)` citations sounds terrible read aloud. So the written answer gets rewritten into two or three spoken sentences by a second, smaller LLM call before synthesis, with a strict instruction to preserve every number, name and date exactly.

That introduces a new hallucination surface — the spoken version could drift from the cited written one — so the written answer stays the source of truth and anything spoken is always verifiable against what's on screen. If I were shipping this for real I'd add an automated check that numbers and named entities in the spoken text also appear in the written text.

Short answers skip the summarizing call entirely, since paying a full round-trip to shorten something already short is the wrong trade. There's also a regex-based cleaner (strips citations, markdown, filenames, normalizes symbols) that acts as the fallback whenever the summarizing call fails — voice degrades, it doesn't break.

### Model selection, and a forced migration

I use a larger model (`gpt-oss-120b`) for answer generation where reasoning quality matters, and a smaller, faster one (`gpt-oss-20b`) for the spoken-summary step, which is compression rather than reasoning. Different latency-vs-capability tradeoffs at different points in the same pipeline.

Both are recent. Groq decommissioned the Llama models this was originally built on mid-development. Because model names were always config values rather than hardcoded strings, that migration was a two-line environment change rather than a code edit.

### TTS: three providers, because the first two both failed in different ways

This took the longest and taught me the most.

I started with `edge-tts` — free, unlimited, no API key, and genuinely good neural voices. It works perfectly on localhost. On Railway it returns `403` on the WebSocket handshake, because it uses an unofficial endpoint intended for the Edge browser's read-aloud feature and Microsoft blocks datacenter IP ranges. Correct code, wrong environment.

So I moved to ElevenLabs for production. That surfaced a second constraint: on the free tier, community Voice Library voices are blocked via the API entirely (`402 paid_plan_required`), and the default voices that *are* accessible are scheduled for deprecation. Free tier is also 10,000 characters a month — roughly 28 answers — and non-commercial only.

What shipped: provider is an environment variable. `edge` locally so development costs nothing, `elevenlabs` in production. If the provider fails for any reason, the endpoint hands the cleaned spoken text back to the browser, which reads it with `SpeechSynthesis` — worse voice, but the turn still completes. Synthesized audio is cached keyed on provider plus answer text, so a repeated question costs nothing.

The honest production answer is Azure Speech: 500k free characters a month, an official SLA, and `en-GB-SoniaNeural` is an Azure voice, so the local and production voices would finally match. I'd move to it for anything beyond a short-lived demo.

### Measured latency

Per stage, on my machine:

| Stage | Time |
|---|---|
| Silence threshold before send | 1.5s (fixed) |
| Retrieval + answer generation | ~1.3s |
| Spoken summary (long answers only) | ~0.7s |
| Speech synthesis | ~1.0s warm, ~3.0s cold |

Roughly 3.5–4.5s from finishing speaking to hearing a reply. The two biggest levers I haven't pulled: the summary and synthesis calls are sequential round-trips, and synthesis waits for the complete audio file before playback starts.

The first TTS call after an idle period was consistently about three times slower than subsequent ones — connection setup, not generation. In production you'd keep a warm connection or pre-warm on session start.

---

## Known Limitations (Honestly)

1. **Document classification is one label for the whole file, and it can be confidently wrong on mixed content.** It's right most of the time on a document that clearly belongs to one of the five types. It's not designed for a single PDF that shifts between several types across its length — the 41-page test case above is a real example, not a hypothetical. Chunking quality inside the document holds up regardless, since table extraction runs page by page and doesn't depend on the top-level label. The label itself can still be wrong for large parts of the file. This is exactly why `document_type` isn't shown anywhere in the UI right now.

2. **Classification's LLM fallback isn't latency-bounded yet.** When the keyword and structural heuristics can't confidently place a document — a compliance circular with no strong keyword bucket, for instance — classification falls back to one Groq call before chunking even starts, on the same client-wide 30-second timeout as everything else. On a slow response, that one call can noticeably stall the upload of an otherwise unremarkable document. I know the fix (a shorter, dedicated timeout just for this call); it just hasn't shipped yet.

3. **Contradiction analysis doesn't make sense yet for data logs.** Running the current contradiction-detection prompt against a 300-row incident log isn't really testing for the same kind of inconsistency it was designed for. Right now it still runs against every document type the same way — this is a real gap I haven't closed yet, not an oversight I'm unaware of.

4. **Reranker got cut for memory, not because it didn't help.** I had a cross-encoder reranker planned, with scores meant to show up in developer mode, and I even had the frontend field wired up for it. Deployment on Render kept OOM-crashing once I added it. I pulled it to ship something that actually works instead of something that looks better on paper but crashes. Retrieval still retrieves 8 candidates and returns 5, but that final trim is a plain truncation right now, not a reranked one.

5. **Large PDFs still take real time to process**, even with async, page-streamed ingestion. The upload no longer blocks the UI, and memory stays flat regardless of file size, but classification, chunking, and embedding for an 80-page document still takes a while in absolute terms. There's a per-file timeout (180 seconds) so one bad file can't hang the whole batch, but there's no progress indicator inside a single file's processing — just queued/processing/done at the file level.

6. **Error handling on the chat side is thinner than the upload side.** Upload failures are handled gracefully with clear messages. If Groq rate-limits or times out mid-chat-request, that can still surface as a raw error rather than a calm fallback message. I fixed this pattern for ingestion but haven't gotten to it for chat yet.

7. **Filtering is coarser than it should be.** `doc_id` scoping is all-or-one — a single uploaded document or the whole corpus, no way to pick a subset of 2 out of 5. There's also a `document_type` filter at the API level now, but given point 1 above, I haven't exposed it in the UI — it's not trustworthy enough yet to hand to a user as a filter control.

8. **Vector store and session data live on local disk inside the container.** On a free-tier host without an attached persistent volume, a redeploy can wipe them. Worth knowing before assuming uploaded documents survive indefinitely.

9. **Voice input is Chrome/Edge only, and browser-dependent by design.** Browser-native speech recognition was the right call for a free web demo — no backend load, no quota, no extra memory — but it behaves inconsistently in Safari and doesn't exist for a phone call. Text chat works everywhere; voice degrades to a notice.

10. **There's no real barge-in.** You can interrupt a spoken answer with a stop button, and the mic is disabled while audio plays so the app can't transcribe its own voice. Proper acoustic barge-in — listening while speaking, using echo cancellation to separate the user's voice from the assistant's — is a genuinely harder problem I scoped out rather than half-solved.

11. **Speech recognition mangles alphanumeric identifiers.** Reading `INC00000015` aloud is exactly the case ASR handles worst, and this corpus is full of them. Query rewriting already protects identifiers once they're in text, but it can't recover one that was transcribed wrong in the first place. A production system would need phonetic normalization or a confirmation prompt.

12. **The spoken/typed distinction isn't persisted.** The "Spoken" tag is session-only — reload the page and history loads without it. For an audit trail you'd genuinely want to know whether a user typed or said something, since transcription introduces an error source typing doesn't. That's a schema change I haven't made.

13. **ElevenLabs' free tier is ~28 answers a month.** The cache and the browser fallback mean running dry degrades rather than breaks, but this is a demo-scale constraint, not a production one.

---

## What I'd Build Next With One More Week

1. **Move classification from whole-document to section-aware.** The real fix for the mixed-document problem isn't a better whole-document classifier — it's detecting when the document changes type partway through (an annexure boundary, a new report heading) and switching chunking strategy at that point, the same way page-level table extraction already works today regardless of the document's overall label.

2. **Bound the classification LLM fallback's timeout separately** from the rest of the LLM client, so one ambiguous document can't stall its own upload waiting on a slow response.

3. **Bring the reranker back on infrastructure that can hold it**, and finish wiring up the rerank scores in developer mode. Now that fastembed freed up real memory headroom by dropping torch, this is genuinely closer to feasible than it was — I'd want to actually test it properly rather than guess.

4. **Make contradiction analysis type-aware.** Skip it entirely for data logs, or reframe what it's checking for on that document type — something like flagging a row where the numbers don't add up internally (e.g. a utilization rate that doesn't match trips and miles) instead of comparing prose sections against each other.

5. **Harden error handling around the chat LLM calls**, the same way I already did for ingestion. A rate-limited request should degrade to a calm "having trouble right now" message instead of a raw 500, especially given the walkthrough call means someone will actually be live-testing this.

6. **Let users scope a question to a subset of documents**, not just one or all — and once classification is trustworthy at a finer grain, surface the type filter in the UI too.

7. **Move Chroma and the session DB to real persistent storage** so a redeploy doesn't risk wiping uploaded documents on a free-tier host.

8. **Stream the voice pipeline end to end.** Token-stream the answer from Groq into sentence-chunked TTS so audio starts before generation finishes, and stream the synthesized audio to the browser instead of waiting for the complete file. This is the single biggest latency win available and it attacks the wait rather than the work.

9. **Move TTS to Azure Speech.** 500k free characters a month against ElevenLabs' 10k, an official SLA instead of an unofficial endpoint or a deprecating voice set, and the same `en-GB-SoniaNeural` voice already used in local development — so local and production would finally sound identical.

10. **Move speech-to-text server-side.** Browser STT was right for a free web demo, but it rules out Safari and rules out telephony entirely. Server-side recognition is the prerequisite for anything phone-shaped.

11. **Instrument the voice pipeline per turn** — recognition, retrieval, generation, summary, synthesis — and log endpointing false-trigger rate and transcription confidence alongside them. Right now I have measured stage latencies from manual testing; what I don't have is that data flowing continuously from real usage.

None of these are hypothetical nice-to-haves — they're things I actually hit walls on and had to consciously trade off to ship something that works end to end. Given more time, this is the order I'd tackle them in.

---

## Tech Stack

| Layer | Tech |
|---|---|
| **Backend** | FastAPI, ChromaDB, fastembed (`BAAI/bge-small-en-v1.5`), rank-bm25, PyMuPDF, Groq (`gpt-oss-120b` / `gpt-oss-20b`), SQLite |
| **Voice** | Browser `SpeechRecognition` (STT), ElevenLabs + `edge-tts` + browser `SpeechSynthesis` (TTS, with fallback chain) |
| **Frontend** | React (Vite) |
| **Deployment** | Railway (backend), Vercel (frontend) |
