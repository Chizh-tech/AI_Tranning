"""Tests for the Tolerance Analysis Flask application."""
import math
import pytest
from app import app as flask_app, _validate_dimensions


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ── Validation helper ──────────────────────────────────────────────────────

def test_validate_empty():
    assert _validate_dimensions([]) is not None


def test_validate_missing_name():
    err = _validate_dimensions([{"name": "", "tolerance": 0.1, "distribution": "normal", "sigma": 3}])
    assert err is not None


def test_validate_bad_tolerance():
    err = _validate_dimensions([{"name": "X", "tolerance": -1, "distribution": "normal", "sigma": 3}])
    assert err is not None


def test_validate_bad_distribution():
    err = _validate_dimensions([{"name": "X", "tolerance": 0.1, "distribution": "banana"}])
    assert err is not None


def test_validate_bad_sigma():
    err = _validate_dimensions([{"name": "X", "tolerance": 0.1, "distribution": "normal", "sigma": -1}])
    assert err is not None


def test_validate_valid_normal():
    assert _validate_dimensions(
        [{"name": "A", "tolerance": 0.05, "distribution": "normal", "sigma": 3}]
    ) is None


def test_validate_valid_uniform():
    assert _validate_dimensions(
        [{"name": "A", "tolerance": 0.05, "distribution": "uniform"}]
    ) is None


# ── Home page ──────────────────────────────────────────────────────────────

def test_home(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Tolerance Analysis" in resp.data


# ── API error cases ────────────────────────────────────────────────────────

def test_api_no_body(client):
    resp = client.post("/api/calculate", data="not json",
                       content_type="application/json")
    assert resp.status_code == 400


def test_api_empty_dimensions(client):
    resp = client.post("/api/calculate", json={"dimensions": []})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_api_bad_result_sigma(client):
    resp = client.post("/api/calculate", json={
        "dimensions": [{"name": "A", "tolerance": 0.1, "distribution": "normal", "sigma": 3}],
        "result_sigma": -1,
    })
    assert resp.status_code == 400


# ── Worst Case calculation ─────────────────────────────────────────────────

def test_worst_case_simple(client):
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "A", "tolerance": 0.1, "distribution": "normal", "sigma": 3},
            {"name": "B", "tolerance": 0.2, "distribution": "normal", "sigma": 3},
        ],
        "result_sigma": 3,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert math.isclose(data["worst_case"]["plus"], 0.3, rel_tol=1e-9)
    assert math.isclose(data["worst_case"]["minus"], -0.3, rel_tol=1e-9)


def test_worst_case_symmetric(client):
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "X", "tolerance": 0.05, "distribution": "uniform"},
        ],
    })
    data = resp.get_json()
    assert data["worst_case"]["plus"] == -data["worst_case"]["minus"]


# ── RSS calculation ────────────────────────────────────────────────────────

def test_rss_normal_single(client):
    """Single normal dimension: RSS should equal the tolerance itself."""
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "A", "tolerance": 0.06, "distribution": "normal", "sigma": 3},
        ],
        "result_sigma": 3,
    })
    data = resp.get_json()
    # variance = (0.06/3)^2 = 0.0004; rss = sqrt(0.0004)*3 = 0.06
    assert math.isclose(data["rss"]["plus"], 0.06, rel_tol=1e-9)


def test_rss_two_equal_normal(client):
    """Two equal normal dims: RSS should be tolerance * sqrt(2)."""
    tol = 0.1
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "A", "tolerance": tol, "distribution": "normal", "sigma": 3},
            {"name": "B", "tolerance": tol, "distribution": "normal", "sigma": 3},
        ],
        "result_sigma": 3,
    })
    data = resp.get_json()
    expected = tol * math.sqrt(2)
    assert math.isclose(data["rss"]["plus"], expected, rel_tol=1e-5)


def test_rss_uniform(client):
    """Single uniform dimension: variance = t^2/3; rss = sqrt(t^2/3)*3 = t*sqrt(3)."""
    tol = 0.1
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "A", "tolerance": tol, "distribution": "uniform"},
        ],
        "result_sigma": 3,
    })
    data = resp.get_json()
    expected = tol * math.sqrt(3)
    assert math.isclose(data["rss"]["plus"], expected, rel_tol=1e-5)


def test_rss_always_le_worst_case(client):
    """RSS tolerance must be ≤ Worst Case for any valid input."""
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "A", "tolerance": 0.05, "distribution": "normal", "sigma": 3},
            {"name": "B", "tolerance": 0.08, "distribution": "normal", "sigma": 3},
            {"name": "C", "tolerance": 0.03, "distribution": "uniform"},
        ],
        "result_sigma": 3,
    })
    data = resp.get_json()
    assert data["rss"]["plus"] <= data["worst_case"]["plus"]


# ── Contribution percentages ───────────────────────────────────────────────

def test_contributions_sum_to_100(client):
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "A", "tolerance": 0.05, "distribution": "normal", "sigma": 3},
            {"name": "B", "tolerance": 0.08, "distribution": "normal", "sigma": 3},
            {"name": "C", "tolerance": 0.03, "distribution": "uniform"},
        ],
    })
    data = resp.get_json()
    total = sum(d["contribution_pct"] for d in data["dimensions"])
    assert math.isclose(total, 100.0, abs_tol=0.1)


# ── Distribution points ────────────────────────────────────────────────────

def test_distribution_points_length(client):
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "A", "tolerance": 0.1, "distribution": "normal", "sigma": 3},
        ],
    })
    pts = resp.get_json()["distribution_points"]
    assert len(pts["x"]) == len(pts["rss"]) == len(pts["worst_case"]) == 200


def test_distribution_points_nonnegative(client):
    resp = client.post("/api/calculate", json={
        "dimensions": [
            {"name": "A", "tolerance": 0.1, "distribution": "normal", "sigma": 3},
        ],
    })
    pts = resp.get_json()["distribution_points"]
    assert all(v >= 0 for v in pts["rss"])
    assert all(v >= 0 for v in pts["worst_case"])
