import uvicorn

if __name__ == "__main__":
    # SQLite file defaults to ./vault.db; override with VAULT_DB.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
