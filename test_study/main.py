import uvicorn
from fastapi import FastAPI

# 实例化应用
app = FastAPI(title="我的第一个FastAPI", version="1.0")

# 根路由 GET 请求
@app.get("/")
def root():
    return {"msg": "Hello FastAPI"}

# 带参数路由
@app.get("/hello/{name}")
def say_hello(name: str):
    return {"name": name, "msg": "你好"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)