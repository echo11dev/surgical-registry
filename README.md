# Surgical Registry App

A complete, production-ready demo web application for managing a surgical registry with patients, surgeries, and implants. Built with Flask, SQLAlchemy, SQLite, and Bootstrap 5.

## Features

- **Patients**: Full CRUD (Create, Read, Update, Delete) with search by name/MRN/phone
- **Surgeries**: Each patient can have multiple surgeries. Record date, procedure type, surgeon, hospital, OR, duration, notes
- **Implants**: Each surgery can have multiple implants with type, manufacturer, model, serial #, size, lot #, notes
- **Lookup Tables**: Manage standardized dropdown values:
  - Genders
  - Procedure Types (11 common orthopedic/neurosurgical procedures pre-loaded)
  - Implant Types (14 common types)
  - Manufacturers (9 major orthopedic companies)
  - Hospitals (8 top US hospitals)
  - Surgeons (5 sample surgeons with specialties)
- **Dashboard**: Statistics, recent surgeries, top procedures
- **Relationships**: Proper one-to-many cascading deletes (delete patient → deletes surgeries → deletes implants)
- **Sample Data**: 4 patients, 5 surgeries, 12 implants pre-seeded
- **Modern UI**: Responsive Bootstrap 5, modals, flash messages, confirmations

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
     └─── Gender         ├─── ProcedureType
                        ├─── Surgeon
                        └─── Hospital

Implant
├─── ImplantType
└─── Manufacturer
```

All foreign keys are properly indexed and relationships use SQLAlchemy ORM with cascade deletes.

## Key Pages

- `/` — Dashboard with stats & recent activity
- `/patients` — Patient list + register new
- `/patients/<id>` — Patient detail + surgeries list + add surgery
- `/surgeries/<id>` — Surgery detail + implants list + add/edit implants
- `/lookups` — Manage all lookup tables (add/delete entries)

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