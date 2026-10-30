import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.aac_app.models.database import Symbol, User, UserSettings
from src.aac_app.services.arasaac import ArasaacService
from src.api import schemas
from src.api.dependencies import get_current_active_user, get_db, get_text

router = APIRouter()


class ArasaacSymbol(BaseModel):
    id: int
    label: str
    description: Optional[str] = None
    keywords: Optional[str] = None
    image_url: str


class ImportArasaacRequest(BaseModel):
    arasaac_id: int
    label: str
    description: Optional[str] = None
    category: str = "general"
    keywords: Optional[str] = None


@router.get("/search", response_model=List[ArasaacSymbol])
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
    try:
        # Check if symbol already exists (optional, maybe by label or some external ID field if we added one)
        # For now, we just allow duplicates or user manages them.

        # Download image
        image_content = await service.download_symbol_image(payload.arasaac_id)
        if not image_content:
            raise HTTPException(
                status_code=404,
                detail=get_text(user=current_user, key="errors.arasaac.downloadFailed"),
            )

        # Save image locally
        base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        uploads_dir = os.path.join(base_dir, "uploads", "symbols")
        os.makedirs(uploads_dir, exist_ok=True)

        filename = f"arasaac_{payload.arasaac_id}_{uuid.uuid4().hex[:8]}.png"
        file_path = os.path.join(uploads_dir, filename)

        with open(file_path, "wb") as f:
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
            user_lang = settings.ui_language if settings else None
        except Exception:
            user_lang = None

        db_symbol = Symbol(
            label=payload.label,
            description=payload.description,
            category=payload.category,
            image_path=public_path,
            keywords=payload.keywords,
            language=user_lang or "es",
            is_builtin=False,
        )
        db.add(db_symbol)
        db.commit()
        db.refresh(db_symbol)

        return db_symbol

    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_text(
                user=current_user, key="errors.arasaac.importFailed", error=str(e)
            ),
        )
    finally:
        await service.close()
