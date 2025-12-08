# Configuration settings

import os
from dotenv import load_dotenv

load_dotenv()

# SQL Server Configuration
SQL_SERVER = os.getenv("SQL_SERVER", "localhost")
SQL_DATABASE = os.getenv("SQL_DATABASE", "ADAS_DB")
SQL_USERNAME = os.getenv("SQL_USERNAME", "sa")
SQL_PASSWORD = os.getenv("SQL_PASSWORD", "")
SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")

# Model Worker Configuration
MODEL_WORKER_URL = os.getenv("MODEL_WORKER_URL", "http://localhost:8000")

# Perplexity API (optional)
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# CORS Configuration
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
