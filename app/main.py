from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import APIStatusError, AuthenticationError, OpenAI
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .config import APP_NAME, OPENAI_API_KEY, OPENAI_MODEL, SECRET_KEY, PAGE_SIZE
from .database import Base, engine, get_db
from .models import User, Quote, UserQuoteReaction
from .security import hash_password, verify_password
from .deps import get_current_user, require_user
from .utils import json_error, generate_qr_data_uri, highlight_text

app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=False)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["highlight"] = highlight_text


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.middleware("http")
async def add_default_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


# Helper

def redirect_with_message(url: str, message: str | None = None) -> RedirectResponse:
    response = RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
    if message:
        response.set_cookie("flash", message, max_age=5)
    return response


def get_flash(request: Request) -> Optional[str]:
    flash = request.cookies.get("flash")
    return flash


def get_openai_client() -> OpenAI | None:
    if not OPENAI_API_KEY:
        return None
    return OpenAI(api_key=OPENAI_API_KEY)


# Auth pages
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("register.html", {"request": request, "user": user, "flash": get_flash(request)})


@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip()
    email = email.strip().lower()
    if not username or not email or not password:
        return json_error("invalid_input", "All fields are required.")
    if db.query(User).filter(User.username == username).first():
        return json_error("user_exists", "Username already taken.")
    if db.query(User).filter(User.email == email).first():
        return json_error("email_exists", "Email already registered.")

    user = User(username=username, email=email, password_hash=hash_password(password), created_at=datetime.utcnow())
    db.add(user)
    db.commit()
    return redirect_with_message("/login", "Registration successful. Please login.")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "user": user, "flash": get_flash(request)})


@app.post("/login")
def login(
    request: Request,
    username_or_email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username_or_email = username_or_email.strip()
    user = (
        db.query(User)
        .filter(or_(User.username == username_or_email, User.email == username_or_email.lower()))
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        return json_error("invalid_credentials", "Invalid username/email or password.", 401)
    request.session["user_id"] = user.id
    user.last_login_at = datetime.utcnow()
    db.commit()
    return redirect_with_message("/", "Welcome back!")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect_with_message("/", "Logged out.")


# Quote listing and search
@app.get("/", response_class=HTMLResponse)
def list_quotes(
    request: Request,
    q: str | None = None,
    author: str | None = None,
    source: str | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    query = db.query(Quote).join(User).order_by(Quote.created_at.desc())
    keyword = (q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Quote.content.ilike(like), Quote.explanation.ilike(like)))
    if author:
        query = query.filter(Quote.author.ilike(f"%{author.strip()}%"))
    if source:
        query = query.filter(Quote.source.ilike(f"%{source.strip()}%"))

    total = query.count()
    page = max(page, 1)
    quotes = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    reactions = {}
    if user:
        user_reacts = (
            db.query(UserQuoteReaction)
            .filter(UserQuoteReaction.user_id == user.id, UserQuoteReaction.quote_id.in_([q.id for q in quotes]))
            .all()
        )
        for r in user_reacts:
            reactions.setdefault(r.quote_id, set()).add(r.reaction_type)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "quotes": quotes,
            "user": user,
            "page": page,
            "page_size": PAGE_SIZE,
            "total": total,
            "keyword": keyword,
            "author": author or "",
            "source": source or "",
            "reactions": reactions,
            "flash": get_flash(request),
        },
    )


# Quote creation
@app.get("/quotes/new", response_class=HTMLResponse)
def new_quote_page(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse("quote_form.html", {"request": request, "user": user, "quote": None, "flash": get_flash(request)})


@app.post("/quotes")
def create_quote(
    request: Request,
    content: str = Form(...),
    source: str | None = Form(None),
    author: str | None = Form(None),
    explanation: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not content.strip():
        return json_error("invalid_input", "Content is required.")
    quote = Quote(
        content=content.strip(),
        source=source.strip() if source else None,
        author=author.strip() if author else None,
        explanation=explanation.strip() if explanation else None,
        owner_id=user.id,
    )
    db.add(quote)
    db.commit()
    return redirect_with_message("/me/quotes", "Quote added.")


@app.post("/api/ai-explanation")
def ai_explanation(
    content: str = Form(...),
    prompt: str = Form(""),
    user: User = Depends(require_user),
):
    cleaned_content = content.strip()
    if not cleaned_content:
        return json_error("invalid_input", "Content is required to generate an explanation.")
    user_prompt = prompt.strip() or "请为这段语录写一段简洁的解释，并说明其含义和适用场景。"
    try:
        client = get_openai_client()
        if not client:
            return json_error("invalid_api_key", "OpenAI API key is missing or invalid.", status.HTTP_401_UNAUTHORIZED)
        result = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant who explains quotes clearly and concisely in Chinese.",
                },
                {
                    "role": "user",
                    "content": f"{user_prompt}\n\n语录：{cleaned_content}",
                },
            ],
            temperature=0.7,
        )
        explanation = result.choices[0].message.content.strip()
        return {"explanation": explanation}
    except AuthenticationError:
        return json_error("invalid_api_key", "OpenAI API key is missing or invalid.", status.HTTP_401_UNAUTHORIZED)
    except APIStatusError as exc:
        if exc.status_code == 401:
            return json_error("invalid_api_key", "OpenAI API key is missing or invalid.", status.HTTP_401_UNAUTHORIZED)
        return json_error("ai_error", "OpenAI service returned an error. Please try again.", status.HTTP_502_BAD_GATEWAY)
    except Exception:
        return json_error("ai_error", "Failed to generate explanation. Please try again later.", status.HTTP_500_INTERNAL_SERVER_ERROR)


# Quote detail
@app.get("/quotes/{quote_id}", response_class=HTMLResponse)
def quote_detail(
    request: Request,
    quote_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    user_reactions = set()
    if user:
        reacts = (
            db.query(UserQuoteReaction)
            .filter(
                UserQuoteReaction.user_id == user.id,
                UserQuoteReaction.quote_id == quote.id,
            )
            .all()
        )
        user_reactions = {r.reaction_type for r in reacts}
    url = str(request.url)
    qr_uri = generate_qr_data_uri(url)
    return templates.TemplateResponse(
        "quote_detail.html",
        {
            "request": request,
            "quote": quote,
            "user": user,
            "reactions": user_reactions,
            "share_url": url,
            "qr_uri": qr_uri,
            "flash": get_flash(request),
            "meta_description": quote.explanation or quote.content[:150],
            "og_title": quote.author or "Quote",
            "og_description": quote.content,
            "og_url": url,
        },
    )


# Quote edit/delete
@app.get("/quotes/{quote_id}/edit", response_class=HTMLResponse)
def edit_quote_page(
    request: Request,
    quote_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return templates.TemplateResponse("quote_form.html", {"request": request, "user": user, "quote": quote, "flash": get_flash(request)})


@app.post("/quotes/{quote_id}/edit")
def update_quote(
    request: Request,
    quote_id: int,
    content: str = Form(...),
    source: str | None = Form(None),
    author: str | None = Form(None),
    explanation: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        return json_error("not_found", "Quote not found", 404)
    if quote.owner_id != user.id:
        return json_error("forbidden", "You cannot edit this quote", 403)
    if not content.strip():
        return json_error("invalid_input", "Content is required.")
    quote.content = content.strip()
    quote.source = source.strip() if source else None
    quote.author = author.strip() if author else None
    quote.explanation = explanation.strip() if explanation else None
    db.commit()
    return redirect_with_message(f"/quotes/{quote.id}", "Quote updated.")


@app.post("/quotes/{quote_id}/delete")
def delete_quote(
    request: Request,
    quote_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        return json_error("not_found", "Quote not found", 404)
    if quote.owner_id != user.id:
        return json_error("forbidden", "You cannot delete this quote", 403)
    db.delete(quote)
    db.commit()
    return redirect_with_message("/me/quotes", "Quote deleted.")


# My pages
@app.get("/me/quotes", response_class=HTMLResponse)
def my_quotes(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    quotes = db.query(Quote).filter(Quote.owner_id == user.id).order_by(Quote.created_at.desc()).all()
    return templates.TemplateResponse("my_quotes.html", {"request": request, "quotes": quotes, "user": user, "flash": get_flash(request)})


@app.get("/me/likes", response_class=HTMLResponse)
def my_likes(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    reactions = (
        db.query(UserQuoteReaction)
        .filter(UserQuoteReaction.user_id == user.id, UserQuoteReaction.reaction_type == "like")
        .all()
    )
    quotes = [r.quote for r in reactions]
    return templates.TemplateResponse("my_reactions.html", {"request": request, "quotes": quotes, "user": user, "title": "My Likes", "flash": get_flash(request)})


@app.get("/me/collections", response_class=HTMLResponse)
def my_collections(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    reactions = (
        db.query(UserQuoteReaction)
        .filter(UserQuoteReaction.user_id == user.id, UserQuoteReaction.reaction_type == "collect")
        .all()
    )
    quotes = [r.quote for r in reactions]
    return templates.TemplateResponse("my_reactions.html", {"request": request, "quotes": quotes, "user": user, "title": "My Collections", "flash": get_flash(request)})


# Reaction toggle
@app.post("/quotes/{quote_id}/react")
def toggle_reaction(
    request: Request,
    quote_id: int,
    reaction_type: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if reaction_type not in {"like", "collect"}:
        return json_error("invalid_reaction", "Reaction must be like or collect")
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        return json_error("not_found", "Quote not found", 404)
    existing = (
        db.query(UserQuoteReaction)
        .filter(
            UserQuoteReaction.user_id == user.id,
            UserQuoteReaction.quote_id == quote.id,
            UserQuoteReaction.reaction_type == reaction_type,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
        message = "Removed"
    else:
        reaction = UserQuoteReaction(user_id=user.id, quote_id=quote.id, reaction_type=reaction_type)
        db.add(reaction)
        db.commit()
        message = "Added"
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"status": "ok", "message": message})
    return redirect_with_message(request.headers.get("referer", "/"), f"{reaction_type.title()} {message.lower()}")


# API endpoints
@app.get("/api/me")
def api_me(user: User | None = Depends(get_current_user)):
    if not user:
        return json_error("unauthorized", "Login required", 401)
    return {"id": user.id, "username": user.username, "email": user.email}


@app.get("/api/quotes")
def api_list_quotes(
    q: str | None = None,
    author: str | None = None,
    source: str | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    query = db.query(Quote)
    keyword = (q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Quote.content.ilike(like), Quote.explanation.ilike(like)))
    if author:
        query = query.filter(Quote.author.ilike(f"%{author.strip()}%"))
    if source:
        query = query.filter(Quote.source.ilike(f"%{source.strip()}%"))
    total = query.count()
    page = max(page, 1)
    quotes = query.order_by(Quote.created_at.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    return {
        "items": [
            {
                "id": q.id,
                "content": q.content,
                "author": q.author,
                "source": q.source,
                "explanation": q.explanation,
                "owner_id": q.owner_id,
                "created_at": q.created_at,
            }
            for q in quotes
        ],
        "page": page,
        "total": total,
    }


@app.get("/api/quotes/{quote_id}")
def api_quote_detail(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        return json_error("not_found", "Quote not found", 404)
    return {
        "id": quote.id,
        "content": quote.content,
        "author": quote.author,
        "source": quote.source,
        "explanation": quote.explanation,
        "owner_id": quote.owner_id,
        "created_at": quote.created_at,
    }


@app.post("/api/quotes")
def api_create_quote(
    content: str = Form(...),
    source: str | None = Form(None),
    author: str | None = Form(None),
    explanation: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not content.strip():
        return json_error("invalid_input", "Content is required.")
    quote = Quote(
        content=content.strip(),
        source=source.strip() if source else None,
        author=author.strip() if author else None,
        explanation=explanation.strip() if explanation else None,
        owner_id=user.id,
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return {"id": quote.id, "message": "created"}


@app.post("/api/quotes/{quote_id}")
def api_update_quote(
    quote_id: int,
    content: str = Form(...),
    source: str | None = Form(None),
    author: str | None = Form(None),
    explanation: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        return json_error("not_found", "Quote not found", 404)
    if quote.owner_id != user.id:
        return json_error("forbidden", "You cannot edit this quote", 403)
    if not content.strip():
        return json_error("invalid_input", "Content is required.")
    quote.content = content.strip()
    quote.source = source.strip() if source else None
    quote.author = author.strip() if author else None
    quote.explanation = explanation.strip() if explanation else None
    db.commit()
    return {"message": "updated"}


@app.post("/api/quotes/{quote_id}/delete")
def api_delete_quote(
    quote_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        return json_error("not_found", "Quote not found", 404)
    if quote.owner_id != user.id:
        return json_error("forbidden", "You cannot delete this quote", 403)
    db.delete(quote)
    db.commit()
    return {"message": "deleted"}


@app.post("/api/quotes/{quote_id}/react")
def api_react_quote(
    quote_id: int,
    reaction_type: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if reaction_type not in {"like", "collect"}:
        return json_error("invalid_reaction", "Reaction must be like or collect")
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        return json_error("not_found", "Quote not found", 404)
    existing = (
        db.query(UserQuoteReaction)
        .filter(
            UserQuoteReaction.user_id == user.id,
            UserQuoteReaction.quote_id == quote.id,
            UserQuoteReaction.reaction_type == reaction_type,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
        message = "removed"
    else:
        reaction = UserQuoteReaction(user_id=user.id, quote_id=quote.id, reaction_type=reaction_type)
        db.add(reaction)
        db.commit()
        message = "added"
    return {"message": message}
