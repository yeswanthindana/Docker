from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.utils.apilogs import logger
import time

app = FastAPI(
    title="Docker Management API",
    description="API to retrieve running containers, images, and volumes from local and remote Docker daemons.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_api_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log the incoming request securely 
    logger.info(f"Incoming Request -> {request.method} {request.url.path} from client {request.client.host}")
    
    # Process the route and grab the response
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"Response Out <- {request.method} {request.url.path} - Status {response.status_code} ({process_time:.3f}s)")
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Error Processing <- {request.method} {request.url.path} - FAILED ({process_time:.3f}s) - {str(e)}")
        raise e

app.include_router(api_router)
