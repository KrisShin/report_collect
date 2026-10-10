"""本地开发入口：python main.py 或 uvicorn app.main:app --reload。"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8600, reload=True)
