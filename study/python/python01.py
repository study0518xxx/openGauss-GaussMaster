import asyncio
import time

# 定义异步函数
async def async_task(name, delay):
    print(f"任务 {name} 开始，等待 {delay}s")
    await asyncio.sleep(delay)  # 异步等待，不阻塞主线程
    print(f"任务 {name} 完成")

# 主异步函数
async def main():
    # 并发执行多个任务
    print("heell")
    task1 = async_task("A", 2)
    task2 = async_task("B", 1)
    await asyncio.gather(task1, task2)  # 批量运行

if __name__ == "__main__":
    start = time.time()
    asyncio.run(main())
    print(f"总耗时：{time.time() - start:.2f}s")
