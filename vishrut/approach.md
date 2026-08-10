# BITS Hackathon Approach: Bid Intelligence Pipeline

This document outlines our deterministic, hybrid LLM + relational SQL approach to solve bid intelligence questions on a synthetic construction document estate.

## Pipeline Architecture

```mermaid
flowchart TD
    subgraph Offline Stage [Stage A: Offline Knowledge Ingestion]
        Docs[Raw Extracted Texts] -->|Field Extraction| Extractors(field_extractors.py)
        Extractors -->|Extract Entities & Values| GraphBuilder(build_graph.py)
        GraphBuilder -->|Entity Linking & Deduplication| SQLiteDB[(SQLite Database)]
    end

    subgraph Online Stage [Stage B: Real-time Question Answering]
        Question[Natural Language Question] -->|Context Enrichment| PromptGen(Prompt Builder)
        SQLiteDB -->|Candidate Entities| Gazetteer[Gazetteer Gazetteer]
        Gazetteer -->|List Matching Entities| PromptGen
        PromptGen -->|Structured Prompt| LLM[OpenRouter API]
        LLM -->|Predict JSON Intent| Parser[Intent Parser]
        Parser -->|Check Entities| ValCheck{Gazetteer Validator}
        ValCheck -->|Valid| Dispatcher(shapes/dispatcher.py)
        ValCheck -->|Invalid| Error[ValueError / Fallback]
        Dispatcher -->|Select Query Shape| SQLQuery[Deterministic SQL Execution]
        SQLiteDB -->|Run Query| SQLQuery
        SQLQuery -->|Raw Data| Formatter(format_answer.py)
        Formatter -->|Formatted Number| CSV[submission.csv]
    end

    classDef stage fill:#f9f,stroke:#333,stroke-width:2px;
    classDef db fill:#bbf,stroke:#333,stroke-width:2px;
    classDef api fill:#bfb,stroke:#333,stroke-width:2px;
    class SQLiteDB db;
    class LLM api;
```

## Key Architectural Pillars

### 1. Data Ingestion & Relational Graphing (`build_db.py`)
Instead of reading documents dynamically per-question, we build a static SQLite database once offline:
- **Heuristic Extractors (`field_extractors.py`)**: Parse standard fields (project name, contract value, dates, client name, engineer name, certificate IDs) using regex filters.
- **Graph Compilation (`build_graph.py`)**: Cross-references relationships. For example, since completion certificates might list a project's client but omit the project manager, we scan CVs for "projects led" to build links between engineers and project values.

### 2. LLM as a Semantic Parser (Not a Calculator)
Standard LLMs struggle with multi-hop numerical reasoning (adding large numbers, counting dates, calculating ratios). Our design treats the LLM purely as a **parser**:
- The prompt includes a list of **Reasoning Shapes** (e.g. `absence`, `date_span`, `referenced_share`) and candidates from the **Gazetteer**.
- OpenRouter translates the question into a structured JSON specifying:
  ```json
  {
    "shape": "absence",
    "client_name": "Jal Nigam, Jharkhand",
    "engineer_name": null,
    "project_name": null
  }
  ```

### 3. Gazetteer & Strict Input Validation
To prevent the LLM from hallucinating names or outputting near-matches (e.g., "Jal Nigam Jharkhand" instead of "Jal Nigam, Jharkhand"):
- We fuzzy-match inputs against the **Gazetteer** compiled directly from the SQLite database.
- The pipeline validates that all extracted entities exist in the database schema before executing the shape handler.

### 4. Pure, Deterministic SQL Shape Executors
Each query logic (the 13 reasoning shapes) is implemented as a pure SQL function in `shapes/dispatcher.py`:
- Mathematics, filtering, sorting, and aggregations are offloaded to **SQLite**.
- This guarantees **100% determinism**—given the same database state and parameters, the query returns the exact same answer every single time.
