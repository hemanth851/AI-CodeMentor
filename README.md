# AI CodeMentor

AI CodeMentor is an LLM-powered interactive code explanation and learning platform designed to help students, developers, and learners understand source code, algorithms, and logic through guided explanations.

---

## Project Status: Step 2 — Code Input and Editor

This repository contains:
- **Monaco Editor Integration**: Embedded VS Code-grade code editor supporting syntax highlighting, line numbers, smooth editing, and auto-indentation.
- **Language Selector**: Dropdown supporting **Python**, **Java**, **C**, and **C++** with live syntax highlighting changes.
- **Explanation Level Selector**: Configuration for **Beginner**, **Intermediate**, and **Advanced** explanation depth.
- **Code File Uploading**: Source code file ingestion for `.py`, `.java`, `.c`, and `.cpp` files with automatic language detection, file reading, and 100 KB size validation.
- **Editor Controls**: Clear code action (preserving settings), default algorithm sample, and pre-analysis validation.
- **Backend**: FastAPI asynchronous Python service providing REST endpoints and CORS-enabled health check.

---

## Project Architecture

```text
AI-CodeMentor/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Header.jsx             # Navigation header & branding
│   │   │   ├── HealthStatus.jsx       # Real-time backend connectivity badge
│   │   │   ├── LanguageSelector.jsx   # Programming language dropdown
│   │   │   ├── LevelSelector.jsx      # Explanation level dropdown
│   │   │   ├── CodeEditor.jsx         # Monaco Editor wrapper with metadata bar
│   │   │   ├── ActionControls.jsx     # Upload, Clear, and Analyze buttons
│   │   │   └── FeedbackBanner.jsx     # Validation, error, and status banners
│   │   ├── constants/
│   │   │   └── editorConfig.js        # Languages, levels, sample code & helpers
│   │   ├── pages/
│   │   │   └── LandingPage.jsx        # AI CodeMentor interactive studio
│   │   ├── services/
│   │   │   └── api.js                 # API service connecting to backend
│   │   ├── App.jsx                    # Root React component
│   │   ├── main.jsx                   # React DOM entrypoint
│   │   └── index.css                  # Modern educational styling
│   ├── .env                           # Frontend environment variables
│   ├── .env.example                   # Template for environment variables
│   ├── index.html                     # HTML5 template with SEO & fonts
│   ├── package.json                   # React 19, Vite, Monaco Editor dependencies
│   └── vite.config.js                 # Vite bundler configuration
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── health.py              # GET /api/health endpoint
│   │   ├── models/
│   │   │   └── health.py              # Pydantic schemas (HealthCheckResponse)
│   │   ├── services/                  # Business logic and future services
│   │   └── main.py                    # FastAPI application and CORS configuration
│   ├── .env                           # Backend environment variables
│   ├── .env.example                   # Template for environment variables
│   ├── requirements.txt               # Python package dependencies
│   └── run.py                         # Server launcher script
│
├── .gitignore                         # Git exclusion rules
└── README.md                          # Project documentation and setup guide
```

---

## Prerequisites

- **Node.js**: v18.0 or newer (tested on v22.17)
- **npm**: v9.0 or newer
- **Python**: 3.10 or newer (tested on 3.13)

---

## Getting Started

### 1. Backend Setup (FastAPI)

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the backend server:
   ```bash
   python run.py
   ```

5. Verify the backend health endpoint:
   ```bash
   curl http://127.0.0.1:8000/api/health
   ```
   Expected response:
   ```json
   {
     "status": "ok",
     "message": "AI CodeMentor backend is running"
   }
   ```
   Interactive API docs are available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

### 2. Frontend Setup (React + Vite + Monaco Editor)

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the frontend development server:
   ```bash
   npm run dev
   ```

4. Open [http://localhost:5173](http://localhost:5173) in your browser:
   - **Default Code**: Loads with the `find_max(numbers)` Python snippet.
   - **Language Selection**: Toggle between Python, Java, C, and C++ to see syntax highlighting change immediately.
   - **Explanation Level**: Choose between Beginner, Intermediate, and Advanced.
   - **Upload Code**: Upload any `.py`, `.java`, `.c`, or `.cpp` file (under 100 KB). Language will auto-select based on file type.
   - **Clear**: Reset the editor without losing selected language or learning level.
   - **Analyze Code**: Validates editor content and displays status notifications.

---

## API Endpoints

| Method | Endpoint | Description | Sample Response |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | API status and overview | `{"name": "AI CodeMentor API", "version": "0.1.0", ...}` |
| `GET` | `/api/health` | Service health status check | `{"status": "ok", "message": "AI CodeMentor backend is running"}` |
| `GET` | `/docs` | Interactive Swagger API documentation | Swagger UI |
