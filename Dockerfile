FROM python:3.10-slim

WORKDIR /code

# 安装依赖
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 复制所有代码
COPY . .

# 魔搭自定义镜像暴露 7860 端口
EXPOSE 7860

# 启动 FastAPI 服务
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
