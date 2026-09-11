FROM python:3.10

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fail the image build early if the scraper's configuration module is missing
# or incompatible with the installed dependencies.
RUN python -c "from config import ExperimentConfig, get_config"

CMD ["python", "parallel_scraper.py"]
