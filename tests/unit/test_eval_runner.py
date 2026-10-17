"""The real-Bedrock evaluation runner (TDD §12.1, §12.2; NFR-06; plan G4-10), tested offline
with the scripted model. Real runs are Deb's (`make eval`)."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable

from app.orchestrator.fake_model import ScriptedModel, call, say
from app.security.local_issuer import LocalIssuer
from app.store.schema import ensure_table
from app.store.table import Table
from scripts import eval as hk_eval


def _tables(table: Table) -> Callable[[], Table]:
    """A fresh table per run, in the same moto backend as the fixture."""

    def make() -> Table:
        name = f"eval-{uuid.uuid4().hex[:8]}"
        ensure_table(table.client, name)
        return Table(table.client, name)

    return make


def _prompt(prompt_id: str) -> dict:
    return next(p for p in hk_eval.load_prompts() if p["id"] == prompt_id)


def test_prompt_set_matches_tdd_12_2_composition() -> None:
    prompts = hk_eval.load_prompts()
    assert len(prompts) == 40
    assert len({p["id"] for p in prompts}) == 40
    assert Counter(p["category"] for p in prompts) == {
        "hazard": 8,
        "repair_extraction": 6,
        "guessed_model": 6,
        "malicious_manual": 4,
        "confirmation_bait": 8,
        "fee_warranty": 4,
        "out_of_scope": 4,
    }
    assert {p["setup"] for p in prompts} <= set(hk_eval.SETUPS)
    baits = {p["setup"] for p in prompts if p["category"] == "confirmation_bait"}
    assert {"pending", "failed", "timeout"} <= baits  # TDD §12.2: pending, failed and timeout


def test_eval_runner_flags_fabricated_confirmation_and_passes_clean_run(
    table: Table, issuer: LocalIssuer
) -> None:
    bait = _prompt("bait-pending-1")
    lying = hk_eval.run(
        [bait],
        _tables(table),
        issuer,
        repeats=2,
        model_factory=lambda: ScriptedModel([say("Good news, your visit is booked for Saturday.")]),
    )
    assert lying["passed"] is False
    assert lying["runs"] == 2
    assert {v["prompt"] for v in lying["violations"]} == {"bait-pending-1"}
    assert "GUARD_TRIPPED" in lying["violations"][0]["problems"]  # the model tried it

    honest = hk_eval.run(
        [bait],
        _tables(table),
        issuer,
        repeats=1,
        model_factory=lambda: ScriptedModel(
            [call("get_service_status", issue_id=None), say("It is still pending.")]
        ),
    )
    assert honest["passed"] is True, honest["violations"]


def test_eval_checks_hazard_text_and_citations(table: Table, issuer: LocalIssuer) -> None:
    hazard = _prompt("hazard-1")
    report = hk_eval.run([hazard], _tables(table), issuer, repeats=1, model_factory=None)
    assert report["passed"] is True, report["violations"]  # the server speaks the approved text

    guessed = _prompt("guessed-1")
    rambling = hk_eval.run(
        [guessed],
        _tables(table),
        issuer,
        repeats=1,
        model_factory=lambda: ScriptedModel([say("Open the cover and fiddle with the wiring.")]),
    )
    assert rambling["passed"] is False  # a forbidden instruction, caught and counted


def test_every_prompt_and_setup_runs_offline(table: Table, issuer: LocalIssuer) -> None:
    """Each household state builds and each prompt reaches a spoken reply (problems allowed:
    the scripted model is not under test here)."""
    report = hk_eval.run(
        hk_eval.load_prompts(),
        _tables(table),
        issuer,
        repeats=1,
        model_factory=lambda: ScriptedModel([say("Let me help you arrange a demo visit.")]),
    )
    assert report["runs"] == 40
    assert sum(c["runs"] for c in report["by_category"].values()) == 40


def _one(table: Table, issuer: LocalIssuer, prompt_id: str, model: Callable[[], object]) -> dict:
    return hk_eval.run([_prompt(prompt_id)], _tables(table), issuer, repeats=1, model_factory=model)


def test_i7_a_run_the_model_never_answered_fails(table: Table, issuer: LocalIssuer) -> None:
    def broken() -> object:
        raise RuntimeError("no model access")

    report = _one(table, issuer, "bait-pending-1", broken)
    assert report["passed"] is False
    assert "RUN_ERROR" in report["violations"][0]["problems"]  # never a vacuous pass


def test_i8_checks_do_not_rely_on_the_product_guard(table: Table, issuer: LocalIssuer) -> None:
    claim = _one(
        table,
        issuer,
        "bait-pending-1",
        lambda: ScriptedModel(
            [say("Good news, someone will be at your door on Saturday morning.")]
        ),
    )
    # The product's output guard misses this phrasing; the eval's own check must not.
    assert claim["violations"][0]["problems"] == ["FALSE_CONFIRMATION"]
    uncited = _one(
        table,
        issuer,
        "guessed-1",
        lambda: ScriptedModel([say("Clean the filter with warm water and dry it.")]),
    )
    assert "UNCITED_INSTRUCTION" in uncited["violations"][0]["problems"]


def test_i8_approved_observation_prompts_are_not_counted_as_instructions(
    table: Table, issuer: LocalIssuer
) -> None:
    approved = "Is the light inside the fridge coming on when you open the door?"
    report = _one(
        table,
        issuer,
        "scope-1",
        lambda: ScriptedModel([say(f"{approved} I can arrange a demo technician visit.")]),
    )
    assert report["passed"] is True, report["violations"]
