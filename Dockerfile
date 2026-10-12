# For Render, Hugging Face Spaces, Railway or any container host.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY investor_fit ./investor_fit
COPY data ./data
ENV MCP_TRANSPORT=http PORT=7860
EXPOSE 7860
CMD ["python", "-m", "investor_fit.server"]
