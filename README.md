# Grade Predictor

> AI-powered grade tracking and simulation tool for students — parse your syllabus, import your grades, and know exactly what you need to earn your target final grade.

---

## Tech Stack

### Backend
![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.x-000000?style=flat&logo=flask&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-llama3.2-black?style=flat&logo=ollama&logoColor=white)
![pdfplumber](https://img.shields.io/badge/pdfplumber-PDF%20Parsing-red?style=flat)

### Frontend
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=flat&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-ES6+-F7DF1E?style=flat&logo=javascript&logoColor=black)
![Chart.js](https://img.shields.io/badge/Chart.js-4.4.0-FF6384?style=flat&logo=chartdotjs&logoColor=white)
![Google Fonts](https://img.shields.io/badge/Google%20Fonts-Playfair%20%2B%20Inter-4285F4?style=flat&logo=google&logoColor=white)

---

## What It Does

Grade Predictor is a local-first, privacy-friendly tool that helps students answer three questions:

1. **What is my current grade?** — Upload your syllabus and a Canvas/LMS grade export to get a precise weighted grade breakdown.
2. **What grade can I realistically earn?** — Run best-case, worst-case, and current-pace scenario projections.
3. **What do I need on remaining work?** — Enter a target grade and get the minimum average score required on ungraded assignments.

All document parsing is handled by a **local LLM** (Ollama + llama3.2), so your academic data never leaves your machine.

---

## Application Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GRADE PREDICTOR FLOW                         │
└─────────────────────────────────────────────────────────────────────┘

 ┌──────────────┐     PDF/TXT      ┌──────────────────┐
 │  1. Upload   │ ───────────────► │  syllabus_parser  │
 │   Syllabus   │                  │  (pdfplumber +    │
 └──────────────┘                  │   Ollama LLM)     │
                                   └────────┬─────────┘
                                            │  JSON policy
                                            ▼
 ┌──────────────┐                  ┌──────────────────┐
 │  2. Review   │ ◄──────────────  │  Grading Policy  │
 │   & Edit     │    editable UI   │  {categories,    │
 │   Policy     │                  │   weights, scale}│
 └──────┬───────┘                  └──────────────────┘
        │ confirmed policy
        ▼
 ┌──────────────┐     PDF          ┌──────────────────┐
 │  3. Upload   │ ───────────────► │  grades_parser    │
 │    Grades    │                  │  (pdfplumber +    │
 └──────────────┘                  │   Ollama LLM)     │
                                   └────────┬─────────┘
                                            │  JSON grades
                                            ▼
 ┌──────────────┐                  ┌──────────────────┐
 │  4. Review   │ ◄──────────────  │  Fuzzy Category  │
 │   & Edit     │    editable UI   │  Matcher         │
 │   Grades     │                  └──────────────────┘
 └──────┬───────┘
        │ confirmed grades
        ▼
 ┌──────────────────────────────────────────────────────┐
 │                  grade_calculator.py                  │
 │                                                      │
 │  apply_drop_policy() → calculate_category_grade()   │
 │  → calculate_weighted_grade() → get_letter_grade()  │
 │  → generate_scenarios()                              │
 └──────────────────────────────────────────────────────┘
        │
        ▼
 ┌──────────────┐        ┌──────────────────────────────┐
 │  5. Grade    │        │  What-If Analyzer            │
 │  Dashboard   │        │  - Hypothetical scores       │
 │  - Weighted  │        │  - Target grade calculator   │
 │    grade     │        │  - Needed average (binary    │
 │  - Charts    │        │    search)                   │
 │  - Scenarios │        │  - Scenario comparison chart │
 └──────────────┘        └──────────────────────────────┘
```

---

## Architecture

```
grade-predictor/
├── app.py                     # Flask app, API routes, file upload handling
├── requirements.txt
│
├── parser/
│   ├── syllabus_parser.py     # PDF/TXT → grading policy via Ollama LLM
│   └── grades_parser.py       # Grade export PDF → grade entries via Ollama LLM
│
├── engine/
│   └── grade_calculator.py    # Pure calculation logic (no external deps)
│
├── templates/
│   └── index.html             # Single-page app shell (6-panel wizard)
│
└── static/
    ├── css/style.css          # Academic dark theme (navy + gold)
    └── js/app.js              # GradePredictor SPA controller class
```

### Layer Responsibilities

| Layer | Responsibility |
|---|---|
| **parser/** | Document ingestion: extract raw text → send to local LLM → parse + validate JSON response |
| **engine/** | Pure calculation: drop policies, weighted averages, scenario generation, binary search for needed scores |
| **app.py** | HTTP layer: file uploads, temp file cleanup, route handlers, Ollama warm-up |
| **app.js** | Frontend state, panel navigation, chart rendering, real-time what-if updates |

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | Serve the SPA |
| `/api/upload-syllabus` | `POST` | Parse syllabus file, return grading policy JSON |
| `/api/upload-grades` | `POST` | Parse grade export PDF, return grade entries JSON |
| `/api/calculate` | `POST` | Compute weighted grade + scenario projections |
| `/api/what-if` | `POST` | Recalculate with user-provided hypothetical scores |
| `/api/needed-scores` | `POST` | Binary search for required average to hit target grade |
| `/api/scenarios` | `POST` | Generate best/worst/current-pace projections |

---

## Key Features

### Syllabus Parsing
- Supports PDF and TXT formats
- LLM extracts: category names, weights, grade scale (A/B/C/D/F thresholds), drop policies
- 4-step JSON extraction fallback for robust LLM output handling
- Manual review and editing before any calculations run

### Grade Import
- Supports Canvas and other LMS grade export PDFs
- 4-level fuzzy category matching (exact → normalized → substring → uncategorized)
- Status normalization: `graded`, `missing`, `excused`, `ungraded`
- Missing assignments count as 0; excused assignments excluded from calculations

### Drop Policies
- Drop Lowest N
- Drop Highest N
- None
- Always ensures at least 1 item remains after dropping

### Dashboard
- Current letter grade and percentage
- Grade buffer before next letter drop
- Weight accounting (% of course graded so far)
- Donut chart — category weight breakdown
- Bar chart — performance by category
- Per-category progress bars with risk flags
- Risk detection: critical (<60% in high-weight categories), warning (<70%)

### What-If Analyzer
- Enter projected scores for any ungraded assignment
- Debounced real-time recalculation (300ms)
- Target grade calculator: enter desired letter grade → see required average
- Achievability check (flags if target is mathematically impossible)
- Scenario comparison chart (best / worst / current pace)

---

## Setup & Usage

### Prerequisites

- **Python 3.13+**
- **Ollama** installed and running — [ollama.com](https://ollama.com)
- `llama3.2` model pulled

### Installation

```bash
# 1. Clone the repo
git clone https://github.com/your-username/grade-predictor.git
cd grade-predictor

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Pull the LLM model (one-time)
ollama pull llama3.2

# 4. Start Ollama (keep this running)
ollama serve

# 5. Run the app
python app.py
```

Then open [http://localhost:5000](http://localhost:5000) in your browser.

### File Requirements

| Upload | Accepted Formats | Notes |
|---|---|---|
| Syllabus | `.pdf`, `.txt` | Any syllabus with a grading breakdown section |
| Grade Export | `.pdf` | Canvas "Grades" PDF export or similar LMS export |

---

## Privacy

All LLM inference runs **locally** via Ollama. No document content, grades, or personal data is sent to any external server. The only network call made is to `http://localhost:11434` (your local Ollama instance).

---

## License

MIT — see [LICENSE](./LICENSE)
