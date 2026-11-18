from sqlalchemy import String, JSON, Double, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class Volume(Base):
    """一“卷”日表：封卷前可补报、排除单边窗；封卷后不再改动记录。"""

    __tablename__ = 'volumes'
    __table_args__ = (UniqueConstraint('series', 'sequence', name='ux_volumes_series_sequence'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    series: Mapped[str] = mapped_column(String(160), default='日表批次')
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    source: Mapped[str] = mapped_column(String(200), default='manual.json')
    records: Mapped[list] = mapped_column(JSON, default=list)
    exclusions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default='collecting')
    # Plain integer, not a ForeignKey: volumes and jobs would otherwise form a
    # circular FK cycle that CREATE TABLE cannot order. Cards link by id only.
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sealed_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    sealed_by: Mapped[str] = mapped_column(String(150), default='')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    next_volume_id: Mapped[int | None] = mapped_column(ForeignKey('volumes.id'), nullable=True)
