FROM python:3.11-slim

WORKDIR /app

# Instalar dependências
RUN pip install python-telegram-bot==20.7 requests psycopg2-binary python-dotenv

# Copiar arquivos
COPY bot_completo.py .
COPY scheduler_job.py .
COPY .env .

# Criar diretório de logs
RUN mkdir -p logs

# Comando padrão (será sobrescrito pelo docker-compose)
CMD ["python", "bot_completo.py"]
