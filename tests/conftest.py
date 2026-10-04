import os

# app.core.config가 import 시점에 Settings()를 만들므로 app보다 먼저 설정한다.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
