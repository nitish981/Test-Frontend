"""
DataBridge API Backend
======================
A lightweight Flask proxy that forwards requests to Shopify (GraphQL Admin API)
and Facebook Ads (Graph API). This solves CORS issues — the browser talks to
this server, and this server talks to the external APIs.

Deploy for free on Render.com, Railway.app, or any Python host.
"""

import os
import json
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)  # Allow all origins — the frontend can be hosted anywhere


# ─────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "DataBridge API",
        "endpoints": ["/shopify/data", "/facebook/data"]
    })


# ─────────────────────────────────────────────────────────────
# SHOPIFY — ShopifyQL via GraphQL Admin API
# ─────────────────────────────────────────────────────────────
@app.route("/shopify/data", methods=["POST"])
def shopify_data():
    try:
        body = request.get_json(force=True)
        shop_domain = body.get("shop_domain", "").strip()
        access_token = body.get("access_token", "").strip()
        since_date = body.get("since_date", "2025-01-01")
        until_date = body.get("until_date", "2025-12-31")

        if not shop_domain or not access_token:
            return jsonify({"error": "shop_domain and access_token are required"}), 400

        # Normalize domain
        if not shop_domain.endswith(".myshopify.com"):
            if "." not in shop_domain:
                shop_domain = shop_domain + ".myshopify.com"

        api_version = "2025-04"
        graphql_url = f"https://{shop_domain}/admin/api/{api_version}/graphql.json"

        # Build ShopifyQL query
        shopifyql = f"""
        FROM sales
          SHOW gross_sales, discounts, returns, net_sales, taxes, shipping_charges, total_sales
          GROUP BY day, order_id
          SINCE {since_date}
          UNTIL {until_date}
          ORDER BY day ASC
        """.strip()

        graphql_query = """
        query ($shopifyql: String!) {
          shopifyqlQuery(query: $shopifyql) {
            tableData {
              columns { name dataType displayName }
              rows
            }
            parseErrors
          }
        }
        """

        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }

        resp = requests.post(
            graphql_url,
            headers=headers,
            json={"query": graphql_query, "variables": {"shopifyql": shopifyql}},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        # Check for errors
        if "errors" in data:
            return jsonify({"error": "; ".join(e.get("message", str(e)) for e in data["errors"])}), 400

        result = data.get("data", {}).get("shopifyqlQuery")
        if not result:
            return jsonify({"error": "No shopifyqlQuery in response"}), 400

        if result.get("parseErrors"):
            return jsonify({"error": f"ShopifyQL parse errors: {result['parseErrors']}"}), 400

        # Parse into rows
        columns = [col["name"] for col in result["tableData"]["columns"]]
        rows = result["tableData"]["rows"]

        # Column rename map
        col_map = {
            "day": "date", "order_id": "order_id", "gross_sales": "gross_sale",
            "discounts": "discount", "returns": "returns", "net_sales": "net_sale",
            "taxes": "taxes", "shipping_charges": "shipping_charges", "total_sales": "total_sales",
        }

        display_columns = [col_map.get(c, c) for c in columns]
        table_rows = []
        for row in rows:
            obj = {}
            for i, col in enumerate(columns):
                key = col_map.get(col, col)
                obj[key] = row[i] if i < len(row) else None
            table_rows.append(obj)

        return jsonify({
            "success": True,
            "columns": display_columns,
            "data": table_rows,
            "row_count": len(table_rows)
        })

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Shopify API request failed: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# FACEBOOK ADS — Graph API Async Insights
# ─────────────────────────────────────────────────────────────
@app.route("/facebook/data", methods=["POST"])
def facebook_data():
    try:
        body = request.get_json(force=True)
        ad_account_id = body.get("ad_account_id", "").strip()
        access_token = body.get("access_token", "").strip()
        start_date = body.get("start_date", "2024-01-01")
        end_date = body.get("end_date", "2025-12-05")

        if not ad_account_id or not access_token:
            return jsonify({"error": "ad_account_id and access_token are required"}), 400

        # Ensure act_ prefix
        if not ad_account_id.startswith("act_"):
            ad_account_id = "act_" + ad_account_id

        api_version = "v21.0"
        base_url = f"https://graph.facebook.com/{api_version}"

        # Fields to fetch
        fields = ",".join([
            "date_start", "date_stop", "campaign_name", "adset_name", "ad_name",
            "impressions", "clicks", "reach", "spend", "cpc", "ctr", "cpm",
            "actions", "action_values"
        ])

        time_range = json.dumps({"since": start_date, "until": end_date})

        # ── Date chunking to avoid timeouts on large ranges ──
        all_rows = []
        for chunk_start, chunk_end in _gen_date_chunks(start_date, end_date, 30):
            chunk_time_range = json.dumps({"since": chunk_start, "until": chunk_end})

            # Step 1: Create async job
            create_resp = requests.post(
                f"{base_url}/{ad_account_id}/insights",
                data={
                    "access_token": access_token,
                    "level": "ad",
                    "time_increment": 1,
                    "fields": fields,
                    "time_range": chunk_time_range,
                    "async": 1
                },
                timeout=30
            )

            if create_resp.status_code != 200:
                err = create_resp.json().get("error", {}).get("message", create_resp.text[:300])
                return jsonify({"error": f"Facebook API error: {err}"}), 400

            job_data = create_resp.json()
            report_run_id = job_data.get("report_run_id")
            if not report_run_id:
                return jsonify({"error": f"No report_run_id: {json.dumps(job_data)[:200]}"}), 400

            # Step 2: Poll for completion
            for attempt in range(120):  # up to ~6 min per chunk
                time.sleep(3)
                poll_resp = requests.get(
                    f"{base_url}/{report_run_id}",
                    params={
                        "access_token": access_token,
                        "fields": "async_status,async_percent_completion"
                    },
                    timeout=15
                )
                poll_data = poll_resp.json()
                status = poll_data.get("async_status")

                if status == "Job Completed":
                    break
                elif status == "Job Failed":
                    return jsonify({"error": f"Facebook job failed: {json.dumps(poll_data)}"}), 400
            else:
                return jsonify({"error": "Facebook job polling timed out"}), 504

            # Step 3: Fetch paginated results
            fetch_url = f"{base_url}/{report_run_id}/insights"
            params = {"access_token": access_token, "limit": 500}
            while fetch_url:
                data_resp = requests.get(fetch_url, params=params, timeout=30)
                data_json = data_resp.json()
                all_rows.extend(data_json.get("data", []))
                fetch_url = data_json.get("paging", {}).get("next")
                params = {}  # next URL already has params

        # Step 4: Flatten for display
        display_rows = []
        for row in all_rows:
            flat = {
                "date": row.get("date_start", ""),
                "campaign": row.get("campaign_name", ""),
                "adset": row.get("adset_name", ""),
                "ad": row.get("ad_name", ""),
                "impressions": row.get("impressions", 0),
                "clicks": row.get("clicks", 0),
                "reach": row.get("reach", 0),
                "spend": row.get("spend", "0"),
                "cpc": row.get("cpc", "0"),
                "ctr": row.get("ctr", "0"),
                "cpm": row.get("cpm", "0"),
            }

            # Extract key actions
            for a in (row.get("actions") or []):
                atype = a.get("action_type", "")
                val = a.get("value", 0)
                if atype == "purchase":
                    flat["purchases"] = val
                elif atype == "link_click":
                    flat["link_clicks"] = val
                elif atype == "landing_page_view":
                    flat["landing_page_views"] = val
                elif atype == "add_to_cart":
                    flat["add_to_cart"] = val
                elif atype == "initiate_checkout":
                    flat["checkouts"] = val

            # Extract purchase value
            for av in (row.get("action_values") or []):
                if av.get("action_type") == "offsite_conversion.fb_pixel_purchase":
                    flat["purchase_value"] = av.get("value", 0)

            display_rows.append(flat)

        columns = [
            "date", "campaign", "adset", "ad", "impressions", "clicks", "reach",
            "spend", "cpc", "ctr", "cpm", "purchases", "purchase_value",
            "link_clicks", "landing_page_views", "add_to_cart", "checkouts"
        ]

        return jsonify({
            "success": True,
            "columns": columns,
            "data": display_rows,
            "row_count": len(display_rows)
        })

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Facebook API request failed: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _gen_date_chunks(start, end, days):
    """Split a date range into chunks of N days."""
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    cur = s
    while cur <= e:
        ce = min(cur + timedelta(days=days - 1), e)
        yield cur.isoformat(), ce.isoformat()
        cur = ce + timedelta(days=1)


# ─────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
