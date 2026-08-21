import contextlib
import uuid

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src import config
from src.aac_app.models import Symbol, User, UserSettings
from src.aac_app.services.arasaac import ArasaacService
from src.aac_app.services.runtime_translation import normalize_language_code
from src.aac_app.services.vector_utils import index_symbol
from src.api import schemas
from src.api.deps import get_current_active_user, get_db, get_text

router = APIRouter()


class ArasaacSymbol(BaseModel):
    id: int
    label: str
    description: str | None = None
    keywords: str | None = None
    image_url: str


class ImportArasaacRequest(BaseModel):
    arasaac_id: int = Field(..., ge=1)
    label: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=10_000)
    category: str = Field("general", min_length=1, max_length=50)
    keywords: str | None = Field(None, max_length=10_000)


@router.get("/search", response_model=list[ArasaacSymbol])
async def search_arasaac(
    q: str, locale: str = "es", current_user: User = Depends(get_current_active_user)
):
    """
    Search for symbols in the ARASAAC library.
    """
    service = ArasaacService()
    try:
        effective_locale = locale or "es"
        try:
            # Prefer user's UI language if available when locale not explicitly set
            if not locale:
                settings = current_user.settings
                if settings and settings.ui_language:
                    effective_locale = settings.ui_language
        except Exception:
            pass
        results = await service.search_symbols(q, effective_locale)
        return results
    finally:
        await service.close()


@router.post("/import", response_model=schemas.SymbolResponse)
async def import_arasaac_symbol(
    payload: ImportArasaacRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Import a symbol from ARASAAC into the local library.
    Downloads the image and creates a Symbol record.
    """
    service = ArasaacService()
    file_path = None
    committed = False
    db_symbol = None
    try:
        normalized_label = payload.label.strip()
        if not normalized_label:
            raise HTTPException(
                status_code=400,
                detail=get_text(user=current_user, key="errors.validation"),
            )

        # Dedupe: link to an existing symbol with the same (case-folded) label
        # instead of creating a duplicate row and downloading the image again.
        # This mirrors the bulk library import, which also dedupes by label.
        existing = (
            db.query(Symbol)
            .filter(func.lower(Symbol.label) == normalized_label.casefold())
            .first()
        )
        if existing is not None:
            return existing

        # Download image
        image_content = await service.download_symbol_image(payload.arasaac_id)
        if not image_content:
            raise HTTPException(
                status_code=404,
                detail=get_text(user=current_user, key="errors.arasaac.downloadFailed"),
            )

        # Save image locally
        uploads_dir = config.UPLOADS_DIR / "symbols"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        filename = f"arasaac_{payload.arasaac_id}_{uuid.uuid4().hex[:8]}.png"
        file_path = uploads_dir / filename

        with file_path.open("wb") as f:
            f.write(image_content)

        public_path = f"/uploads/symbols/{filename}"

        # Create Symbol record
        # Prefer user's UI language for saved symbol metadata
        user_lang = None
        try:
            settings = (
                db.query(UserSettings)
                .filter(UserSettings.user_id == current_user.id)
                .first()
            )
            # Store the base code (e.g. "es") so it matches the language
            # filter used by the symbol search (exact match against "es"/"en").
            user_lang = normalize_language_code(settings.ui_language) if settings else None
        except Exception:
            user_lang = None

        db_symbol = Symbol(
            label=normalized_label,
            description=payload.description,
            category=payload.category,
            image_path=public_path,
            keywords=payload.keywords,
            language=user_lang or "es",
            is_builtin=False,
        )
        db.add(db_symbol)
        db.commit()
        committed = True
        db.refresh(db_symbol)
        # Indexing is an optional acceleration path. The durable symbol and
        # image must remain available when the vector store is unavailable or
        # temporarily fails.
        try:
            index_symbol(db_symbol)
        except Exception as exc:
            logger.warning("ARASAAC symbol indexing failed: {}", exc)

        return db_symbol

    except HTTPException:
        db.rollback()
        if file_path is not None and not committed:
            with contextlib.suppress(OSError):
                file_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        db.rollback()
        if file_path is not None and not committed:
            with contextlib.suppress(OSError):
                file_path.unlink(missing_ok=True)
        logger.error(f"Import failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_text(
                user=current_user, key="errors.arasaac.importFailed", error=str(e)
            ),
        )
    finally:
        await service.close()
