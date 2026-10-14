FROM python:3.13-slim
ENV POETRY_VIRTUALENVS_CREATE=false

WORKDIR app/
COPY . .

RUN pip install poetry \
&& poetry config installer.max-workers 10 \
&& poetry install --no-interaction --no-ansi --without dev \
&& chmod +x entrypoint.sh

EXPOSE 8000
CMD ["./entrypoint.sh"]
