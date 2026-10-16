import pytest

from netlab.content import GUIDES, LEARNING_MODES, TOPICS, get_topic, search_topics


def test_curriculum_has_unique_complete_targeted_lessons_and_existing_links():
    assert len(TOPICS) >= 150
    ids = {topic["id"] for topic in TOPICS}
    assert len(ids) == len(TOPICS)
    assert len({topic["category"] for topic in TOPICS}) >= 12
    assert len({topic["question"] for topic in TOPICS}) == len(TOPICS)
    for topic in TOPICS:
        for key in ("title", "category", "concept", "mechanism", "example", "fields", "experiment", "question", "explanation", "related", "sources"):
            assert topic[key], (topic["id"], key)
        assert len(topic["options"]) == 3
        assert len(set(topic["options"])) == 3
        assert 0 <= topic["answer"] < 3
        assert all(link in ids and link != topic["id"] for link in topic["related"])
        assert all(source.startswith("https://") for source in topic["sources"])


def test_search_concept_and_category():
    assert get_topic("arp")["title"] == "ARP 请求与响应"
    assert get_topic("missing") is None
    assert "arp" in {topic["id"] for topic in search_topics("ARP")}
    assert "quic" in {topic["id"] for topic in search_topics("QUIC UDP")}
    assert all(topic["category"] == "操作系统" for topic in search_topics("", "操作系统"))
    assert not search_topics("不存在的字符串 xxxxxxxxxxx")


def test_all_integrated_guides_link_to_real_lessons_and_modes():
    assert set(GUIDES) == set("ABCDEF")
    for guide in GUIDES.values():
        assert guide["goal"] and len(guide["steps"]) >= 4
        assert all(get_topic(topic_id) for topic_id in guide["topics"])
    assert set(LEARNING_MODES) == {"free", "guided", "challenge"}


def test_transport_security_qualifications_and_answers_rotate():
    assert "不能" in get_topic("transport_compare")["options"][get_topic("transport_compare")["answer"]]
    assert "不保证" in get_topic("stun")["options"][get_topic("stun")["answer"]]
    assert {topic["answer"] for topic in TOPICS} == {0, 1, 2}
