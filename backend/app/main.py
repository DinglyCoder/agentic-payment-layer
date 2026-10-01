import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .blockchain import EscrowChain
from .config import get_settings
from .database import SessionLocal, close_database, init_database
from .fraud import FraudEngine
from .seed import seed_database
from .service import PaymentProcessor
from .websocket import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database()
    async with SessionLocal() as session:
        await seed_database(session, settings.simulation_mode and settings.seed_demo_data)

    chain = EscrowChain(settings)
    fraud = FraudEngine(settings)
    processor = PaymentProcessor(SessionLocal, fraud, chain, manager)
    app.state.processor = processor
    chain_task: asyncio.Task | None = None

    if chain.enabled:
        await chain.validate()
        chain_task = asyncio.create_task(
            chain.listen(
                processor.process_deposit,
                processor.process_resolution,
                processor.settle_due,
                processor.load_cursor,
                processor.save_cursor,
                processor.reconcile,
            ),
            name="sepolia-event-listener",
        )
        logger.info("Sepolia escrow listener started")
    else:
        logger.info("Paradime started in simulation mode")

    yield

    chain.stop()
    if chain_task:
        chain_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await chain_task
    await close_database()


app = FastAPI(
    title="Paradime API",
    description="Identity, fraud detection, and arbitration for autonomous agent payments.",
    version=settings.app_version,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.websocket("/ws/payments")
async def payment_events(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    await websocket.send_json({"event": "connected", "payment": None})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
