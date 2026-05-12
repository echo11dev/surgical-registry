# University of Miami Hip & Knee Arthroplasty Registry

**Production-ready Flask web application** for managing a comprehensive surgical registry focused on hip and knee arthroplasty. Built for research, quality improvement, and standardized complication tracking at the University of Miami.

## Key Features (v1.4 – May 2026)

### Core Registry Functions
- **Patients**: Full CRUD with search by name, MRN, phone. Includes demographics, BMI auto-calculation, race/ethnicity fields.
- **Surgeries**: Detailed capture including joint (Hip/Knee), side, surgery type (Primary/Revision), procedure name auto-calculated from standardized algorithm, surgeon, hospital, notes.
- **Implants**: Full implant tracking with master catalog lookup by reference number. Mandatory component validation for Primary THA/TKA.
- **Research Projects**: Enroll surgeries into multiple research studies (many-to-many).

### Standardized Complications Module (New in v1.1)
Completely redesigned **Complications tab** aligned with:
- **The Knee Society** (TKA Complications, 2013)
- **The Hip Society** (THA Complications, 2015)

**Four organized sections**:
1. **General Complications** (common to hip & knee)
2. **Hip-Specific Complications**
3. **Knee-Specific Complications**
4. **Key Outcome Events** (Reoperation, Readmission ≤90 days, Revision, Death ≤90 days – critical for public reporting)

- Every item has a clickable info icon (i) that opens a modal with the **official definition** from the Hip/Knee Society papers.
- Optional date-of-occurrence capture for time-to-event analysis.
- Stored as structured JSON with value + date for robust querying and research exports.
- Supports future severity stratification (Grade 1–5).

This ensures our registry produces comparable, high-quality complication data for internal QI, research publications, and external benchmarking.

### Other Features
- **Lookup Tables**: Fully manageable (Hospitals, Manufacturers, Implant Types, Surgeons, Procedure Types, Research Projects).
- **Dashboard**: Live stats including complication rate, deep infection rate, 30-day readmission rate, revision burden, and % outpatient joints.
- **Reports**: One-click CSV exports for Patients, Surgeries, and Implants (de-identified ready for research).
- **Implant Master Catalog**: Searchable central database of implants by catalog/reference number.
- **Modern UI**: Bootstrap 5, responsive, modals, flash messages, confirmations.
- **Data Integrity**: Proper cascading deletes, unique constraints on MRN and implant reference numbers.

## How to Run

1. Make sure you have Python 3.12+
2. Install dependencies:
   ```bash
   pip install flask flask-sqlalchemy
   ```
3. Run the app:
   ```bash
   cd /home/workdir/artifacts/surgical_registry
   python app.py
   ```
4. Open browser to **http://localhost:5000**

The database (`/tmp/surgical_registry.db`) is created automatically on first run with sample data.

## Data Model

```
Patient (1) ────< (many) Surgery (1) ────< (many) Implant
     │                  │
     └── Gender         ├── ProcedureType
                        ├── Surgeon
                        └── Hospital

Implant
├── ImplantType
└── Manufacturer
```

All foreign keys are properly indexed and relationships use SQLAlchemy ORM with cascade deletes.

## Key Pages

- `/` — Dashboard with stats & recent activity
- `/patients` — Patient list + register new
- `/patients/<id>` — Patient detail + surgeries list + add surgery
- `/surgeries/<id>` — Surgery detail + implants list + add/edit implants
- `/lookups` — Manage all lookup tables (add/delete entries)
- `/reports` — **Redesigned Reports & Exports page** (v1.1.1)
  - Full Registry Backup (ZIP containing 3 standardized CSVs)
  - Specific reports filtered by **Date Range**, **Surgeon**, or **Implant/Manufacturer**
  - All exports downloadable as CSV (or ZIP for backups)
  - Includes complication counts and structured data aligned with Hip/Knee Society standards

## Notes

- This is a **demo** application. For production use:
  - Change `SECRET_KEY`
  - Use PostgreSQL/MySQL instead of SQLite
  - Add authentication & role-based access
  - Enable HTTPS and proper logging
  - Add audit logging for HIPAA compliance
- Serial numbers and MRNs are unique (enforced by DB)
- All dates use proper `date` type

## Screenshots (text description)

The UI features a clean medical-themed design with:
- Sticky navbar with quick links
- Statistics cards on dashboard
- Responsive tables with hover effects
- Bootstrap modals for all add/edit forms
- Instant feedback via flash messages
- Mobile-friendly layout

Enjoy tracking your surgical cases! 

Built for the Grok AI coding session — May 2026.

---

## 🌐 Deploy to the Internet (Free Options)

Your Surgical Registry can be deployed **publicly on the internet for free** in under 5 minutes using these platforms:

### Option 1: Render.com (Recommended - Easiest)

1. Go to [https://render.com](https://render.com) and sign up (free)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repo (or upload the folder)
4. Settings:
   - **Name**: `surgical-registry`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Plan**: Free
5. Add these **Environment Variables**:
   - `SECRET_KEY` → (generate a long random string)
   - `DATABASE_URL` → Leave empty (Render will provide Postgres automatically on free tier)
6. Click **"Create Web Service"**
7. Your app will be live at `https://surgical-registry.onrender.com`

**Render gives you a free PostgreSQL database** — perfect for production!

---

### Option 2: Railway.app (Very Easy)

1. Go to [https://railway.app](https://railway.app)
2. Sign in with GitHub
3. Click **"New Project"** → **"Deploy from GitHub repo"**
4. Select this repo
5. Railway auto-detects Flask + adds Postgres automatically
6. Add environment variable:
   - `SECRET_KEY` = your secret key
7. Done! Your app is live.

---

### Option 3: Heroku (Classic)

```bash
# After installing Heroku CLI
heroku create surgical-registry-2026
git push heroku main
heroku config:set SECRET_KEY="your-long-random-secret-here"
heroku addons:create heroku-postgresql:mini
heroku open
```

---

### Option 4: PythonAnywhere (Good for Beginners)

1. Go to [https://www.pythonanywhere.com](https://www.pythonanywhere.com)
2. Create a free account
3. Upload your files via the web interface
4. Set up a Flask web app pointing to `app.py`
5. Use their built-in MySQL or SQLite

---

## 🔒 Security Notes for Production

Before going live:
1. **Change `SECRET_KEY`** to a long random string (use `python -c "import secrets; print(secrets.token_hex(32))"`)
2. **Use PostgreSQL** instead of SQLite (all platforms above provide it free)
3. Consider adding **user authentication** (Flask-Login) for real medical data
4. Enable **HTTPS** (all platforms above do this automatically)

---

## 📱 Mobile App (Future)

The app already includes a `/health` endpoint and API routes. You can easily connect:
- Flutter app
- React Native app
- Native iOS/Android app

Just point them to your deployed URL + add JWT authentication when ready.

---

## Quick Local Production Test

```bash
pip install -r requirements.txt
export SECRET_KEY="test-secret-key-12345"
export DATABASE_URL="sqlite:///./test.db"
python app.py
```

Or with gunicorn:
```bash
gunicorn app:app --bind 0.0.0.0:5000
```