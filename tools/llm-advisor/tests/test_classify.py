from advisor.classify import capability_class

def test_coding_role_maps_to_coding():
    assert capability_class("VP Engineering", "qwen2.5-coder-14b-instruct-mlx") == "coding"

def test_research_role_maps_to_reasoning():
    assert capability_class("Online-Rechercheur", "qwen3.6-35b-a3b-mlx") == "reasoning"

def test_classifier_model_maps_to_classification():
    assert capability_class("Sekretärin", "qwen2.5-0.5b-instruct-mlx@4bit") == "classification"

def test_unknown_defaults_to_general():
    assert capability_class("Irgendwas", "gemma-4-31b-it-mlx") == "general"
