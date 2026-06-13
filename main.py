import uvicorn
from dotenv import load_dotenv

load_dotenv()

from api.server import app

if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
