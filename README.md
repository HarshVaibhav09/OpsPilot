# OpsPilot

A document intelligence assistant for logistics ops teams. Upload your rate cards, SOPs, vendor contracts, and compliance circulars, and just ask questions instead of Ctrl+F-ing through 50-page PDFs.

Built for the VANCO AI technical assignment.

- **Live app:** https://ops-pilot-phi.vercel.app
- **Backend API:** https://opspilot-production-427d.up.railway.app
- **Repo:** https://github.com/HarshVaibhav09/OpsPilot

Built by Harsh Vaibhav.

---

## Table of Contents

| Section | Description |
|---------|-------------|
| [Overview](#overview) | Brief introduction to OpsPilot |
| [Features](#features) | Core capabilities of the platform |
| [Tech Stack](#tech-stack) | Technologies used in the project |
| [Architecture](#architecture) | High-level system architecture |
| [Getting Started](#getting-started) | Installation and setup instructions |
| [Chunking & Retrieval Decisions](#chunking--retrieval-decisions) | Design choices behind document ingestion and retrieval |
| [Honest Trade-offs](#honest-trade-offs) | Engineering compromises made during development |
| [Known Limitations](#known-limitations) | Current limitations of the system |
| [If I Had One More Week](#if-i-had-one-more-week) | Planned improvements and future work |
| [Future Scope](#future-scope) | Long-term enhancements |
| [License](#license) | Project license information |

---

## What It Does

- Upload 2-3+ PDFs — it extracts text and tables, chunks them, embeds them, and stores them in a vector DB.
- Ask questions in a chat interface, grounded strictly in the uploaded documents.
- Follow-up questions work. Ask "what's the penalty clause?" then "who does it apply to?" and it resolves the second question using the first.
- Every answer comes with citations back to the source file, page, and section.
- Each document also gets an automatic contradiction check on upload — if two sections of the same doc disagree on a date, amount, or name, it flags it.
- A developer mode toggle shows what actually got retrieved: similarity scores, the rewritten query, chunk-level detail — mostly there so I could debug my own retrieval quality, but it's genuinely useful if you're the kind of user who wants to see the receipts.

---

## Architecture

I've attached a hand-drawn version of this below (photo), but here's the flow:

Frontend (React, on Vercel) talks to a FastAPI backend (on Railway). The backend splits into two pipelines:

### Ingestion Pipeline
PDF comes in → PyMuPDF pulls out text and tables page by page → text gets chunked (heading-aware + recursive splitting, more on this below) → everything gets embedded with a sentence-transformers model → lands in a Chroma vector store with a parallel BM25 index for keyword search. The doc also gets sent once to Groq for a contradiction check, and that result is cached.

### Chat Pipeline
User message comes in → if there's prior conversation history, the message gets rewritten into a standalone query (so "who does it apply to?" becomes "who does the penalty clause apply to?") → that standalone query hits hybrid retrieval (dense + BM25 fused) → the top chunks get formatted into context → Groq generates the actual answer. The turn gets saved to a SQLite session store so the next follow-up has history to work with.

**Diagram:**

![Architecture diagram](./architecture-diagram.jpg)

*(hand-drawn — see the SVG version I worked from in the repo if the photo's hard to read)*

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
LLM_MODEL=llama-3.3-70b-versatile

EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

CHUNK_SIZE=700
CHUNK_OVERLAP=120

TOP_K_RETRIEVAL=8
TOP_K_FINAL=5

CHROMA_PERSIST_DIR=./data/chroma
SESSION_DB_PATH=./data/sessions.db

CORS_ORIGINS=https://your-frontend-url.vercel.app
```

Run it:

```bash
uvicorn app.main:app --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Docker (optional)

There's a `Dockerfile` for both frontend and backend if you'd rather not set up the environment locally.

---

## Chunking and Retrieval — What I Did and Why

### Chunking

I didn't just do a flat fixed-size split. Each PDF page gets processed for text and tables separately:

1. **Tables** get pulled out with PyMuPDF's table detection and kept as whole chunks (converted to markdown), because splitting a table mid-row destroys it for retrieval. You lose the row/column relationship and the chunk becomes useless.
2. **Text** gets grouped under detected headings first (numbered headings like "3.2 Payment Terms", or ALL-CAPS section titles), then split further with a recursive character splitter (700 chars, 120 overlap).

The idea: chunk boundaries should respect document structure where possible, not just cut every N characters blind. A chunk that's half of one section and half of another is confusing for the LLM and for retrieval both.

This works well on documents with clear section headers — SOPs, contracts, circulars. It works less well on dense, tabular reports with no clear heading structure (see limitations below).

### Retrieval

Hybrid: dense vector search (Chroma, cosine similarity) fused with BM25 keyword search.

I went hybrid because logistics documents are full of exact terms that matter — SKU codes, clause numbers, specific vendor names — where pure dense retrieval sometimes misses an exact match that BM25 catches instantly, and vice versa for more semantic/paraphrased questions. Retrieve top 8 candidates, return top 5 after formatting.

I originally had a reranking step planned between those two numbers — a cross-encoder reranker that would re-score the 8 candidates before truncating to 5, and I even had a `rerank_scores` field wired up to show in developer mode on the frontend. I pulled it out. More on why below.

### Query Rewriting for Follow-Ups

Before retrieval, if there's conversation history, the raw question gets rewritten into a standalone query by the LLM. Retrieval runs on the rewritten query; the original question plus history goes to the final answer-generation call. This is the actual mechanism that makes "and who does it apply to?" work.

---

## Known Limitations (Honestly)

1. **Reranker got cut for memory, not because it didn't help.** I had a cross-encoder reranker between retrieval and generation, with scores meant to show up in developer mode. Backend deployment on Render kept crashing from RAM shortage once I added it — running torch + sentence-transformers + a reranker on a free tier just doesn't fit. I pulled the reranker to get a working deployment instead of a memory-crashed one, and moved the backend to Railway. The retrieval step still retrieves 8 and returns 5, but that final trim is a plain truncation right now, not a reranked one.

2. **Large PDFs are slow, on both ends.** An 85-page PDF takes noticeably longer to upload and chunk than a 10-page one, and that's compounded by the fact that ingestion is fully synchronous — text extraction, chunking, embedding, *and* the LLM contradiction check all happen in the same request before you get a response. On a free-tier host this can feel sluggish, and on a large enough file it risks hitting a request timeout. There's no background job queue or progress indicator right now — you upload and wait.

3. **Answers get a bit less precise on large, structurally flat documents.** I tested this directly with an 85-page truck utilization metrics PDF. Answers on it were occasionally a little off compared to the same kind of question on a well-structured contract or SOP. My read on why: that document is mostly numbers and tables with very few clean section headings, so most of it falls into a generic catch-all section rather than getting properly grouped. Combined with no reranker, retrieval has less signal to work with on documents like this. It's a real gap, not a hypothetical one.

4. **No background/async ingestion.** Uploading 3 documents means 3 sequential rounds of extraction + embedding + an LLM call, one after another, in a single request.

5. **Error handling on LLM calls is thinner than it should be.** If Groq rate-limits or times out mid-request, right now that can surface as a raw error rather than a graceful fallback message. The "I couldn't find enough information" path exists for empty retrieval, but not yet for LLM-call failures specifically.

6. **`doc_id` filtering is all-or-one.** You can scope a question to a single uploaded document or search across everything — there's no way to pick a subset of 2 out of 5 documents.

7. **Contradiction analysis is capped and cached in memory.** For very long documents it only looks at the first ~100 chunks, not the whole document, and results are cached in a plain in-memory dict, not a database, so they don't survive a backend restart.

---

## What I'd Build Next With One More Week

If I had another week on this, in order of what I'd actually prioritize:

1. **Bring the reranker back, properly, on infrastructure that can hold it.** This is the fix I most want to make. I'd either move to a host with more memory headroom or use a much smaller/quantized cross-encoder that fits the free tier, and finish wiring up the `rerank_scores` in developer mode I'd already started building the frontend for. I know exactly what this would look like — I just ran out of memory budget, not ideas.

2. **Fix chunking for tabular/low-structure documents.** The heading-detection approach works for contracts and SOPs but clearly breaks down on dense metrics reports, which is exactly the kind of document a logistics ops team deals with constantly (utilization reports, rate cards). I'd add a fallback strategy — maybe using table density or page layout as a secondary signal for section boundaries when there's no clean heading pattern — so retrieval quality doesn't degrade on exactly the documents this tool is supposed to help with most.

3. **Make ingestion async.** Upload triggers a background job, return immediately with a job ID, and the frontend polls for status (or uses a websocket) instead of blocking the whole request on extraction + embedding + an LLM call. This alone would fix most of the "large PDFs feel slow" problem, even without touching the actual chunking speed.

4. **Harden error handling around LLM calls.** Wrap the Groq calls in `chat_service.py` with real fallback behavior instead of letting failures propagate as raw 500s. A rate-limited request should degrade to a calm "having trouble right now, try again" message, the same way an empty-retrieval result already does.

5. **Move the vector store and session DB to actual persistent storage.** Right now they're local files inside the container, which isn't safe against a redeploy or restart on Railway's free tier. I'd move Chroma to a hosted instance (or attach a proper persistent volume) and do the same for the session SQLite file, so a redeploy doesn't wipe every document a user has uploaded.

6. **Let users scope a question to a subset of documents**, not just one doc or all of them — closer to how someone actually works when they've got 5+ documents loaded and only care about 2 of them right now.

None of these are "nice to have someday" items to me — they're the exact things I hit walls on this week and had to consciously trade off to ship something that actually works end to end. Given more time, this is the order I'd tackle them in.

---

## Tech Stack

| Layer | Tech |
|---|---|
| **Backend** | FastAPI, ChromaDB, sentence-transformers (`BAAI/bge-small-en-v1.5`), rank-bm25, PyMuPDF, Groq (`llama-3.3-70b-versatile`), SQLite |
| **Frontend** | React (Vite) |
| **Deployment** | Railway (backend), Vercel (frontend) |
