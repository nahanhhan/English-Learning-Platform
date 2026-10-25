from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# ---- 真题 ----

class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_type: Mapped[str] = mapped_column(String(10), index=True)  # cet6 / ky2
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, default=0)  # 六级有 6/12 月；考研为 12 月(次年考)，记真题年份
    set_no: Mapped[int] = mapped_column(Integer, default=1)
    q_type: Mapped[str] = mapped_column(String(20), index=True)  # translation / writing / small_writing / big_writing
    title: Mapped[str] = mapped_column(String(200), default="")
    # 作文题 directions / 翻译题说明
    prompt: Mapped[str] = mapped_column(Text, default="")
    # 翻译原文段落（六级为中文段，考研为英文段）
    source_text: Mapped[str] = mapped_column(Text, default="")
    chart_image: Mapped[str] = mapped_column(String(300), default="")  # 考研大作文图表图片相对路径
    source_file: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(String(300), default="")


# ---- 练习与批改 ----

class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"), nullable=True)
    exam_type: Mapped[str] = mapped_column(String(10))  # cet6 / ky2 / free
    q_type: Mapped[str] = mapped_column(String(20))  # translation / writing / small_writing / big_writing
    title: Mapped[str] = mapped_column(String(200), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")   # 提交时题面快照（自由练习时为用户粘贴内容）
    source_text: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / grading / done / failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Grading(Base):
    __tablename__ = "gradings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    mock: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0)
    full_score: Mapped[float] = mapped_column(Float, default=15)
    result_json: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---- 词库 ----

class Word(Base):
    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book: Mapped[str] = mapped_column(String(20), index=True)  # cet6 / kaoyan / custom
    headword: Mapped[str] = mapped_column(String(80), index=True)
    phonetic_us: Mapped[str] = mapped_column(String(80), default="")
    phonetic_uk: Mapped[str] = mapped_column(String(80), default="")
    translation: Mapped[str] = mapped_column(Text, default="")  # 中英释义
    definition: Mapped[str] = mapped_column(Text, default="")   # 英英释义
    tags: Mapped[str] = mapped_column(String(200), default="")
    freq: Mapped[int] = mapped_column(Integer, default=0)  # 词频，越大越常用


class Phrase(Base):
    __tablename__ = "phrases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book: Mapped[str] = mapped_column(String(20), index=True)  # exam / custom
    text: Mapped[str] = mapped_column(String(200), index=True)
    translation: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")


# ---- 间隔重复 ----

class SrsCard(Base):
    __tablename__ = "srs_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(10), index=True)  # word / phrase
    item_id: Mapped[int] = mapped_column(Integer, index=True)
    book: Mapped[str] = mapped_column(String(20), index=True, default="")
    status: Mapped[str] = mapped_column(String(10), default="new")  # new / learning / review
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[float] = mapped_column(Float, default=0)
    due: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    starred: Mapped[bool] = mapped_column(Boolean, default=False)
    in_mistake_book: Mapped[bool] = mapped_column(Boolean, default=False)  # 错题本
    mistake_consec: Mapped[int] = mapped_column(Integer, default=0)  # 错题本内连续答对次数
    added_at: Mapped[date] = mapped_column(Date, default=date.today)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = ({"sqlite_autoincrement": True},)


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("srs_cards.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(10))
    rating: Mapped[str] = mapped_column(String(10))  # again / hard / good
    last_interval: Mapped[float] = mapped_column(Float, default=0)
    next_interval: Mapped[float] = mapped_column(Float, default=0)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


# ---- AI 配置与偏好 ----

class AiProvider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    base_url: Mapped[str] = mapped_column(String(200))
    api_key: Mapped[str] = mapped_column(String(300), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class UserSetting(Base):
    __tablename__ = "user_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


# ---- 课内词汇：独立词库与可恢复的整轮练习 ----

class ClassroomGroup(Base):
    __tablename__ = "classroom_groups"
    __table_args__ = {"sqlite_autoincrement": True}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class ClassroomEntry(Base):
    __tablename__ = "classroom_entries"
    __table_args__ = (UniqueConstraint("group_id", "item_type", "normalized"), {"sqlite_autoincrement": True})
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("classroom_groups.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(10))
    english: Mapped[str] = mapped_column(String(300))
    normalized: Mapped[str] = mapped_column(String(300))
    translation: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="")
    in_mistake_book: Mapped[bool] = mapped_column(Boolean, default=False)
    mistake_consec: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)


class ClassroomSession(Base):
    __tablename__ = "classroom_sessions"
    __table_args__ = {"sqlite_autoincrement": True}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(100), unique=True)
    source: Mapped[str] = mapped_column(String(10))
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    receipts: Mapped[str] = mapped_column(Text, default="[]")


class ClassroomSessionItem(Base):
    __tablename__ = "classroom_session_items"
    __table_args__ = (UniqueConstraint("session_id", "position"), {"sqlite_autoincrement": True})
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("classroom_sessions.id"), index=True)
    entry_id: Mapped[int] = mapped_column(Integer, index=True)
    position: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[str] = mapped_column(Text)
    options: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(10), default="choice")
    picked: Mapped[str | None] = mapped_column(Text, nullable=True)
    spell_wrong: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[str] = mapped_column(String(10), default="")
