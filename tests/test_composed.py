"""Wiring checks for the composed example queries and the agent-task graders.

The rows each composed query returns are pinned in ``test/sql/composed.test``
(run through a real ATTACH); these tests check where the queries are published.
"""

from __future__ import annotations

import json
import pathlib
import re

from vgi_calendar import worker
from vgi_calendar.composed import COMPOSED_EXAMPLES, ComposedExample

_REPO = pathlib.Path(__file__).resolve().parent.parent


def _norm(sql: str) -> str:
    """Whitespace/case-insensitive SQL with column aliases removed (near-verbatim match)."""
    flat = " ".join(sql.split()).lower().rstrip(";")
    return re.sub(r" as [a-z_][a-z0-9_]*(?=[ ,]|$)", "", flat)


def _published_sql() -> set[str]:
    """Every SQL string published in any vgi.example_queries / executable list."""
    out = {_norm(e["sql"]) for e in json.loads(worker._SCHEMA_EXAMPLE_QUERIES)}
    out |= {_norm(e["sql"]) for e in json.loads(worker._EXECUTABLE_EXAMPLES)}
    for examples in worker._EXAMPLES_BY_NAME.values():
        out |= {_norm(e["sql"]) for e in examples}
    return out


def _graders() -> dict[str, str]:
    """Parse the flat ``vgi-agent-tests.yaml`` (name + double-quoted reference_sql)."""
    out: dict[str, str] = {}
    name = None
    for line in (_REPO / "vgi-agent-tests.yaml").read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            name = stripped.removeprefix("- name:").strip()
        elif stripped.startswith("reference_sql:") and name:
            out[name] = json.loads(stripped.removeprefix("reference_sql:").strip())
    return out


def test_every_composed_example_is_in_the_schema_list() -> None:
    schema = json.loads(worker._SCHEMA_EXAMPLE_QUERIES)
    for ex in COMPOSED_EXAMPLES:
        assert ex.as_example() in schema, ex.name


def test_composed_examples_are_within_the_first_five_of_each_object() -> None:
    for ex in COMPOSED_EXAMPLES:
        assert ex.attach_to, ex.name
        for name in ex.attach_to:
            assert ex.as_example() in worker._EXAMPLES_BY_NAME[name][:5], (ex.name, name)


def test_composed_examples_combine_two_distinct_objects_mostly() -> None:
    names = set(worker._EXAMPLES_BY_NAME)

    def objects(ex: ComposedExample) -> set[str]:
        return {n for n in names if f"cal.main.{n}(" in ex.sql}

    multi = [ex for ex in COMPOSED_EXAMPLES if len(objects(ex)) >= 2]
    assert len(multi) >= len(COMPOSED_EXAMPLES) - 1


def test_no_duplicate_examples_in_any_list() -> None:
    lists = [json.loads(worker._SCHEMA_EXAMPLE_QUERIES), *worker._EXAMPLES_BY_NAME.values()]
    for examples in lists:
        keys = [_norm(e["sql"]) for e in examples]
        assert len(keys) == len(set(keys))


def test_every_example_has_a_description() -> None:
    for examples in [json.loads(worker._SCHEMA_EXAMPLE_QUERIES), *worker._EXAMPLES_BY_NAME.values()]:
        assert all(e["description"].strip() for e in examples)


def test_schema_example_list_fits_vgi417() -> None:
    assert len(worker._SCHEMA_EXAMPLE_QUERIES) <= 8000


def test_agent_tasks_and_graders_match() -> None:
    tasks = {t["name"] for t in json.loads(worker._AGENT_TEST_TASKS)}
    assert tasks == set(_graders())


def test_grader_answers_are_not_published() -> None:
    # An agent must not be able to copy a grader's answer from catalog metadata.
    published = _published_sql()
    for name, sql in _graders().items():
        assert _norm(sql) not in published, name
