# raffles.py
import requests
from typing import Optional
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from main import admin_required  # зависимость из main.py
from main import templates       # TemplateResponse

router = APIRouter()

RAFFLES_SERVER_URL = "https://rafflesrun.onrender.com"

# ----------------------
# Страница розыгрышей
@router.get("/admin/raffles", response_class=HTMLResponse)
async def admin_raffles_page(request: Request, _: None = Depends(admin_required)):
    try:
        resp = requests.get(f"{RAFFLES_SERVER_URL}/api/raffles", timeout=10)
        resp.raise_for_status()
        raffles = resp.json()
    except requests.RequestException as e:
        print("[ERROR] Не удалось получить розыгрыши:", e)
        raffles = []
    except ValueError as e:
        print("[ERROR] Ответ не JSON:", resp.text)
        raffles = []

    return templates.TemplateResponse(
        "admin/raffles.html",
        {"request": request, "raffles": raffles, "is_admin": True}
    )


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
    weapon_img: Optional[str] = Form(None),
    min_deposit_rub: int = Form(...),
    min_deposit_usd: int = Form(...),
    weapon_price_rub: int = Form(...),
    weapon_price_usd: int = Form(...),
    period_days: int = Form(...),
    _: None = Depends(admin_required)
):
    data = {
        "raffle_id": raffle_id,
        "name": name,
        "freq_seconds": freq_seconds,
        "card_type": card_type,
        "weapon_name": weapon_name,
        "weapon_type": weapon_type,
        "min_deposit_rub": min_deposit_rub,
        "min_deposit_usd": min_deposit_usd,
        "weapon_price_rub": weapon_price_rub,
        "weapon_price_usd": weapon_price_usd,
        "period_days": period_days
    }

    # Если пришло weapon_img, отправляем его, иначе сервер оставит старое значение
    if weapon_img is not None:
        data["weapon_img"] = weapon_img

    try:
        resp = requests.post(f"{RAFFLES_SERVER_URL}/api/raffles/update", data=data, timeout=10)
        resp.raise_for_status()
        json_resp = resp.json()
    except requests.RequestException as e:
        print("[ERROR] Не удалось обновить розыгрыш:", e)
        return JSONResponse({"ok": False, "error": str(e)})
    except ValueError:
        print("[ERROR] Ответ не JSON:", resp.text)
        return JSONResponse({"ok": False, "error": "Invalid JSON response from server"})

    return JSONResponse(json_resp)