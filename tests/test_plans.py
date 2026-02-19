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
    param_set_to_typed,
    update_parameter_set,
    update_plan_name,
)
from vibe_carlo.schemas import (
    FlatDistribution,
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


def _make_param_set_kwargs(
    name: str = "Phase 1",
    duration: int | None = 5,
    cash: float = 100000,
    market: float = 500000,
    bonds: float = 50000,
    earnings: float = 60000,
    spending: FlatDistribution | UniformDistribution | TruncatedNormalDistribution | None = None,
    filing_status: str | None = None,
) -> dict[str, object]:
    dist = spending or FlatDistribution(value=40000)
    return {
        "name": name,
        "duration": duration,
        "cash_value": cash,
        "market_value": market,
        "bond_value": bonds,
        "earnings": earnings,
        "spending_distribution": dist,
        "filing_status": filing_status,
    }


# --- Plan happy path ---


def test_create_and_get_plan(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "My Retirement Plan")
    plan = get_plan(conn, plan_id, user_id)
    conn.close()

    assert plan is not None
    assert plan["name"] == "My Retirement Plan"
    assert plan["user_id"] == user_id


def test_list_plans_with_count(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Test Plan")
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("Phase 1"))  # type: ignore[arg-type]
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("Phase 2"))  # type: ignore[arg-type]
    plans = list_plans(conn, user_id)
    conn.close()

    assert len(plans) == 1
    assert plans[0]["parameter_set_count"] == 2


def test_update_plan_name(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Original")
    result = update_plan_name(conn, plan_id, user_id, "Updated")
    plan = get_plan(conn, plan_id, user_id)
    conn.close()

    assert result is True
    assert plan is not None
    assert plan["name"] == "Updated"


def test_delete_plan_cascades(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "To Delete")
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs())  # type: ignore[arg-type]
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
    ps_id = create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs())  # type: ignore[arg-type]
    raw = get_parameter_set(conn, ps_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert raw is not None
    assert raw["name"] == "Phase 1"
    assert raw["duration"] == 5
    assert raw["cash_value"] == 100000
    assert raw["market_value"] == 500000
    assert raw["bond_value"] == 50000
    assert raw["earnings"] == 60000
    assert '"dist_type": "flat"' in str(raw["spending_distribution"])


def test_list_parameter_sets_ordered(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("First"))  # type: ignore[arg-type]
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("Second"))  # type: ignore[arg-type]
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("Third"))  # type: ignore[arg-type]
    params = list_parameter_sets(conn, plan_id, user_id)
    conn.close()

    assert len(params) == 3
    assert params[0]["name"] == "First"
    assert params[1]["name"] == "Second"
    assert params[2]["name"] == "Third"
    assert (
        int(str(params[0]["order_position"]))
        < int(str(params[1]["order_position"]))
        < int(str(params[2]["order_position"]))
    )


def test_update_parameter_set(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    ps_id = create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs())  # type: ignore[arg-type]
    result = update_parameter_set(
        conn,
        ps_id,  # type: ignore[arg-type]
        user_id,
        name="Updated Phase",
        duration=10,
        cash_value=200000,
        market_value=600000,
        bond_value=100000,
        earnings=80000,
        spending_distribution=FlatDistribution(value=50000),
        filing_status="single",
    )
    raw = get_parameter_set(conn, ps_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert result is True
    assert raw is not None
    assert raw["name"] == "Updated Phase"
    assert raw["duration"] == 10
    assert raw["cash_value"] == 200000


def test_delete_parameter_set(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    ps_id = create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs())  # type: ignore[arg-type]
    result = delete_parameter_set(conn, ps_id, user_id)  # type: ignore[arg-type]
    raw = get_parameter_set(conn, ps_id, user_id)  # type: ignore[arg-type]
    conn.close()

    assert result is True
    assert raw is None


def test_move_parameter_set_up(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("First"))  # type: ignore[arg-type]
    ps2_id = create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("Second"))  # type: ignore[arg-type]

    result = move_parameter_set(conn, ps2_id, user_id, "up")  # type: ignore[arg-type]
    params = list_parameter_sets(conn, plan_id, user_id)
    conn.close()

    assert result is True
    assert params[0]["name"] == "Second"
    assert params[1]["name"] == "First"


def test_move_parameter_set_down(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    ps1_id = create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("First"))  # type: ignore[arg-type]
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("Second"))  # type: ignore[arg-type]

    result = move_parameter_set(conn, ps1_id, user_id, "down")  # type: ignore[arg-type]
    params = list_parameter_sets(conn, plan_id, user_id)
    conn.close()

    assert result is True
    assert params[0]["name"] == "Second"
    assert params[1]["name"] == "First"


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
    ps1_id = create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("First"))  # type: ignore[arg-type]
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("Second"))  # type: ignore[arg-type]

    result = move_parameter_set(conn, ps1_id, user_id, "up")  # type: ignore[arg-type]
    conn.close()
    assert result is False


def test_move_last_down_noop(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Plan")
    create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("First"))  # type: ignore[arg-type]
    ps2_id = create_parameter_set(conn, plan_id, user_id, **_make_param_set_kwargs("Second"))  # type: ignore[arg-type]

    result = move_parameter_set(conn, ps2_id, user_id, "down")  # type: ignore[arg-type]
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
    ps_id = create_parameter_set(conn, plan_id, user_b_id, **_make_param_set_kwargs())  # type: ignore[arg-type]
    assert ps_id is None

    conn.close()


def test_parameter_set_all_distribution_types(db: tuple[Path, int]) -> None:
    db_path, user_id = db
    conn = get_connection(db_path)
    plan_id = create_plan(conn, user_id, "Dist Test")

    # Flat
    ps1 = create_parameter_set(
        conn,
        plan_id,
        user_id,
        **_make_param_set_kwargs(name="Flat", spending=FlatDistribution(value=50000)),  # type: ignore[arg-type]
    )
    raw1 = get_parameter_set(conn, ps1, user_id)  # type: ignore[arg-type]
    typed1 = param_set_to_typed(raw1)  # type: ignore[arg-type]
    dist1 = typed1["spending_distribution"]
    assert hasattr(dist1, "dist_type") and dist1.dist_type == "flat"
    # Uniform
    ps2 = create_parameter_set(
        conn,
        plan_id,
        user_id,
        **_make_param_set_kwargs(
            name="Uniform", spending=UniformDistribution(low=30000, high=60000)
        ),  # type: ignore[arg-type]
    )
    raw2 = get_parameter_set(conn, ps2, user_id)  # type: ignore[arg-type]
    typed2 = param_set_to_typed(raw2)  # type: ignore[arg-type]
    dist2 = typed2["spending_distribution"]
    assert hasattr(dist2, "dist_type") and dist2.dist_type == "uniform"
    # Truncated normal
    ps3 = create_parameter_set(
        conn,
        plan_id,
        user_id,
        **_make_param_set_kwargs(
            name="Normal",
            spending=TruncatedNormalDistribution(low=20000, high=80000, mean=50000, stddev=10000),
        ),  # type: ignore[arg-type]
    )
    raw3 = get_parameter_set(conn, ps3, user_id)  # type: ignore[arg-type]
    typed3 = param_set_to_typed(raw3)  # type: ignore[arg-type]
    dist3 = typed3["spending_distribution"]
    assert hasattr(dist3, "dist_type") and dist3.dist_type == "truncated_normal"
    conn.close()
