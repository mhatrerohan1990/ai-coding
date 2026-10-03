import uvicorn

if __name__ == "__main__":
    # Requires JWT_SECRET in the environment (the app refuses to start without it).
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
