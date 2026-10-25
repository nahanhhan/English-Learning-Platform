"""学习偏好（含自动发音开关）的测试（内存库）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AiProvider, UserSetting  # noqa: F401  建表需要模型被导入
from app.routers.settings import PrefsBody, get_settings, update_prefs
from app.services import study


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_auto_speak_defaults_on():
    """没有记录时自动发音缺省为开启。"""
    db = make_db()
    prefs = get_settings(db=db)["prefs"]
    assert prefs["auto_speak"] == "1"


def test_update_auto_speak_keeps_other_prefs():
    """关闭自动发音能写回，且不影响其它偏好。"""
    db = make_db()
    study.set_setting(db, "daily_new_words", "30")
    db.commit()

    update_prefs(PrefsBody(auto_speak=False), db=db)

    prefs = get_settings(db=db)["prefs"]
    assert prefs["auto_speak"] == "0"
    assert prefs["daily_new_words"] == "30"


def test_update_auto_speak_back_on():
    """重新打开自动发音也能写回。"""
    db = make_db()
    update_prefs(PrefsBody(auto_speak=False), db=db)
    update_prefs(PrefsBody(auto_speak=True), db=db)
    assert get_settings(db=db)["prefs"]["auto_speak"] == "1"
