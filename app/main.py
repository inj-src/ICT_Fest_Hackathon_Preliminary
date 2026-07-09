"""CoWork API application entrypoint."""
from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse

from .database import Base, engine
from .errors import AppError, app_error_handler
from .routers import admin, auth, bookings, health, rooms

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CoWork API", version="1.0.0")

app.add_exception_handler(AppError, app_error_handler)


@app.get("/", include_in_schema=False)
def read_root():
    return RedirectResponse(url="/docs")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(bookings.router)
app.include_router(admin.router)
