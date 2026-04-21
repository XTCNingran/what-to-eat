from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app import config
from app.routers import rooms, questionnaire, results, restaurants

app = FastAPI(title="今天吃什么", docs_url="/docs")

# 静态文件 & 模板
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))

# API 路由
app.include_router(rooms.router)
app.include_router(questionnaire.router)
app.include_router(results.router)
app.include_router(restaurants.router)


# 页面路由
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    from app.services import history_store
    recent = history_store.get_recent(3)
    return templates.TemplateResponse(request, "index.html", {"recent": recent})


@app.get("/room/{room_id}", response_class=HTMLResponse)
async def room_page(request: Request, room_id: str):
    from app.services import room_manager
    room = room_manager.get_room(room_id)
    if room is None:
        return templates.TemplateResponse(request, "index.html", {"error": "房间不存在", "recent": []})
    return templates.TemplateResponse(request, "room.html", {"room_id": room_id})


@app.get("/join/{room_id}", response_class=HTMLResponse)
async def join_page(request: Request, room_id: str):
    return templates.TemplateResponse(request, "join.html", {"room_id": room_id})


@app.get("/q/{room_id}", response_class=HTMLResponse)
async def questionnaire_page(request: Request, room_id: str):
    return templates.TemplateResponse(request, "questionnaire.html", {"room_id": room_id})


@app.get("/results/{room_id}", response_class=HTMLResponse)
async def results_page(request: Request, room_id: str):
    return templates.TemplateResponse(request, "results.html", {"room_id": room_id})


@app.get("/manage", response_class=HTMLResponse)
async def manage_page(request: Request):
    return templates.TemplateResponse(request, "manage.html", {})
