import os
import io
import csv
from datetime import datetime, timedelta

import pandas as pd
from flask import Flask, render_template, request, jsonify, Response

from database import get_connection, init_db

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

app = Flask(__name__)
init_db()

REQUIRED_COLUMNS = {"order_date", "region", "category", "product", "quantity", "unit_price"}
OPTIONAL_COST_COL = "unit_cost"

NAVY = "#1a2744"
TEAL = "#0d9488"
SLATE = "#64748b"


def build_filters(args):
    clauses = ["1=1"]
    params = []

    if args.get("start_date"):
        clauses.append("order_date >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("order_date <= ?")
        params.append(args["end_date"])
    if args.get("region") and args["region"] != "all":
        clauses.append("region = ?")
        params.append(args["region"])
    if args.get("category") and args["category"] != "all":
        clauses.append("category = ?")
        params.append(args["category"])
    if args.get("product") and args["product"] != "all":
        clauses.append("product = ?")
        params.append(args["product"])

    return " AND ".join(clauses), params


def _parse_df_from_upload(file):
    df = pd.read_csv(file)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
    df["revenue"] = df["quantity"] * df["unit_price"]

    has_cost = OPTIONAL_COST_COL in df.columns
    if has_cost:
        df["unit_cost"] = pd.to_numeric(df["unit_cost"], errors="coerce")
        df["cost"] = df["quantity"] * df["unit_cost"].fillna(0)
        df["profit"] = df["revenue"] - df["cost"]
    else:
        df["unit_cost"] = None
        df["cost"] = None
        df["profit"] = None

    df = df.dropna(subset=["order_date"])
    return df, has_cost


def _insert_df(df, filename, conn):
    cur = conn.cursor()
    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row["order_date"]),
            row.get("region", ""),
            row.get("category", ""),
            row.get("product", ""),
            int(row["quantity"]),
            float(row["unit_price"]),
            float(row["unit_cost"]) if pd.notna(row.get("unit_cost")) else None,
            float(row["revenue"]),
            float(row["cost"]) if pd.notna(row.get("cost")) else None,
            float(row["profit"]) if pd.notna(row.get("profit")) else None,
        ))
    cur.executemany(
        """INSERT INTO sales
           (order_date, region, category, product, quantity, unit_price, unit_cost, revenue, cost, profit)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    cur.execute(
        "INSERT INTO uploads (filename, row_count) VALUES (?, ?)",
        (filename, len(rows)),
    )
    conn.commit()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/upload", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "No file selected."}), 400
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Please upload a .csv file."}), 400
    try:
        df, has_cost = _parse_df_from_upload(file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Could not read CSV: {exc}"}), 400

    conn = get_connection()
    _insert_df(df, file.filename, conn)
    conn.close()
    return jsonify({"message": f"Imported {len(df)} rows from {file.filename}.", "has_cost": has_cost})


@app.route("/api/load-sample", methods=["POST"])
def load_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "sample_data", "sample_data.csv")
    if not os.path.exists(sample_path):
        return jsonify({"error": "Sample data file not found."}), 404
    try:
        df, has_cost = _parse_df_from_upload(sample_path)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    conn = get_connection()
    _insert_df(df, os.path.basename(sample_path), conn)
    conn.close()
    return jsonify({"message": f"Loaded {len(df)} sample rows.", "has_cost": has_cost})


@app.route("/api/reset", methods=["POST"])
def reset_data():
    conn = get_connection()
    conn.execute("DELETE FROM sales")
    conn.execute("DELETE FROM uploads")
    conn.commit()
    conn.close()
    return jsonify({"message": "All data cleared."})


@app.route("/api/filters")
def api_filter_options():
    conn = get_connection()
    regions = [r["region"] for r in conn.execute(
        "SELECT DISTINCT region FROM sales WHERE region != '' ORDER BY region").fetchall()]
    categories = [c["category"] for c in conn.execute(
        "SELECT DISTINCT category FROM sales WHERE category != '' ORDER BY category").fetchall()]
    products = [p["product"] for p in conn.execute(
        "SELECT DISTINCT product FROM sales WHERE product != '' ORDER BY product").fetchall()]
    has_data = conn.execute("SELECT COUNT(*) AS c FROM sales").fetchone()["c"] > 0
    date_range = conn.execute(
        "SELECT MIN(order_date) AS min_date, MAX(order_date) AS max_date FROM sales"
    ).fetchone()
    conn.close()
    return jsonify({
        "regions": regions,
        "categories": categories,
        "products": products,
        "has_data": has_data,
        "min_date": date_range["min_date"] if date_range else None,
        "max_date": date_range["max_date"] if date_range else None,
    })


@app.route("/api/kpis")
def api_kpis():
    where_clause, params = build_filters(request.args)
    conn = get_connection()
    row = conn.execute(f"""
        SELECT
            COALESCE(SUM(revenue), 0) AS total_revenue,
            COALESCE(SUM(quantity), 0) AS total_units,
            COUNT(*) AS total_orders,
            COALESCE(AVG(revenue), 0) AS avg_order_value
        FROM sales WHERE {where_clause}
    """, params).fetchone()
    conn.close()
    return jsonify(dict(row))


@app.route("/api/period-comparison")
def api_period_comparison():
    args = request.args
    start = args.get("start_date", "")
    end = args.get("end_date", "")

    def get_stats(where_clause, params):
        conn = get_connection()
        row = conn.execute(f"""
            SELECT
                COALESCE(SUM(revenue), 0) AS revenue,
                COUNT(*) AS orders
            FROM sales WHERE {where_clause}
        """, params).fetchone()
        conn.close()
        return dict(row)

    current_where, current_params = build_filters(args)
    current = get_stats(current_where, current_params)

    prev_data = None
    if start and end:
        try:
            s = datetime.strptime(start, "%Y-%m-%d")
            e = datetime.strptime(end, "%Y-%m-%d")
            delta = e - s
            prev_end = s - timedelta(days=1)
            prev_start = prev_end - delta

            prev_args = dict(args)
            prev_args["start_date"] = prev_start.strftime("%Y-%m-%d")
            prev_args["end_date"] = prev_end.strftime("%Y-%m-%d")
            prev_where, prev_params = build_filters(prev_args)
            prev_data = get_stats(prev_where, prev_params)
        except ValueError:
            pass

    result = {"current": current, "previous": prev_data}
    if prev_data:
        def calc_change(curr, prev):
            diff = curr - prev
            pct = round((diff / abs(prev)) * 100, 2) if prev else None
            return {"absolute": round(diff, 2), "pct": pct}

        result["changes"] = {
            "revenue": calc_change(current["revenue"], prev_data["revenue"]),
            "orders": calc_change(current["orders"], prev_data["orders"]),
        }
    return jsonify(result)


@app.route("/api/revenue-trend")
def api_revenue_trend():
    where_clause, params = build_filters(request.args)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT
            substr(order_date, 1, 7) AS month,
            SUM(revenue) AS revenue
        FROM sales WHERE {where_clause}
        GROUP BY month ORDER BY month
    """, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/top-products")
def api_top_products():
    where_clause, params = build_filters(request.args)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT
            product,
            SUM(revenue) AS revenue,
            SUM(quantity) AS units
        FROM sales WHERE {where_clause}
        GROUP BY product ORDER BY revenue DESC LIMIT 10
    """, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/region-breakdown")
def api_region_breakdown():
    where_clause, params = build_filters(request.args)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT region, SUM(revenue) AS revenue
        FROM sales WHERE {where_clause}
        GROUP BY region ORDER BY revenue DESC
    """, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/category-breakdown")
def api_category_breakdown():
    where_clause, params = build_filters(request.args)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT category, SUM(revenue) AS revenue, SUM(quantity) AS units
        FROM sales WHERE {where_clause}
        GROUP BY category ORDER BY revenue DESC
    """, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/table")
def api_table():
    where_clause, params = build_filters(request.args)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT order_date, region, category, product, quantity, unit_price, revenue
        FROM sales WHERE {where_clause}
        ORDER BY order_date DESC LIMIT 200
    """, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/export")
def api_export():
    where_clause, params = build_filters(request.args)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT order_date, region, category, product, quantity, unit_price, revenue
        FROM sales WHERE {where_clause}
        ORDER BY order_date DESC
    """, params).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["order_date", "region", "category", "product", "quantity", "unit_price", "revenue"])
    for r in rows:
        writer.writerow([r["order_date"], r["region"], r["category"], r["product"],
                         r["quantity"], r["unit_price"], r["revenue"]])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=insightflow_report.csv"},
    )


@app.route("/api/export-pdf")
def api_export_pdf():
    if not REPORTLAB_AVAILABLE:
        return jsonify({"error": "ReportLab is not installed."}), 500

    args = request.args
    where_clause, params = build_filters(args)
    conn = get_connection()

    totals = conn.execute(f"""
        SELECT
            COALESCE(SUM(revenue), 0) AS revenue,
            COUNT(*) AS orders,
            COALESCE(SUM(quantity), 0) AS units
        FROM sales WHERE {where_clause}
    """, params).fetchone()

    monthly = conn.execute(f"""
        SELECT substr(order_date, 1, 7) AS month, SUM(revenue) AS revenue
        FROM sales WHERE {where_clause}
        GROUP BY month ORDER BY month
    """, params).fetchall()

    top_products = conn.execute(f"""
        SELECT product, SUM(revenue) AS revenue, SUM(quantity) AS units
        FROM sales WHERE {where_clause}
        GROUP BY product ORDER BY revenue DESC LIMIT 8
    """, params).fetchall()

    regions = conn.execute(f"""
        SELECT region, SUM(revenue) AS revenue
        FROM sales WHERE {where_clause}
        GROUP BY region ORDER BY revenue DESC
    """, params).fetchall()

    conn.close()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=18*mm, bottomMargin=18*mm,
    )

    styles = getSampleStyleSheet()
    w = A4[0] - 40*mm

    navy_rgb = colors.HexColor(NAVY)
    teal_rgb = colors.HexColor(TEAL)
    slate_rgb = colors.HexColor(SLATE)

    h1 = ParagraphStyle("h1", fontSize=22, textColor=navy_rgb, spaceAfter=4,
                        fontName="Helvetica-Bold", leading=26)
    h2 = ParagraphStyle("h2", fontSize=13, textColor=navy_rgb, spaceAfter=4,
                        fontName="Helvetica-Bold", spaceBefore=12, leading=16)
    body = ParagraphStyle("body", fontSize=9, textColor=colors.HexColor("#334155"), leading=13, spaceAfter=4)
    small = ParagraphStyle("small", fontSize=8, textColor=slate_rgb, leading=11)
    kpi_val = ParagraphStyle("kpi_val", fontSize=16, textColor=navy_rgb, fontName="Helvetica-Bold", leading=18)
    kpi_lbl = ParagraphStyle("kpi_lbl", fontSize=8, textColor=slate_rgb, leading=10)
    tbl_hdr = ParagraphStyle("tbl_hdr", fontSize=8, textColor=colors.white, fontName="Helvetica-Bold", leading=10, alignment=TA_LEFT)
    tbl_cell = ParagraphStyle("tbl_cell", fontSize=8, textColor=colors.HexColor("#1e293b"), leading=10)

    story = []

    story.append(Paragraph("InsightFlow", h1))
    story.append(Paragraph("Business Intelligence &amp; Sales Analytics Report", body))
    story.append(Spacer(1, 3*mm))
    story.append(HRFlowable(width=w, thickness=2, color=teal_rgb, spaceAfter=3))

    generated_at = datetime.now().strftime("%d %B %Y, %H:%M")
    story.append(Paragraph(f"Generated: {generated_at}", small))

    filter_parts = []
    if args.get("start_date"): filter_parts.append(f"From: {args['start_date']}")
    if args.get("end_date"): filter_parts.append(f"To: {args['end_date']}")
    if args.get("region") and args["region"] != "all": filter_parts.append(f"Region: {args['region']}")
    if args.get("category") and args["category"] != "all": filter_parts.append(f"Category: {args['category']}")
    if args.get("product") and args["product"] != "all": filter_parts.append(f"Product: {args['product']}")
    if filter_parts:
        story.append(Paragraph("Filters: " + " | ".join(filter_parts), small))

    story.append(Spacer(1, 5*mm))

    story.append(Paragraph("Key Performance Indicators", h2))
    story.append(HRFlowable(width=w, thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=4))

    total_rev = totals["revenue"] or 0
    total_orders = totals["orders"] or 0
    total_units = totals["units"] or 0

    kpi_data = [
        [Paragraph(f"₹{total_rev:,.0f}", kpi_val), Paragraph("Total Revenue", kpi_lbl)],
        [Paragraph(f"{total_orders:,}", kpi_val), Paragraph("Total Orders", kpi_lbl)],
        [Paragraph(f"{total_units:,}", kpi_val), Paragraph("Units Sold", kpi_lbl)],
        [Paragraph(f"₹{(total_rev/total_orders):,.0f}" if total_orders else "—", kpi_val), Paragraph("Avg Order Value", kpi_lbl)],
    ]

    val_row = [item[0] for item in kpi_data]
    lbl_row = [item[1] for item in kpi_data]
    kpi_table = Table([val_row, lbl_row], colWidths=[w/4]*4, hAlign="LEFT")
    kpi_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 5*mm))

    monthly_list = [dict(r) for r in monthly]
    if monthly_list:
        story.append(Paragraph("Monthly Revenue Trend", h2))
        story.append(HRFlowable(width=w, thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=4))
        trend_rows = [[
            Paragraph("Month", tbl_hdr),
            Paragraph("Revenue (₹)", tbl_hdr),
            Paragraph("Share of Total", tbl_hdr)
        ]]
        for m in monthly_list:
            rev = m["revenue"] or 0
            share_str = f"{((rev/total_rev)*100):.1f}%" if total_rev > 0 else "—"
            trend_rows.append([
                Paragraph(m["month"], tbl_cell),
                Paragraph(f"{rev:,.0f}", tbl_cell),
                Paragraph(share_str, tbl_cell),
            ])
        trend_table = Table(trend_rows, colWidths=[w*0.35, w*0.35, w*0.3], hAlign="LEFT")
        trend_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), teal_rgb),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdfa")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccfbf1")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(trend_table)
        story.append(Spacer(1, 5*mm))

    prod_list = [dict(r) for r in top_products]
    if prod_list:
        story.append(Paragraph("Product Performance", h2))
        story.append(HRFlowable(width=w, thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=4))
        prod_rows = [[
            Paragraph("Product", tbl_hdr),
            Paragraph("Revenue (₹)", tbl_hdr),
            Paragraph("Units", tbl_hdr),
            Paragraph("Revenue Share", tbl_hdr)
        ]]
        for p in prod_list:
            rev = p["revenue"] or 0
            share_str = f"{((rev/total_rev)*100):.1f}%" if total_rev > 0 else "—"
            prod_rows.append([
                Paragraph(str(p["product"]), tbl_cell),
                Paragraph(f"{rev:,.0f}", tbl_cell),
                Paragraph(f"{int(p['units']):,}", tbl_cell),
                Paragraph(share_str, tbl_cell),
            ])
        prod_table = Table(prod_rows, colWidths=[w*0.4, w*0.25, w*0.15, w*0.2], hAlign="LEFT")
        prod_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), navy_rgb),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(prod_table)
        story.append(Spacer(1, 5*mm))

    region_list = [dict(r) for r in regions]
    if region_list:
        story.append(Paragraph("Regional Performance", h2))
        story.append(HRFlowable(width=w, thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=4))
        reg_rows = [[
            Paragraph("Region", tbl_hdr),
            Paragraph("Revenue (₹)", tbl_hdr),
            Paragraph("Revenue Share", tbl_hdr)
        ]]
        for r in region_list:
            rev = r["revenue"] or 0
            share_str = f"{((rev/total_rev)*100):.1f}%" if total_rev > 0 else "—"
            reg_rows.append([
                Paragraph(str(r["region"]), tbl_cell),
                Paragraph(f"{rev:,.0f}", tbl_cell),
                Paragraph(share_str, tbl_cell),
            ])
        reg_table = Table(reg_rows, colWidths=[w*0.4, w*0.35, w*0.25], hAlign="LEFT")
        reg_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), navy_rgb),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(reg_table)
        story.append(Spacer(1, 5*mm))

    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width=w, thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(f"InsightFlow | Report generated {generated_at}", small))

    doc.build(story)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=insightflow_report.pdf"},
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
