"""Pack endpoints — the price list, plus the grid the packs screen renders.

An *offering* ("Maths seul") is a pack ``name`` shared across its level-variants, so the routes
come in two shapes: per-pack ones edit a single grid **cell** (its price, whether it's offered),
and ``/offerings/...`` ones edit the **row** (name, subjects) across every level at once. Keeping
that split is what stops a level-variant's subject list drifting away from its siblings.
"""


from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import ClassLevel, Pack
from app.schemas.pack import (
    GridCellOut,
    GridRowOut,
    OfferingCreate,
    OfferingUpdate,
    PackCreate,
    PackDetailOut,
    PackGridOut,
    PackOut,
    PackUpdate,
)
from app.services.pack_service import PackService

router = APIRouter(prefix="/packs", tags=["packs"])


def _detail(pack: Pack, service: PackService) -> PackDetailOut:
    return PackDetailOut(
        **PackOut.model_validate(pack).model_dump(),
        subjects=[s.name for s in pack.subjects],
        student_count=service.student_count(pack.id),
    )


@router.get("", response_model=list[PackDetailOut])
async def list_packs(
    db: Session = Depends(get_db),
    level: ClassLevel | None = Query(None),
    active: bool | None = Query(None),
) -> list[PackDetailOut]:
    service = PackService(db)
    return [_detail(pack, service) for pack in service.list(level=level, active=active)]


@router.get("/grid", response_model=PackGridOut)
async def get_grid(db: Session = Depends(get_db)) -> PackGridOut:
    """The offerings x levels matrix. Missing cells mean "not offered at that level"."""
    service = PackService(db)
    levels = list(ClassLevel)
    by_offering: dict[str, dict[ClassLevel, Pack]] = {}
    subjects: dict[str, list[str]] = {}
    for pack in service.list():
        by_offering.setdefault(pack.name, {})[pack.level] = pack
        subjects.setdefault(pack.name, [s.name for s in pack.subjects])

    rows = [
        GridRowOut(
            name=name,
            subjects=subjects[name],
            cells=[
                GridCellOut(
                    level=level,
                    pack_id=variants[level].id if level in variants else None,
                    price=variants[level].price if level in variants else None,
                    is_active=variants[level].is_active if level in variants else None,
                    student_count=(
                        service.student_count(variants[level].id) if level in variants else 0
                    ),
                )
                for level in levels
            ],
        )
        for name, variants in by_offering.items()
    ]
    return PackGridOut(levels=levels, rows=rows)


@router.post("", response_model=PackDetailOut, status_code=status.HTTP_201_CREATED)
async def create_pack(payload: PackCreate, db: Session = Depends(get_db)) -> PackDetailOut:
    service = PackService(db)
    pack = service.create(
        name=payload.name,
        level=payload.level,
        price=payload.price,
        subjects=payload.subjects,
    )
    return _detail(pack, service)


@router.post("/offerings", response_model=list[PackDetailOut], status_code=status.HTTP_201_CREATED)
async def create_offering(
    payload: OfferingCreate, db: Session = Depends(get_db)
) -> list[PackDetailOut]:
    """Create a whole grid row: one pack per priced level, sharing one subject set."""
    service = PackService(db)
    packs = service.create_offering(
        name=payload.name, subjects=payload.subjects, prices=payload.prices
    )
    return [_detail(pack, service) for pack in packs]


@router.patch("/offerings/{name}", response_model=list[PackDetailOut])
async def update_offering(
    name: str, payload: OfferingUpdate, db: Session = Depends(get_db)
) -> list[PackDetailOut]:
    """Rename an offering and/or set its subjects, across every level-variant at once."""
    service = PackService(db)
    fields = payload.model_dump(exclude_unset=True)
    if "name" in fields:
        fields["new_name"] = fields.pop("name")
    packs = service.update_offering(name, **fields)
    return [_detail(pack, service) for pack in packs]


@router.get("/{pack_id}", response_model=PackDetailOut)
async def get_pack(pack_id: int, db: Session = Depends(get_db)) -> PackDetailOut:
    service = PackService(db)
    return _detail(service.get(pack_id), service)


@router.patch("/{pack_id}", response_model=PackDetailOut)
async def update_pack(
    pack_id: int, payload: PackUpdate, db: Session = Depends(get_db)
) -> PackDetailOut:
    service = PackService(db)
    pack = service.update(pack_id, **payload.model_dump(exclude_unset=True))
    return _detail(pack, service)


@router.delete("/{pack_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pack(pack_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a pack no student is on; otherwise 409 — deactivate it instead."""
    PackService(db).delete(pack_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
