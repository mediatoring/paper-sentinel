from app.services.arxiv import parse_feed

API_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2509.00001v1</id>
    <updated>2026-09-18T10:00:00Z</updated>
    <published>2026-09-18T10:00:00Z</published>
    <title>Agents that   reason</title>
    <summary>We study agents.
  They reason.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <link href="http://arxiv.org/abs/2509.00001v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2509.00001v1" rel="related" type="application/pdf"/>
    <category term="cs.AI"/><category term="cs.LG"/>
  </entry>
</feed>"""

RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <entry>
    <id>oai:arXiv.org:2509.00002v1</id>
    <title>Retrieval for long context</title>
    <link href="https://arxiv.org/abs/2509.00002v1" rel="alternate"/>
    <summary>arXiv:2509.00002v1 Announce Type: new
Abstract: We retrieve things. It works.</summary>
    <dc:creator>Grace Hopper, Claude Shannon</dc:creator>
    <category term="cs.CL"/>
    <published>2026-09-18T04:00:00Z</published>
  </entry>
</feed>"""


def test_parse_api_feed():
    papers = parse_feed(API_FEED)
    assert len(papers) == 1
    p = papers[0]
    assert p["arxiv_id"] == "2509.00001v1"
    assert p["title"] == "Agents that reason"
    assert p["abstract"] == "We study agents. They reason."
    assert p["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert p["categories"] == ["cs.AI", "cs.LG"]
    assert p["pdf_url"] == "http://arxiv.org/pdf/2509.00001v1"


def test_parse_rss_feed():
    papers = parse_feed(RSS_FEED)
    assert len(papers) == 1
    p = papers[0]
    assert p["arxiv_id"] == "2509.00002v1"
    assert p["abstract"] == "We retrieve things. It works."
    assert p["authors"] == ["Grace Hopper", "Claude Shannon"]
    assert p["abs_url"] == "https://arxiv.org/abs/2509.00002v1"
    assert p["pdf_url"] == "https://arxiv.org/pdf/2509.00002v1"


def test_parse_empty_feed():
    assert parse_feed("<feed xmlns='http://www.w3.org/2005/Atom'></feed>") == []
