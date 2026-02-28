from app.main import app

if __name__ == "__main__":
    import uvicorn
    # This block allows you to run `python main.py` directly instead of uvicorn main:app
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
