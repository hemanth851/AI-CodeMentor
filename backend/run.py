import os
import uvicorn
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting AI CodeMentor backend server at http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
