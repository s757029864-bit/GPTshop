FROM python:3.12-slim
WORKDIR /app
COPY server.py ./
COPY public ./public
ENV BIND_HOST=0.0.0.0
ENV PORT=8765
EXPOSE 8765
CMD ["python", "-u", "server.py"]
