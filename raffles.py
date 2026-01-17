import requests
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

RAFFLES_SERVER_URL = "https://rafflesrun.onrender.com"

def admin_required(request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")

# ----------------------
# Страница розыгрышей
@router.get("/admin/raffles", response_class=HTMLResponse)
async def admin_raffles_page(request: Request, _: None = Depends(admin_required)):
    resp = requests.get(f"{RAFFLES_SERVER_URL}/api/raffles", timeout=10)
    raffles = resp.json()
    return templates.TemplateResponse("admin/raffles.html", {"request": request, "raffles": raffles, "is_admin": True})

# ----------------------
# Обновление розыгрыша
@router.post("/admin/raffles/update")
async def admin_raffle_update(
    raffle_id: int = Form(...),
    name: str = Form(...),
    freq_seconds: int = Form(...),
    card_type: str = Form(...),
    weapon_name: str = Form(...),
    weapon_type: str = Form(...),
    weapon_img: str = Form(...),
    min_deposit_rub: int = Form(...),
    min_deposit_usd: int = Form(...),
    weapon_price_rub: int = Form(...),
    weapon_price_usd: int = Form(...),
    period_days: int = Form(...),
    _: None = Depends(admin_required)
):
    resp = requests.post(
        f"{RAFFLES_SERVER_URL}/api/raffles/update",
        data={
            "raffle_id": raffle_id,
            "name": name,
            "freq_seconds": freq_seconds,
            "card_type": card_type,
            "weapon_name": weapon_name,
            "weapon_type": weapon_type,
            "weapon_img": weapon_img,
            "min_deposit_rub": min_deposit_rub,
            "min_deposit_usd": min_deposit_usd,
            "weapon_price_rub": weapon_price_rub,
            "weapon_price_usd": weapon_price_usd,
            "period_days": period_days
        }
    )
    return JSONResponse(resp.json())
