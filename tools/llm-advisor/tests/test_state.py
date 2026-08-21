from advisor.state import diff_proposals

def test_new_proposal_is_reported():
    prev = {"proposals": []}
    cur = [{"agent": "VP Engineering", "to_model": "qwen3-coder-30b-mlx"}]
    new = diff_proposals(prev, cur)
    assert len(new) == 1

def test_known_proposal_is_suppressed():
    prev = {"proposals": [{"agent": "VP Engineering", "to_model": "qwen3-coder-30b-mlx", "decision": "pending"}]}
    cur = [{"agent": "VP Engineering", "to_model": "qwen3-coder-30b-mlx"}]
    assert diff_proposals(prev, cur) == []

def test_rejected_proposal_is_never_resurfaced():
    prev = {"proposals": [{"agent": "VP Engineering", "to_model": "qwen3-coder-30b-mlx", "decision": "rejected"}]}
    cur = [{"agent": "VP Engineering", "to_model": "qwen3-coder-30b-mlx"}]
    assert diff_proposals(prev, cur) == []
