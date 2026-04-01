"""
ClubMillies — SQLAlchemy models.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    broker_type = Column(String(20), default="paper")  # paper, mt5, oanda
    login = Column(String(100), default="")
    password = Column(String(200), default="")
    server = Column(String(100), default="")
    symbol = Column(String(20), default="XAUUSDm")
    timeframe = Column(String(10), default="M15")
    profile = Column(String(20), default="SNIPER")  # SNIPER, AGGRESSIVE
    risk_per_trade = Column(Float, default=0.02)
    max_open_trades = Column(Integer, default=3)
    max_daily_loss = Column(Float, default=0.05)
    enabled = Column(Boolean, default=True)
    balance = Column(Float, default=10000.0)
    equity = Column(Float, default=10000.0)
    starting_balance = Column(Float, default=10000.0)
    is_demo = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    trades = relationship("Trade", back_populates="account", lazy="dynamic")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    direction = Column(String(10))  # BUY, SELL
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    lots = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    pnl = Column(Float, nullable=True)
    confluence_score = Column(Integer, default=0)
    confluence_reasons = Column(JSON, default=list)
    status = Column(String(20), default="OPEN")  # OPEN, CLOSED
    close_reason = Column(String(30), nullable=True)  # TP, SL, REVERSAL, CLIENT, etc.
    mt5_position_ticket = Column(Integer, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    account = relationship("Account", back_populates="trades")


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    signal_type = Column(String(10))  # BUY, SELL, HOLD
    score = Column(Integer)
    max_score = Column(Integer, default=15)
    reasons = Column(JSON, default=list)
    price = Column(Float)
    sl = Column(Float, nullable=True)
    tp = Column(Float, nullable=True)
    rsi = Column(Float, nullable=True)
    atr = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    currency = Column(String(10))
    impact = Column(String(20))  # low, medium, high
    forecast = Column(String(50), nullable=True)
    previous = Column(String(50), nullable=True)
    actual = Column(String(50), nullable=True)
    event_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id = Column(Integer, primary_key=True)
    source = Column(String(30))  # news, twitter, market, trade_close
    account_id = Column(Integer, nullable=True)
    trade_id = Column(Integer, nullable=True)
    input_summary = Column(Text)
    direction = Column(String(20))  # bullish, bearish, neutral
    confidence = Column(Integer, default=0)  # 0-100
    reasoning = Column(Text)
    raw_response = Column(Text, nullable=True)
    metrics = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TelegramChat(Base):
    __tablename__ = "telegram_chats"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(50), unique=True)
    username = Column(String(100), nullable=True)
    subscribed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Tweet(Base):
    __tablename__ = "tweets"

    id = Column(Integer, primary_key=True)
    tweet_id = Column(String(100), unique=True, index=True)
    author = Column(String(100))
    text = Column(Text)
    url = Column(String(300), nullable=True)
    created_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
