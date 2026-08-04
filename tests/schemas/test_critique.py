from app.schemas.critique import CritiqueOutput


def test_critique_normalizes_percentage_scores_from_local_models() -> None:
    critique = CritiqueOutput.model_validate({
        "overall_score": 85,
        "decision": "accept_with_warnings",
        "summary": "Production ready with minor warnings.",
        "panel_critiques": [{
            "panel_id": "p1_panel_1", "score": 90, "strengths": ["Continuity"],
            "issues": [], "correction": None,
        }],
        "regeneration_instructions": [],
        "lora_training": {
            "eligible": True, "reason": "Complete metadata", "caption_tags": ["manga"],
            "quality_score": 85, "required_metadata": ["checkpoint"],
        },
    })

    assert critique.overall_score == 8.5
    assert critique.panel_critiques[0].score == 9.0
    assert critique.lora_training.quality_score == 8.5
