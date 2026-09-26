import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.routes import router as api_router
from app.db.session import engine
from app.db.models import Base

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description='Intelligent Document Processing - Trusted Extraction Pipeline',
    version='1.0.0'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Mount storage directory for viewing preprocessed images and ELA heatmaps directly
storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'storage'))
os.makedirs(storage_dir, exist_ok=True)
os.makedirs(os.path.join(storage_dir, 'tamper'), exist_ok=True)
os.makedirs(os.path.join(storage_dir, 'preprocessed'), exist_ok=True)
os.makedirs(os.path.join(storage_dir, 'raw'), exist_ok=True)

app.mount('/storage', StaticFiles(directory=storage_dir), name='storage')

app.include_router(api_router)

@app.get('/health')
def health_check():
    return {'status': 'healthy', 'phase': 'Phase 5 - Tamper Detection & Full Pipeline'}
