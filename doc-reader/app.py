from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.chat import router as chat_router

app = FastAPI(title="Doc Reader - 长文档智能阅读")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(chat_router)


@app.get("/")
def index():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "ok"}
