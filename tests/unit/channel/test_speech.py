from __future__ import annotations

from app.channel import templates
from app.channel.pipeline import speak_agent_outcome
from app.orchestrator.agent import ToolCall, TurnOutcome


def _guidance(speech: str) -> ToolCall:
    data = {
        "step": {"step_id": "s1", "speech": speech, "helper_only": False},
        "evidence": {"document_id": "d", "locator": "l", "catalog_item": "c", "version": "v"},
    }
    return ToolCall("get_guidance", {"issue_id": "i1"}, {"status": "OK", "data": data})


def test_follow_up_only_after_steps_without_a_question() -> None:
    plain = speak_agent_outcome(TurnOutcome("", [_guidance("Please press Mode.")]))
    assert plain[0] == f"Please press Mode. {templates.GUIDANCE_FOLLOW_UP}"
    asking = speak_agent_outcome(
        TurnOutcome("", [_guidance("Shall I arrange a demo technician visit?")])
    )
    assert asking[0] == "Shall I arrange a demo technician visit?"


def test_scope_limit_text_is_spoken_for_fridge_and_tv() -> None:
    refusal = {
        "status": "ERROR",
        "error": {
            "code": "NO_APPROVED_GUIDANCE",
            "reason": "SCOPE_LIMIT",
            "message": "generic",
            "details": {
                "scope_limit": "I can't give checks for TVs yet.",
                "generic_prompts": ["Does the small light come on?"],
            },
        },
    }
    speech = speak_agent_outcome(TurnOutcome("ignored", [ToolCall("get_guidance", {}, refusal)]))[0]
    assert speech == "I can't give checks for TVs yet. Does the small light come on?"


def test_model_thinking_tags_are_never_spoken_or_guarded() -> None:
    # Amazon Nova Pro on AWS (23 Oct) put its reasoning in <thinking> tags in the reply text.
    spoken = speak_agent_outcome(
        TurnOutcome(
            text="<thinking> The TV was not found. I need to ask. </thinking> Which TV is it?"
        )
    )
    assert spoken[0] == "Which TV is it?"
    # The guard judges what is said: words that exist only inside the reasoning are not spoken.
    reasoning_only = TurnOutcome(
        text="<thinking>Do not tell them to use a screwdriver.</thinking> Okay."
    )
    assert speak_agent_outcome(reasoning_only)[:3] == ("Okay.", None, False)
    # Several blocks, any case, and an unclosed block that runs to the end are all dropped.
    mixed = TurnOutcome(
        text="<Thinking>a</Thinking>Hello. <thinking>b</thinking>What is wrong?<thinking>c"
    )
    assert speak_agent_outcome(mixed)[0] == "Hello. What is wrong?"
    # Reasoning and nothing else is an empty reply.
    assert speak_agent_outcome(TurnOutcome(text="<thinking>only this</thinking>"))[0] == (
        templates.TURN_ERROR
    )
