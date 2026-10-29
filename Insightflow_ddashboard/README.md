# InsightFlow — Business Intelligence & Sales Analytics Platform

InsightFlow is a sales analytics dashboard built with Python (Flask) and JavaScript (Chart.js). I built this project to make it easy to upload sales data from CSV files and immediately visualize key performance metrics, monthly trends, regional distribution, and top products without needing complicated BI software.

The dashboard includes interactive charts, period-over-period comparisons, customizable filters, and report exports in both CSV and PDF formats.

---

## Features

- **Sales KPI Cards:** Displays total revenue, total orders, units sold, and average order value.
- **Period Comparison:** Compares the selected date range against the immediately preceding period to show changes in revenue and orders.
- **Interactive Charts (Chart.js):**
  - Monthly revenue trend (line chart)
  - Regional sales distribution (doughnut chart)
  - Top-selling products by revenue (horizontal bar chart)
  - Category sales breakdown (bar chart)
- **Data Filtering:** Filter records by start date, end date, region, category, or product.
- **Recent Orders Table:** View recent transaction records with pagination.
- **CSV Upload & Sample Data:** Upload any valid sales CSV, or load the built-in sample dataset with one click.
- **Report Exports:** Export filtered sales data to CSV or download a formatted PDF summary report generated using ReportLab.

---

## Technologies Used

- **Backend:** Python 3, Flask, Pandas, SQLite
- **Frontend:** HTML5, CSS3, JavaScript (ES6+), Chart.js
- **PDF Generation:** ReportLab
- **Storage:** SQLite (`dashboard.db`)

---

## Project Structure

```
sales-analytics-dashboard-main/
├── app.py                      # Flask routes, API endpoints, data processing, and PDF export
├── database.py                 # SQLite database initialization and connection helper
├── requirements.txt            # Python dependencies
├── .gitignore                  # Git ignore rules
├── sample_data/
│   └── sample_data.csv         # Comprehensive sample sales dataset (240 rows)
├── static/
│   ├── css/
│   │   └── style.css           # Dashboard styles
│   ├── js/
│   │   ├── dashboard.js        # Dashboard interactivity, API calls, and Chart.js setup
│   │   └── chart.umd.min.js    # Self-hosted Chart.js library
│   └── fonts/                  # Self-hosted Inter and Fraunces fonts
└── templates/
    └── dashboard.html          # Main dashboard HTML template
```

---

## How to Run the Project (Windows / VS Code)

### 1. Open the Project Folder
Open VS Code, select **File > Open Folder...**, and navigate to the project directory:
```powershell
cd v:\vs\sales-analytics-dashboard-main
```

### 2. Create a Virtual Environment
In the VS Code terminal (PowerShell), create a Python virtual environment:
```powershell
python -m venv .venv
```

### 3. Activate the Virtual Environment
Activate the environment:
```powershell
.venv\Scripts\Activate.ps1
```
*(If you see an execution policy error in PowerShell, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first.)*

### 4. Install Dependencies
Install the required packages from `requirements.txt`:
```powershell
pip install -r requirements.txt
```

### 5. Start the Application
Run the Flask app:
```powershell
python app.py
```

The database (`dashboard.db`) initializes automatically when the app starts.

### 6. Open the Dashboard in Your Browser
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## Sample Dataset

The project includes a ready-to-use sample dataset located at:
```
sample_data/sample_data.csv
```
This file contains **240 sales records** spanning across various regions, product categories, and months (from November 2025 to April 2026).

To load it:
- Click the **"Load Sample Data"** button on the welcome screen, or
- Drag and drop `sample_data/sample_data.csv` onto the upload zone.

You can also upload your own CSV files. The CSV should contain at least: `order_date`, `region`, `category`, `product`, `quantity`, and `unit_price`.

---

## Notes & Limitations

- The dashboard currently assumes sales amounts are calculated from `quantity * unit_price` unless a `revenue` column is explicitly provided.
- Dates should ideally follow `YYYY-MM-DD` format in uploaded CSVs.
- This application uses SQLite and is meant for local analysis or demonstration purposes.
"# InsightFlow" 
