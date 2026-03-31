import math
import os
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)


def _validate_dimensions(dimensions):
    """Return an error string if dimensions data is invalid, else None."""
    if not isinstance(dimensions, list) or len(dimensions) == 0:
        return "At least one dimension is required."
    for i, dim in enumerate(dimensions):
        label = f"Dimension {i + 1}"
        if not isinstance(dim.get("name"), str) or not dim["name"].strip():
            return f"{label}: name must be a non-empty string."
        try:
            tol = float(dim["tolerance"])
        except (TypeError, ValueError, KeyError):
            return f"{label}: tolerance must be a number."
        if tol <= 0:
            return f"{label}: tolerance must be positive."
        dist = dim.get("distribution", "normal")
        if dist not in ("normal", "uniform"):
            return f"{label}: distribution must be 'normal' or 'uniform'."
        if dist == "normal":
            try:
                sigma = float(dim.get("sigma", 3))
            except (TypeError, ValueError):
                return f"{label}: sigma must be a number."
            if sigma <= 0:
                return f"{label}: sigma must be positive."
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/calculate", methods=["POST"])
def calculate():
    """
    Accepts JSON body:
    {
        "dimensions": [
            {
                "name": "Part A",
                "nominal": 10.0,
                "tolerance": 0.1,
                "distribution": "normal",   // "normal" | "uniform"
                "sigma": 3                  // only used for normal (default 3)
            },
            ...
        ],
        "result_sigma": 3   // target sigma for combined RSS result (default 3)
    }

    Returns:
    {
        "worst_case": { "plus": ..., "minus": ... },
        "rss": { "plus": ..., "minus": ... },
        "dimensions": [ { "name", "tolerance", "variance", "contribution_pct" }, ... ],
        "distribution_points": { "x": [...], "worst_case": [...], "rss": [...] }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400

    dimensions = data.get("dimensions", [])
    error = _validate_dimensions(dimensions)
    if error:
        return jsonify({"error": error}), 400

    try:
        result_sigma = float(data.get("result_sigma", 3))
        if result_sigma <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "result_sigma must be a positive number."}), 400

    # ------------------------------------------------------------------
    # Worst Case
    # ------------------------------------------------------------------
    worst_case_total = sum(float(d["tolerance"]) for d in dimensions)

    # ------------------------------------------------------------------
    # RSS
    # Total variance is the sum of component variances.
    # Normal:  variance_i = (tolerance_i / sigma_i)^2
    # Uniform: tolerance_i is the half-width (±) of the distribution.
    #          For Uniform(-a, +a), variance = a^2 / 3.
    #          With a = tolerance_i: variance_i = tolerance_i^2 / 3
    # Combined RSS tolerance at result_sigma:
    #   rss_tolerance = sqrt(total_variance) * result_sigma
    # ------------------------------------------------------------------
    total_variance = 0.0
    dim_stats = []
    for d in dimensions:
        tol = float(d["tolerance"])
        dist = d.get("distribution", "normal")
        if dist == "normal":
            sigma = float(d.get("sigma", 3))
            variance = (tol / sigma) ** 2
        else:  # uniform
            variance = (tol ** 2) / 3.0
        total_variance += variance
        dim_stats.append(
            {
                "name": d["name"],
                "tolerance": tol,
                "distribution": dist,
                "variance": variance,
            }
        )

    rss_total = math.sqrt(total_variance) * result_sigma

    # Contribution percentages
    for ds in dim_stats:
        ds["contribution_pct"] = (
            round(ds["variance"] / total_variance * 100, 2) if total_variance > 0 else 0
        )

    # ------------------------------------------------------------------
    # Distribution curve points for the chart
    # Generate a Gaussian PDF for the RSS combined output and a uniform
    # distribution scaled to the worst-case span.
    # ------------------------------------------------------------------
    rss_std = math.sqrt(total_variance)
    n_points = 200
    span = max(worst_case_total, rss_total) * 1.5
    step = (2 * span) / (n_points - 1)

    x_points = [-span + i * step for i in range(n_points)]

    def gaussian_pdf(x, std):
        if std == 0:
            return 0.0
        return math.exp(-0.5 * (x / std) ** 2) / (std * math.sqrt(2 * math.pi))

    rss_curve = [gaussian_pdf(x, rss_std) for x in x_points]

    # Worst-case: uniform distribution between [-worst_case_total, +worst_case_total]
    wc_height = 1.0 / (2 * worst_case_total) if worst_case_total > 0 else 0
    wc_curve = [
        wc_height if -worst_case_total <= x <= worst_case_total else 0.0
        for x in x_points
    ]

    return jsonify(
        {
            "worst_case": {
                "plus": round(worst_case_total, 6),
                "minus": round(-worst_case_total, 6),
            },
            "rss": {
                "plus": round(rss_total, 6),
                "minus": round(-rss_total, 6),
            },
            "dimensions": dim_stats,
            "distribution_points": {
                "x": [round(v, 6) for v in x_points],
                "rss": [round(v, 8) for v in rss_curve],
                "worst_case": [round(v, 8) for v in wc_curve],
            },
        }
    )


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
