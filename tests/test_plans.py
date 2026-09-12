"""CRUD unit tests for plan operations."""

from pathlib import Path

import pytest

from vibe_carlo.auth import create_user
from vibe_carlo.db import get_connection, init_db
from vibe_carlo.plans import (
    create_parameter_set,
    create_plan,
    delete_parameter_set,
    delete_plan,
    get_parameter_set,
    get_plan,
    list_parameter_sets,
    list_plans,
    move_parameter_set,
    update_parameter_set,
    update_plan_name,
)
from vibe_carlo.schemas import (
    FlatDistribution,
    ParamSetSpec,
    SpendingDistribution,
    TruncatedNormalDistribution,
    UniformDistribution,
)


@pytest.fixture()
def db(tmp_path: Path) -> tuple[Path, int]:
    """Create a temporary SQLite database with a test user, return (path, user_id)."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)
    user_id = create_user(conn, "test@example.com", "password123")
    conn.close()
    return db_path, user_id


def _make_spec(
    name: str = "Phase 1",
    duration: int | None = 5,
    cash: float = 100000,
    market: float = 500000,
    bonds: float = 50000,
    earnings: float = 60000,
    spending: SpendingDistribution | None = None,
    withdrawal_tax_rate: float = 0.0,
) -> ParamSetSpec:
    return ParamSetSpec(
        name=name,
        duration=duration,
        cash_value=cash,
        market_value=market,
        bond_value=bonds,
        earnings=earnings,
        spending_distribution=spending or FlatDistribution(value=40000),
        withdrawal_tax_rate=withdrawal_tax_rate,
    )


# --- Plan happy path ---


def test_create_and_get_plan(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "My Retirement Plan")
    plan = get_plan(conn, plan_id, user_id)
    conn.close()

    assert plan is not None
    assert plan.name == "My Retirement Plan"
    assert plan.user_id == user_id


def test_list_plans_with_count(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Test Plan")
    create_parameter_set(conn, plan_id, user_id, _make_spec("Phase 1"))
    create_parameter_set(conn, plan_id, user_id, _make_spec("Phase 2"))
    plans = list_plans(conn, user_id)
    conn.close()

    assert len(plans) == 1
    assert plans[0].parameter_set_count == 2


def test_update_plan_name(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Original")
    result = update_plan_name(conn, plan_id, user_id, "Updated")
    plan = get_plan(conn, plan_id, user_id)
    conn.close()

    assert result is True
    assert plan is not None
    assert plan.name == "Updated"


def test_delete_plan_cascades(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "To Delete")
    create_parameter_set(conn, plan_id, user_id, _make_spec())
    result = delete_plan(conn, plan_id, user_id)
    plan = get_plan(conn, plan_id, user_id)
    params = list_parameter_sets(conn, plan_id, user_id)
    conn.close()

    assert result is True
    assert plan is None
    assert len(params) == 0


# --- Parameter set happy path ---


def test_create_parameter_set(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    ps_id = create_parameter_set(conn, plan_id, user_id, _make_spec())
    assert ps_id is not None
    ps = get_parameter_set(conn, ps_id, user_id)
    conn.close()

    assert ps is not None
    assert ps.name == "Phase 1"
    assert ps.duration == 5
    assert ps.cash_value == 100000
    assert ps.market_value == 500000
    assert ps.bond_value == 50000
    assert ps.earnings == 60000
    assert ps.spending_distribution.dist_type == "flat"


def test_list_parameter_sets_ordered(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    create_parameter_set(conn, plan_id, user_id, _make_spec("First"))
    create_parameter_set(conn, plan_id, user_id, _make_spec("Second"))
    create_parameter_set(conn, plan_id, user_id, _make_spec("Third"))
    params = list_parameter_sets(conn, plan_id, user_id)
    conn.close()

    assert len(params) == 3
    assert params[0].name == "First"
    assert params[1].name == "Second"
    assert params[2].name == "Third"
    assert params[0].order_position < params[1].order_position < params[2].order_position


def test_update_parameter_set(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    ps_id = create_parameter_set(conn, plan_id, user_id, _make_spec())
    assert ps_id is not None
    result = update_parameter_set(
        conn,
        ps_id,
        user_id,
        ParamSetSpec(
            name="Updated Phase",
            duration=10,
            cash_value=200000,
            market_value=600000,
            bond_value=100000,
            earnings=80000,
            spending_distribution=FlatDistribution(value=50000),
            withdrawal_tax_rate=0.22,
        ),
    )
    ps = get_parameter_set(conn, ps_id, user_id)
    conn.close()

    assert result is True
    assert ps is not None
    assert ps.name == "Updated Phase"
    assert ps.duration == 10
    assert ps.cash_value == 200000


def test_delete_parameter_set(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    ps_id = create_parameter_set(conn, plan_id, user_id, _make_spec())
    assert ps_id is not None
    result = delete_parameter_set(conn, ps_id, user_id)
    ps = get_parameter_set(conn, ps_id, user_id)
    conn.close()

    assert result is True
    assert ps is None


def test_move_parameter_set_up(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    create_parameter_set(conn, plan_id, user_id, _make_spec("First"))
    ps2_id = create_parameter_set(conn, plan_id, user_id, _make_spec("Second"))
    assert ps2_id is not None

    result = move_parameter_set(conn, ps2_id, user_id, "up")
    params = list_parameter_sets(conn, plan_id, user_id)
    conn.close()

    assert result is True
    assert params[0].name == "Second"
    assert params[1].name == "First"


def test_move_parameter_set_down(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    ps1_id = create_parameter_set(conn, plan_id, user_id, _make_spec("First"))
    create_parameter_set(conn, plan_id, user_id, _make_spec("Second"))
    assert ps1_id is not None

    result = move_parameter_set(conn, ps1_id, user_id, "down")
    params = list_parameter_sets(conn, plan_id, user_id)
    conn.close()

    assert result is True
    assert params[0].name == "Second"
    assert params[1].name == "First"


# --- Edge cases ---


def test_get_nonexistent_plan(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan = get_plan(conn, 999, user_id)
    conn.close()
    assert plan is None


def test_delete_nonexistent_plan(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    result = delete_plan(conn, 999, user_id)
    conn.close()
    assert result is False


def test_move_first_up_noop(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    ps1_id = create_parameter_set(conn, plan_id, user_id, _make_spec("First"))
    create_parameter_set(conn, plan_id, user_id, _make_spec("Second"))
    assert ps1_id is not None

    result = move_parameter_set(conn, ps1_id, user_id, "up")
    conn.close()
    assert result is False


def test_move_last_down_noop(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    create_parameter_set(conn, plan_id, user_id, _make_spec("First"))
    ps2_id = create_parameter_set(conn, plan_id, user_id, _make_spec("Second"))
    assert ps2_id is not None

    result = move_parameter_set(conn, ps2_id, user_id, "down")
    conn.close()
    assert result is False


def test_cross_user_isolation(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    user_b_id = create_user(conn, "other@example.com", "password456")
    plan_id = create_plan(conn, user_id, "User A Plan")

    # User B cannot see User A's plan
    assert get_plan(conn, plan_id, user_b_id) is None
    assert list_plans(conn, user_b_id) == []
    assert delete_plan(conn, plan_id, user_b_id) is False
    assert update_plan_name(conn, plan_id, user_b_id, "Hacked") is False

    # User B cannot create parameter sets on User A's plan
    ps_id = create_parameter_set(conn, plan_id, user_b_id, _make_spec())
    assert ps_id is None

    conn.close()


def test_parameter_set_all_distribution_types(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Dist Test")

    # Flat
    ps1 = create_parameter_set(
        conn, plan_id, user_id, _make_spec(name="Flat", spending=FlatDistribution(value=50000))
    )
    assert ps1 is not None
    got1 = get_parameter_set(conn, ps1, user_id)
    assert got1 is not None
    assert got1.spending_distribution.dist_type == "flat"

    # Uniform
    ps2 = create_parameter_set(
        conn,
        plan_id,
        user_id,
        _make_spec(name="Uniform", spending=UniformDistribution(low=30000, high=60000)),
    )
    assert ps2 is not None
    got2 = get_parameter_set(conn, ps2, user_id)
    assert got2 is not None
    assert got2.spending_distribution.dist_type == "uniform"

    # Truncated normal
    ps3 = create_parameter_set(
        conn,
        plan_id,
        user_id,
        _make_spec(
            name="Normal",
            spending=TruncatedNormalDistribution(low=20000, high=80000, mean=50000, stddev=10000),
        ),
    )
    assert ps3 is not None
    got3 = get_parameter_set(conn, ps3, user_id)
    assert got3 is not None
    assert got3.spending_distribution.dist_type == "truncated_normal"
    conn.close()
