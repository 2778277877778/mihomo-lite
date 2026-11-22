from mihomo_lite import i18n
from mihomo_lite.models.app_state import AppSettings, ConnectionState


def test_english_is_the_source_language():
    i18n.set_language("en")
    assert i18n.tr("Dashboard") == "Dashboard"
    assert ConnectionState.CONNECTED.label == "Connected"


def test_chinese_translates_known_and_keeps_unknown():
    i18n.set_language("zh")
    try:
        assert i18n.tr("Dashboard") == "仪表盘"
        assert ConnectionState.CONNECTED.label == "已连接"
        assert i18n.tr("Some untranslated text") == "Some untranslated text"
    finally:
        i18n.set_language("en")


def test_invalid_language_falls_back_to_english():
    i18n.set_language("fr")
    assert i18n.get_language() == "en"


def test_language_setting_validation():
    assert AppSettings(language="zh").language == "zh"
    try:
        AppSettings(language="fr")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValidationError")
