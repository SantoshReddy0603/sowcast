from sqlalchemy import Float, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AgentTrace(Base):
    __tablename__ = "traces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    saved: Mapped[float] = mapped_column(Float, default=0)


class BacktestRecord(Base):
    __tablename__ = "backtest_results"
    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    saved: Mapped[float] = mapped_column(Float)
    body: Mapped[str] = mapped_column(Text)


class BacktestJob(Base):
    __tablename__ = "backtest_jobs"
    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    owner: Mapped[str] = mapped_column(String(36))
    expires: Mapped[float] = mapped_column(Float)
