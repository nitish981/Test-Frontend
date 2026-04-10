# DataBridge — Shopify + Facebook Ads Dashboard

A dark industrial-utility dashboard that pulls live data from **Shopify** (ShopifyQL / GraphQL Admin API) and **Facebook Ads** (Graph API async insights).

**Architecture:**
```
┌─────────────────┐       ┌──────────────────┐       ┌─────────────────┐
│  GitHub Pages   │──────▶│  Render.com       │──────▶│  Shopify API    │
│  (index.html)   │ POST  │  (app.py / Flask) │ POST  │  Facebook API   │
│  Frontend       │◀──────│  Backend Proxy    │◀──────│  External APIs  │
└─────────────────┘  JSON └──────────────────┘  JSON └─────────────────┘
```

---

## 🚀 Step-by-Step Deployment

### STEP 1: Create GitHub Repository

1. Go to **https://github.com/new**
2. Repository name: `databridge`
3. Set to **Public**
4. Click **Create repository**

### STEP 2: Upload All Files

Upload these files to the repo root:

```
databridge/
├── app.py              ← Flask backend (proxy server)
├── requirements.txt    ← Python dependencies
├── render.yaml         ← Render deployment config
├── Procfile            ← Alternative deployment config
├── index.html          ← Frontend dashboard
├── .gitignore
└── README.md
```

**How to upload:**
1. On your new repo page, click **"Add file"** → **"Upload files"**
2. Drag all files from this folder
3. Click **"Commit changes"**

### STEP 3: Deploy Backend on Render.com (FREE)

1. Go to **https://render.com** and sign up (use GitHub login)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub account if prompted
4. Select your **`databridge`** repository
5. Configure:
   - **Name:** `databridge-api` (or anything you want)
   - **Region:** Pick closest to you
   - **Branch:** `main`
   - **Runtime:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 2`
   - **Plan:** `Free`
6. Click **"Create Web Service"**
7. Wait 2-3 minutes for it to build and deploy
8. You'll get a URL like: **`https://databridge-api-xxxx.onrender.com`**
9. Test it: open that URL in browser — you should see `{"status": "ok"}`

> ⚠️ **Note:** Free Render instances sleep after 15 min of inactivity.
> First request after sleep takes ~30 seconds to wake up. This is normal.

### STEP 4: Host Frontend on GitHub Pages (FREE)

1. Go to your repo → **Settings** → **Pages** (left sidebar)
2. Under **"Source"**, select **"Deploy from a branch"**
3. Branch: **`main`**, folder: **`/ (root)`**
4. Click **Save**
5. Wait 1-2 minutes
6. Your dashboard will be live at: **`https://YOUR-USERNAME.github.io/databridge/`**

### STEP 5: Connect Frontend to Backend

1. Open your GitHub Pages dashboard URL
2. In the top bar, replace `https://YOUR-APP.onrender.com` with your actual Render URL
   (e.g., `https://databridge-api-xxxx.onrender.com`)
3. Click **"Test"** — it should show a green **"CONNECTED"** badge
4. Enter your Shopify / Facebook credentials and fetch data!

---

## 🔧 How It Works

### Shopify Flow
1. You enter shop domain + access token + date range
2. Frontend sends `POST /shopify/data` to your Render backend
3. Backend builds a ShopifyQL query and sends it via GraphQL Admin API
4. Returns order-level breakdown: date, order_id, gross_sale, discount, returns, net_sale, taxes, shipping, total_sales

### Facebook Ads Flow
1. You enter ad account ID + access token + date range
2. Frontend sends `POST /facebook/data` to your Render backend
3. Backend creates an async insights job via Graph API
4. Polls until complete, then fetches all pages of results
5. Flattens actions (purchases, link_clicks, add_to_cart, etc.) into clean columns

---

## 🔑 Getting Your API Credentials

### Shopify
1. Go to your Shopify admin → **Settings** → **Apps and sales channels**
2. Click **"Develop apps"** → **"Create an app"**
3. Under **API credentials**, click **"Configure Admin API scopes"**
4. Enable: `read_orders`, `read_reports`, `read_analytics`
5. Click **"Install app"** and copy the **Admin API access token**
6. Your shop domain is: `your-store-name.myshopify.com`

### Facebook Ads
1. Go to **https://developers.facebook.com/tools/explorer/**
2. Select your app (or create one)
3. Add permissions: `ads_read`, `ads_management`
4. Click **"Generate Access Token"** and copy it
5. Your Ad Account ID is in Ads Manager URL: `act_XXXXXXXXX`

> ⚠️ Facebook tokens expire! For long-term use, exchange for a long-lived token.

---

## 🖥 Local Development

Run the backend locally:
```bash
pip install -r requirements.txt
python app.py
```
Backend runs at `http://localhost:8000`.

Open `index.html` in your browser and set the backend URL to `http://localhost:8000`.

---

## 📁 File Overview

| File | Purpose |
|---|---|
| `app.py` | Flask backend — proxies API calls, handles CORS |
| `requirements.txt` | Python packages: flask, flask-cors, requests, gunicorn |
| `render.yaml` | Tells Render.com how to build/run the app |
| `Procfile` | Alternative config for Heroku/Railway |
| `index.html` | The full dashboard — HTML + CSS + JS, no build tools |
| `.gitignore` | Keeps cache/env files out of git |

---

## ❓ Troubleshooting

| Problem | Fix |
|---|---|
| "Test" button shows **UNREACHABLE** | Check your Render URL is correct, wait for cold start (~30s) |
| Shopify returns **401** | Your access token is wrong or expired — regenerate it |
| Shopify returns **parse errors** | Your store may not support ShopifyQL — needs Shopify Plus or compatible plan |
| Facebook returns **error** | Token expired — generate a new one at developers.facebook.com |
| CORS errors in console | Make sure you're calling your Render backend, not the APIs directly |
| Render build fails | Check the Render logs — usually a typo in requirements.txt |

---

**Security note:** Credentials are sent from your browser to your Render backend over HTTPS, then from Render to the APIs. Nothing is stored or logged. For production use, add authentication to the backend.
