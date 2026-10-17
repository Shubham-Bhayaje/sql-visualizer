# SQL Query Visualizer

A small Streamlit app for learning SQL. It connects to a PostgreSQL database, runs your queries, and can show a `SELECT` query **one stage at a time**, so you can see what each clause does to the data.

## Features

- **Run SQL tab:** run any SQL (several statements at once is fine) against your database, including `CREATE`, `INSERT`, `UPDATE`, and `DELETE`.
- **Step by step tab:** for a single `SELECT`, click through the stages in the order the database runs them: `FROM`/`JOIN`, `WHERE`, `GROUP BY` (one colored pile per group), `HAVING`, `SELECT`, `ORDER BY`, and `LIMIT`. The matching part of the query is highlighted, and `NULL` values are marked.
- **Sidebar:** connection settings and a list of your tables and columns.

## Requirements

- Python 3.10 or newer
- A running PostgreSQL server

## Setup

```bash
git clone https://github.com/Shubham-Bhayaje/sql-visualizer.git
cd sql-visualizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Connecting to your database

Use the sidebar fields:

| Field | Value |
|---|---|
| Database | your database name, for example `practice` |
| Host | leave empty to use the local socket (Linux or WSL), or `localhost` |
| Port | `5432` |
| User | leave empty to use your Linux username |
| Password | leave empty when using the local socket |

## Notes

- The Step by step tab supports plain `SELECT` queries with joins, `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, and `LIMIT`. Subqueries inside `FROM` or `JOIN` are not supported yet.
- The Run SQL tab saves changes immediately, exactly like `psql`. Use a practice database, not one you care about.

## Built with

Python, Streamlit, pandas, psycopg, sqlglot, and sqlparse.
