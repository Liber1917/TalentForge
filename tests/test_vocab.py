from talentforge.profile.vocab import VOCAB_VERSION, ATTRIBUTE_VOCAB, resolve_attribute

def test_exact_match():
    assert resolve_attribute("薪资") == "薪资"
    assert resolve_attribute("  成长空间 ") == "成长空间"  # 去空白

def test_oov_falls_back():
    assert resolve_attribute("想要摸真东西") == "其他"
    assert resolve_attribute("") == "其他"

def test_versioned():
    assert isinstance(VOCAB_VERSION, int) and len(ATTRIBUTE_VOCAB) == 12
