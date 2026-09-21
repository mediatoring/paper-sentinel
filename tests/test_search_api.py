from app.main import _rrf


def test_rrf_merges_and_orders():
    text = [{"arxiv_id": "a", "snippet": "x"}, {"arxiv_id": "b", "snippet": "y"}]
    semantic = [{"arxiv_id": "b", "similarity": 0.9}, {"arxiv_id": "c", "similarity": 0.8}]
    fused = _rrf(text, semantic)
    assert [f["arxiv_id"] for f in fused] == ["b", "a", "c"]
    assert fused[0]["snippet"] == "y" and fused[0]["similarity"] == 0.9
    assert fused[0]["fusion_score"] > fused[1]["fusion_score"]
