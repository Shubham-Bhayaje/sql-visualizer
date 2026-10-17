"""
SQL Query Visualizer — Postgres edition.
Production-grade UI for learning SQL step by step.
"""

import difflib
import html
import re
from uuid import uuid4

import pandas as pd
import psycopg
import sqlglot
import sqlparse
import streamlit as st
from sqlglot import exp

MAX_RESULT_ROWS = 5_000
STATEMENT_TIMEOUT_MS = 15_000
LOCK_TIMEOUT_MS = 3_000

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="SQL Visualizer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Production-grade CSS ─────────────────────────────────────────────
st.markdown("""
<style>
/* ── Reset & Global ─────────────────────────────────────────────── */
.block-container {
    max-width: min(96vw, 1580px) !important;
    padding: 1rem 2rem 3rem 2rem !important;
}
h1, h2, h3 { font-weight: 700 !important; }

/* ── Side-by-side layout & sticky query ────────────────────────── */
.sticky-query {
    position: sticky;
    top: 1.5rem;
    z-index: 5;
}
.query-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.8rem;
    font-weight: 700;
    color: rgba(128,128,128,0.75);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.3rem;
}
.query-active-badge {
    background: rgba(102,126,234,0.18);
    color: #667eea;
    font-size: 0.72rem;
    padding: 0.15rem 0.55rem;
    border-radius: 8px;
    font-weight: 700;
}

/* ── Header ─────────────────────────────────────────────────────── */
.app-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.2rem 0 0.8rem 0;
    border-bottom: 2px solid rgba(128,128,128,0.15);
    margin-bottom: 1.2rem;
}
.app-header .icon { font-size: 1.8rem; }
.app-header .title {
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: -0.02em;
}
.app-header .badge {
    background: rgba(102,126,234,0.15);
    color: #667eea;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    margin-left: 0.3rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

/* ── SQL editor ─────────────────────────────────────────────────── */
.stTextArea textarea {
    font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace !important;
    font-size: 0.88rem !important;
    line-height: 1.6 !important;
    border-radius: 10px !important;
    border: 1.5px solid rgba(128,128,128,0.25) !important;
    padding: 0.8rem 1rem !important;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.stTextArea textarea:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 3px rgba(102,126,234,0.12) !important;
}

/* ── Buttons ────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 0.4rem 1.2rem !important;
    transition: transform 0.08s, box-shadow 0.15s !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 3px 12px rgba(0,0,0,0.15);
}
.stButton > button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
}

/* ── Tabs ───────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 2px solid rgba(128,128,128,0.15);
}
.stTabs [data-baseweb="tab"] {
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.6rem 1.5rem;
    border-radius: 8px 8px 0 0;
}
.stTabs [aria-selected="true"] {
    background: rgba(102,126,234,0.08);
}

/* ── Pipeline breadcrumb ────────────────────────────────────────── */
.pipeline {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.25rem;
    padding: 0.6rem 0;
}
.pipeline .step {
    font-size: 0.78rem;
    padding: 0.2rem 0.65rem;
    border-radius: 6px;
    font-weight: 500;
    background: rgba(128,128,128,0.1);
    color: rgba(128,128,128,0.65);
    white-space: nowrap;
}
.pipeline .step.active {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    font-weight: 700;
    box-shadow: 0 2px 8px rgba(102,126,234,0.3);
}
.pipeline .step.done {
    background: rgba(102,126,234,0.12);
    color: #667eea;
    font-weight: 600;
}
.pipeline .arrow {
    color: rgba(128,128,128,0.35);
    font-size: 0.7rem;
    margin: 0 0.1rem;
}
/* Subquery sub-steps: orange-tinted to distinguish from outer query */
.pipeline .step.sub {
    font-size: 0.72rem;
    padding: 0.15rem 0.5rem;
    border: 1px dashed rgba(255,152,0,0.35);
    background: rgba(255,152,0,0.06);
    color: rgba(255,152,0,0.65);
}
.pipeline .step.sub.active {
    background: linear-gradient(135deg, #ff9800 0%, #f44336 100%);
    color: white;
    font-weight: 700;
    border: none;
    box-shadow: 0 2px 8px rgba(255,152,0,0.3);
}
.pipeline .step.sub.done {
    background: rgba(255,152,0,0.15);
    color: #ff9800;
    font-weight: 600;
    border: 1px dashed rgba(255,152,0,0.4);
}

/* ── Query display ──────────────────────────────────────────────── */
.sql-display {
    background: rgba(128,128,128,0.08);
    border: 1px solid rgba(128,128,128,0.12);
    padding: 0.8rem 1rem;
    border-radius: 10px;
    margin: 0.6rem 0 1rem 0;
}
.sql-display .line {
    font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.82rem;
    line-height: 1.65;
    white-space: pre;
    padding: 1px 6px;
    border-radius: 4px;
}
.sql-display .line.hl {
    background: rgba(102,126,234,0.2);
    border-left: 3px solid #667eea;
    padding-left: 8px;
}

/* ── Stage header ───────────────────────────────────────────────── */
.stage-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0 0.3rem 0;
    margin-bottom: 0.3rem;
}
.stage-header .num {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    width: 28px; height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    font-weight: 700;
    flex-shrink: 0;
}
.stage-header .label {
    font-size: 1.1rem;
    font-weight: 700;
}

/* ── Data tables ────────────────────────────────────────────────── */
.stDataFrame { border-radius: 8px; overflow: hidden; }
.stDataFrame [data-testid="stDataFrameResizable"] {
    width: 100% !important;
}

/* ── Pile cards (GROUP BY) ──────────────────────────────────────── */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
    overflow: visible !important;
}
[data-testid="stVerticalBlockBorderWrapper"] .stDataFrame {
    min-width: 0 !important;
}

/* ── Row count badge ────────────────────────────────────────────── */
.row-count {
    display: inline-block;
    background: rgba(128,128,128,0.1);
    padding: 0.15rem 0.6rem;
    border-radius: 10px;
    font-size: 0.78rem;
    font-weight: 500;
    margin-top: 0.3rem;
}

/* ── Sidebar ────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] .stTextInput input {
    font-size: 0.85rem !important;
    border-radius: 8px !important;
}
section[data-testid="stSidebar"] .stExpander {
    border: 1px solid rgba(128,128,128,0.12) !important;
    border-radius: 8px !important;
    margin-bottom: 0.3rem !important;
}

/* ── Footer ─────────────────────────────────────────────────────── */
.app-footer {
    text-align: center;
    padding: 2rem 0 0.5rem 0;
    border-top: 1px solid rgba(128,128,128,0.1);
    margin-top: 2rem;
}
.app-footer span {
    font-size: 0.75rem;
    color: rgba(128,128,128,0.5);
    letter-spacing: 0.03em;
}

/* ── Polished workspace UI ───────────────────────────────────────── */
.app-header {
    flex-wrap: wrap;
    row-gap: 0.25rem;
    padding: 0.45rem 0 1rem;
}
.app-header .title { font-size: clamp(1.45rem, 2.5vw, 1.9rem); }
.app-header .subtitle {
    flex-basis: 100%;
    margin-left: 2.45rem;
    margin-top: -0.3rem;
    color: var(--text-color, rgba(128,128,128,0.75));
    opacity: 0.72;
    font-size: 0.88rem;
}
.connection-strip {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    margin: 0.8rem 0 1.15rem;
    padding: 0.65rem 0.8rem;
    border: 1px solid rgba(128,128,128,0.18);
    border-radius: 12px;
    background: rgba(128,128,128,0.045);
    font-size: 0.8rem;
}
.connection-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.24rem 0.55rem;
    border-radius: 7px;
    background: rgba(128,128,128,0.08);
}
.connection-chip strong { font-weight: 700; }
.connection-chip.connected { color: #16845b; background: rgba(22,132,91,0.10); }
.connection-chip.write-mode { color: #b45309; background: rgba(245,158,11,0.13); }
.workspace-label {
    margin: 0.2rem 0 0.35rem;
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    opacity: 0.62;
}
.editor-help {
    padding: 0.45rem 0.7rem;
    border-left: 3px solid rgba(102,126,234,0.7);
    border-radius: 0 7px 7px 0;
    background: rgba(102,126,234,0.06);
    font-size: 0.82rem;
    opacity: 0.84;
}
.stTextArea textarea { min-height: 150px; }
.stSelectbox [data-baseweb="select"] > div,
.stTextInput input,
.stNumberInput input,
.stTextArea textarea {
    border-radius: 10px !important;
}
.stAlert { border-radius: 10px !important; }
.stTabs [data-baseweb="tab-list"] { margin-bottom: 0.4rem; }
.stTabs [data-baseweb="tab"] { min-height: 2.7rem; }
[data-testid="stMetric"] {
    padding: 0.7rem 0.8rem;
    border: 1px solid rgba(128,128,128,0.15);
    border-radius: 10px;
    background: rgba(128,128,128,0.035);
}
[data-testid="stProgressBar"] { margin-top: 0.55rem; }

@media (max-width: 760px) {
    .block-container { padding: 0.8rem 0.85rem 2rem !important; }
    .app-header .subtitle { margin-left: 0; }
    .app-header .badge { margin-left: 0; }
    .connection-strip { gap: 0.35rem; padding: 0.55rem; }
    .sql-display { overflow-x: auto; }
    .sql-display .line { font-size: 0.76rem; }
    .pipeline { gap: 0.2rem; }
    .pipeline .step { font-size: 0.7rem; }
    .stTabs [data-baseweb="tab"] { padding: 0.5rem 0.7rem; }
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar: Connection ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔌 Connection")
    dbname = st.text_input("Database", "practice")
    host = st.text_input("Host", "", help="Leave empty inside WSL to use the local socket")
    port = st.text_input("Port", "5432")
    user = st.text_input("User", "", help="Leave empty to use your Linux username")
    password = st.text_input("Password", "", type="password")
    allow_database_changes = st.checkbox(
        "Allow data-changing SQL",
        value=False,
        key="allow_database_changes",
        help="Enables INSERT, UPDATE, DELETE, DDL, and other non-read-only statements. Leave off while learning.",
    )
    if allow_database_changes:
        st.warning(
            "Write access is enabled. Successful statements are committed individually; "
            "this app is not a database backup or transaction manager."
        )


def connect(dbname, host, port, user, password):
    """Create a connection for this Streamlit session (never globally share it)."""
    kwargs = {
        "dbname": dbname,
        "autocommit": True,
        "connect_timeout": 5,
        "application_name": "SQL Visualizer",
        "options": (
            f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
            f"-c lock_timeout={LOCK_TIMEOUT_MS}"
        ),
    }
    if host.strip():
        kwargs["host"] = host.strip()
    if port.strip():
        try:
            kwargs["port"] = int(port)
        except ValueError as exc:
            raise ValueError("Port must be an integer.") from exc
    if user.strip():
        kwargs["user"] = user.strip()
    if password:
        kwargs["password"] = password
    return psycopg.connect(**kwargs)


def get_connection(dbname, host, port, user, password):
    """Keep one connection per browser session and reconnect when settings change."""
    config = (dbname, host, port, user, password)
    old_config = st.session_state.get("_sqlviz_connection_config")
    conn = st.session_state.get("_sqlviz_connection")

    if conn is not None and (config != old_config or conn.closed):
        try:
            conn.close()
        except Exception:
            pass
        conn = None

    if conn is None:
        conn = connect(dbname, host, port, user, password)
        st.session_state["_sqlviz_connection"] = conn
        st.session_state["_sqlviz_connection_config"] = config
    return conn


try:
    con = get_connection(dbname, host, port, user, password)
except Exception as e:
    st.error(f"Could not connect: {e}")
    st.stop()

# ── Constants ────────────────────────────────────────────────────────
COLORS = ["blue", "green", "orange", "violet", "red", "gray"]
KEYWORDS = [("SELECT", "SELECT"), ("FROM", "FROM"), ("INNER JOIN", "FROM"),
            ("LEFT JOIN", "FROM"), ("RIGHT JOIN", "FROM"), ("FULL", "FROM"),
            ("CROSS", "FROM"), ("JOIN", "FROM"), ("WHERE", "WHERE"),
            ("GROUP BY", "GROUP"), ("HAVING", "HAVING"),
            ("ORDER BY", "ORDER"), ("LIMIT", "LIMIT")]
NAMES = {"START": "Tables", "FROM": "FROM / JOIN", "WHERE": "WHERE", "GROUP": "GROUP BY",
         "HAVING": "HAVING", "SELECT": "SELECT", "ORDER": "ORDER BY", "LIMIT": "LIMIT",
         "SUBQUERY": "Subquery",
         "SUB_START": "📂 Source", "SUB_FROM": "📂 FROM", "SUB_WHERE": "📂 WHERE",
         "SUB_GROUP": "📂 GROUP", "SUB_HAVING": "📂 HAVING", "SUB_SELECT": "📂 SELECT",
         "SUB_ORDER": "📂 ORDER", "SUB_LIMIT": "📂 LIMIT", "SUB_RESULT": "📂 Result"}
STAGE_ICONS = {"START": "📋", "FROM": "🔗", "WHERE": "🔍", "GROUP": "📦",
               "HAVING": "✂️", "SELECT": "🎯", "ORDER": "↕️", "LIMIT": "✋",
               "SUBQUERY": "🔄",
               "SUB_START": "🔄", "SUB_FROM": "🔄", "SUB_WHERE": "🔄",
               "SUB_GROUP": "🔄", "SUB_HAVING": "🔄", "SUB_SELECT": "🔄",
               "SUB_ORDER": "🔄", "SUB_LIMIT": "🔄", "SUB_RESULT": "🔄"}

EXAMPLES = {
    "Derived Table (Subquery in FROM)": """SELECT AVG(spent)
FROM (
  SELECT customer_id, SUM(total) AS spent
  FROM orders
  GROUP BY customer_id
) AS per_customer;""",
    "Subquery (NOT IN)": """SELECT name FROM customers
WHERE NOT id IN (
  SELECT customer_id FROM orders
);""",
    "Subquery (above average)": """SELECT * FROM orders
WHERE total > (SELECT AVG(total) FROM orders);""",
    "JOIN + GROUP BY + COUNT": """SELECT customers.name, COUNT(orders.id) AS num_orders
FROM customers
LEFT JOIN orders ON orders.customer_id = customers.id
GROUP BY customers.name;""",
    "Simple SELECT": "SELECT * FROM customers;",
    "WHERE filter": """SELECT * FROM orders
WHERE total > 100;""",
    "JOIN only": """SELECT customers.name, orders.total
FROM customers
LEFT JOIN orders ON orders.customer_id = customers.id;""",
    "GROUP BY + HAVING": """SELECT customers.name, SUM(orders.total) AS spent
FROM customers
LEFT JOIN orders ON orders.customer_id = customers.id
GROUP BY customers.name
HAVING SUM(orders.total) > 200;""",
    "ORDER BY + LIMIT": """SELECT customers.name, orders.total
FROM customers
JOIN orders ON orders.customer_id = customers.id
ORDER BY orders.total DESC
LIMIT 3;""",
}


# ── Helpers ──────────────────────────────────────────────────────────
def uniq(cols):
    seen, out = {}, []
    for c in cols:
        n = seen.get(c, 0)
        seen[c] = n + 1
        out.append(c if n == 0 else f"{c}_{n}")
    return out


def quote_ident(identifier):
    """Quote a PostgreSQL identifier safely (identifiers cannot use bind params)."""
    return '"' + str(identifier).replace('"', '""') + '"'


def table_sql(table):
    """Return a safely quoted table reference from a sqlglot Table node."""
    parts = []
    if getattr(table, "db", None):
        parts.append(table.db)  # PostgreSQL schema
    parts.append(table.name)
    return ".".join(quote_ident(part) for part in parts if part)


def qualified_column_sql(table_alias, column_name):
    alias = quote_ident(table_alias)
    column = quote_ident(column_name)
    output_name = quote_ident(f"{table_alias}.{column_name}")
    return f"{alias}.{column} AS {output_name}"


def statement_requires_write_access(statement):
    """Conservatively gate statements that are not plain read-only queries."""
    try:
        parsed = sqlglot.parse_one(statement, read="postgres")
    except Exception:
        # Let PostgreSQL report malformed read queries while transaction-level
        # read-only mode still prevents database changes.
        first_keyword = re.match(r"^\s*([A-Za-z]+)", str(statement))
        return not first_keyword or first_keyword.group(1).upper() not in {
            "SELECT", "WITH", "VALUES", "EXPLAIN", "SHOW", "DESCRIBE"
        }
    if parsed is None:
        return False

    write_nodes = {
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter",
        "TruncateTable", "Command", "Copy", "Transaction", "Commit", "Rollback",
    }
    if any(node.__class__.__name__ in write_nodes for node in parsed.walk()):
        return True

    read_only_roots = {"Select", "Union", "Intersect", "Except", "Values", "Show", "Describe", "Explain"}
    if parsed.__class__.__name__ not in read_only_roots:
        return True
    # SELECT ... FOR UPDATE/SHARE obtains row locks and is not suitable for read-only learning mode.
    if parsed.args.get("locks") or parsed.args.get("lock"):
        return True
    return False


def execute(statement, params=None):
    """Execute one statement in an isolated transaction and cap displayed result rows."""
    if re.match(r"^\s*(BEGIN|START\s+TRANSACTION|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)\b", str(statement), re.I):
        raise ValueError(
            "Transaction-control statements are managed by SQL Visualizer and cannot be run directly."
        )
    allow_writes = st.session_state.get("allow_database_changes", False)
    if not allow_writes and statement_requires_write_access(statement):
        raise PermissionError(
            "This statement may change the database or is not recognized as a read-only query. "
            "Enable **Allow data-changing SQL** in the sidebar to run it."
        )

    try:
        parsed = sqlglot.parse_one(statement, read="postgres")
    except Exception:
        parsed = None
    write_node_names = {
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter",
        "TruncateTable", "Command", "Copy", "Transaction", "Commit", "Rollback",
    }
    can_stream = (
        parsed is not None
        and parsed.__class__.__name__ in {"Select", "Union", "Intersect", "Except", "Values"}
        and not any(node.__class__.__name__ in write_node_names for node in parsed.walk())
        and not parsed.args.get("locks")
        and not parsed.args.get("lock")
    )

    def collect(cursor):
        status = cursor.statusmessage
        if not cursor.description:
            return None, status
        columns = uniq([description.name for description in cursor.description])
        rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
        truncated = len(rows) > MAX_RESULT_ROWS
        if truncated:
            rows = rows[:MAX_RESULT_ROWS]
        frame = pd.DataFrame(rows, columns=columns)
        frame.attrs["truncated"] = truncated
        frame.attrs["row_limit"] = MAX_RESULT_ROWS
        return frame, status

    with con.transaction():
        with con.cursor() as control_cursor:
            if not allow_writes:
                # Enforce read-only behavior at the PostgreSQL transaction level as well.
                control_cursor.execute("SET TRANSACTION READ ONLY")

        if can_stream:
            # A named/server-side cursor avoids buffering an unbounded SELECT result in Python.
            with con.cursor(name=f"sqlviz_{uuid4().hex}") as cursor:
                cursor.execute(statement, params)
                return collect(cursor)

        with con.cursor() as cursor:
            cursor.execute(statement, params)
            return collect(cursor)


def show(df, max_height=400):
    if df is None:
        return
    if df.attrs.get("truncated"):
        st.warning(
            f"Showing the first {df.attrs.get('row_limit', MAX_RESULT_ROWS):,} rows only. "
            "The result was capped to keep the app responsive."
        )
    shown = df.astype("string").fillna("NULL")
    sty = shown.style.apply(
        lambda col: ["background-color: rgba(255,193,7,0.25)" if v == "NULL" else "" for v in col]
    )
    st.dataframe(
        sty,
        hide_index=True,
        use_container_width=True,
        height=min(max_height, 38 + 35 * len(df)),
    )


def clause_of(line, last):
    # Only top-level lines (no leading indentation) define the outer SQL clause
    if not line.startswith(" ") and not line.startswith("\t"):
        stripped = line.strip()
        for kw, name in KEYWORDS:
            if stripped.upper().startswith(kw):
                return name
    return last


def build(ast, items, keep):
    q = ast.copy()
    if items:
        q.set("expressions", sqlglot.parse_one("SELECT " + ", ".join(items), read="postgres").expressions)
        q.args.pop("distinct", None)
    for k in ["where", "group", "having", "order", "limit"]:
        if k not in keep:
            q.args.pop(k, None)
    return q.sql(dialect="postgres")


def norm(v):
    return None if pd.isna(v) else v


def render_pipeline(stages, step):
    parts = []
    for i, s in enumerate(stages):
        state_cls = "active" if i == step else ("done" if i < step else "")
        stage_key = s[1]
        is_sub = stage_key.startswith("SUB_")
        type_cls = "sub" if is_sub else ""
        label = NAMES.get(stage_key, stage_key)
        icon = STAGE_ICONS.get(stage_key, "🔹")
        parts.append(f'<span class="step {state_cls} {type_cls}">{icon} {label}</span>')
        if i < len(stages) - 1:
            parts.append('<span class="arrow">▸</span>')
    st.markdown(f'<div class="pipeline">{"".join(parts)}</div>', unsafe_allow_html=True)


def expand_subquery_stages(raw_sql, context_clause, is_derived=False, alias=None):
    """Break a subquery into its own mini-pipeline of SUB_ stages."""
    try:
        sub_ast = sqlglot.parse_one(raw_sql, read="postgres")
    except Exception:
        # Fallback: single SUBQUERY stage if parse fails
        return [("Subquery", "SUBQUERY", raw_sql,
                 {"clause": context_clause, "raw_sql": raw_sql,
                  "is_derived_table": is_derived, "alias": alias})]

    sub_has = {k: bool(sub_ast.args.get(k)) for k in ["where", "group", "having", "order", "limit"]}
    has_join = bool(sub_ast.args.get("joins"))

    # Collect tables in this subquery
    sub_from = sub_ast.args.get("from_") or sub_ast.args.get("from")
    sub_tables = []
    if sub_from:
        sub_tables = [sub_from.this] + [j.this for j in (sub_ast.args.get("joins") or [])]

    # Build column references for intermediate queries
    sub_cols = []
    for t in sub_tables:
        if isinstance(t, exp.Table):
            ref = t.alias_or_name
            try:
                sample, _ = execute(f"SELECT * FROM {table_sql(t)} LIMIT 0")
                if sample is not None:
                    for c in sample.columns:
                        sub_cols.append(qualified_column_sql(ref, c))
            except Exception:
                pass

    sub_keys = [e.sql(dialect="postgres") for e in sub_ast.args["group"].expressions] if sub_has["group"] else []
    sub_gitems = [f'{k} AS "__g{i}"' for i, k in enumerate(sub_keys)]
    sub_gcols = [f"__g{i}" for i in range(len(sub_keys))]

    label_prefix = "Subquery" if not is_derived else f"Derived table {alias or 'sub'}"
    base_meta = {"clause": context_clause, "raw_sql": raw_sql,
                 "is_derived_table": is_derived, "alias": alias}

    stages = []

    # SUB_FROM: load source tables
    from_sql = build(sub_ast, sub_cols if sub_cols else None, [])
    from_lbl = "JOIN source tables" if has_join else "Load source table"
    stages.append((f"{label_prefix} → {from_lbl}", "SUB_FROM", from_sql,
                   {**base_meta, "sub_ast": sub_ast, "sub_tables": sub_tables, "has_join": has_join,
                    "sub_clause": "FROM"}))

    # SUB_WHERE
    if sub_has["where"]:
        where_sql = build(sub_ast, sub_cols if sub_cols else None, ["where"])
        stages.append((f"{label_prefix} → Filter rows", "SUB_WHERE", where_sql,
                       {**base_meta, "sub_ast": sub_ast, "sub_clause": "WHERE"}))

    # SUB_GROUP
    sub_gsql = None
    if sub_has["group"]:
        sub_gsql = build(sub_ast, sub_gitems + (sub_cols if sub_cols else []), ["where"])
        stages.append((f"{label_prefix} → Group rows", "SUB_GROUP", sub_gsql,
                       {**base_meta, "sub_ast": sub_ast, "sub_gcols": sub_gcols,
                        "sub_clause": "GROUP"}))

        # SUB_HAVING
        if sub_has["having"]:
            having_sql = build(sub_ast, sub_gitems, ["where", "group", "having"])
            stages.append((f"{label_prefix} → Filter groups", "SUB_HAVING", having_sql,
                           {**base_meta, "sub_ast": sub_ast, "sub_gcols": sub_gcols,
                            "sub_gsql": sub_gsql, "sub_clause": "HAVING"}))

    # SUB_SELECT
    select_sql = build(sub_ast, None, ["where", "group", "having"])
    stages.append((f"{label_prefix} → Pick columns", "SUB_SELECT", select_sql,
                   {**base_meta, "sub_ast": sub_ast, "sub_clause": "SELECT"}))

    # SUB_ORDER
    if sub_has["order"]:
        order_sql = build(sub_ast, None, ["where", "group", "having", "order"])
        stages.append((f"{label_prefix} → Sort rows", "SUB_ORDER", order_sql,
                       {**base_meta, "sub_ast": sub_ast, "sub_clause": "ORDER"}))

    # SUB_LIMIT
    if sub_has["limit"]:
        limit_sql = build(sub_ast, None, ["where", "group", "having", "order", "limit"])
        stages.append((f"{label_prefix} → Limit rows", "SUB_LIMIT", limit_sql,
                       {**base_meta, "sub_ast": sub_ast, "sub_clause": "LIMIT"}))

    # SUB_RESULT: show the final subquery result with context of how it's used
    stages.append((f"{label_prefix} → Final result", "SUB_RESULT", raw_sql,
                   {**base_meta, "sub_ast": sub_ast, "sub_clause": "RESULT"}))

    return stages


def render_sql(ast_node, active, sub_sql=None, sub_clause=None):
    rows = []
    lines = ast_node.sql(dialect="postgres", pretty=True).split("\n")

    if active.startswith("SUB_") and sub_sql:
        # ── Sub-stage highlighting: find the subquery lines, then
        #    highlight only the clause within those lines ──
        hl_set = set()
        try:
            sub_ast = sqlglot.parse_one(sub_sql, read="postgres")
            sub_lines = sub_ast.sql(dialect="postgres", pretty=True).split("\n")
            sub_stripped = [l.strip() for l in sub_lines]

            # Find where the subquery lives in the full SQL
            sub_start = -1
            for start in range(len(lines) - len(sub_stripped) + 1):
                if all(lines[start + j].strip() == sub_stripped[j]
                       for j in range(len(sub_stripped))):
                    sub_start = start
                    break

            if sub_start >= 0:
                sub_end = sub_start + len(sub_stripped)
                inner_clause = sub_clause  # e.g. "FROM", "WHERE", "GROUP", "SELECT"

                if inner_clause == "RESULT":
                    # Highlight all subquery lines
                    hl_set = set(range(sub_start, sub_end))
                else:
                    # Map SUB_clause back to the clause keyword for clause_of()
                    clause_map = {"FROM": "FROM", "WHERE": "WHERE", "GROUP": "GROUP",
                                  "HAVING": "HAVING", "SELECT": "SELECT",
                                  "ORDER": "ORDER", "LIMIT": "LIMIT"}
                    target_clause = clause_map.get(inner_clause, inner_clause)

                    # Walk only the subquery lines and highlight the matching clause
                    last = ""
                    for idx in range(sub_start, sub_end):
                        line = lines[idx]
                        stripped = line.strip()
                        # clause_of needs non-indented lines; inside subquery everything
                        # is indented, so strip to get the keyword
                        for kw, name in KEYWORDS:
                            if stripped.upper().startswith(kw):
                                last = name
                                break
                        if last == target_clause:
                            hl_set.add(idx)
        except Exception:
            pass

        for i, line in enumerate(lines):
            cls = "line hl" if i in hl_set else "line"
            rows.append(f'<div class="{cls}">{html.escape(line)}</div>')

    elif active == "SUBQUERY" and sub_sql:
        # ── Legacy single-step subquery highlighting ──
        hl_set = set()
        try:
            sub_ast = sqlglot.parse_one(sub_sql, read="postgres")
            sub_lines = sub_ast.sql(dialect="postgres", pretty=True).split("\n")
            sub_stripped = [l.strip() for l in sub_lines]
            for start in range(len(lines) - len(sub_stripped) + 1):
                if all(
                    lines[start + j].strip() == sub_stripped[j]
                    for j in range(len(sub_stripped))
                ):
                    hl_set = set(range(start, start + len(sub_stripped)))
                    break
        except Exception:
            pass

        for i, line in enumerate(lines):
            cls = "line hl" if i in hl_set else "line"
            rows.append(f'<div class="{cls}">{html.escape(line)}</div>')
    else:
        # ── Outer clause highlighting with cumulative depth tracking ──
        last = ""
        depth = 0
        for line in lines:
            last = clause_of(line, last)
            depth_start = depth
            for ch in line:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            depth_end = depth

            is_hl = False
            if last == active:
                # Highlight only when NOT fully inside a nested subquery
                if depth_start == 0 or depth_end == 0:
                    is_hl = True

            cls = "line hl" if is_hl else "line"
            rows.append(f'<div class="{cls}">{html.escape(line)}</div>')

    st.markdown(f'<div class="sql-display">{"".join(rows)}</div>', unsafe_allow_html=True)


def render_stage_header(step_num, title):
    # Dynamic identifiers embedded in stage titles are escaped at their call sites;
    # retaining trusted <code> markup here keeps derived-table labels readable.
    st.markdown(f'''<div class="stage-header">
        <div class="num">{step_num}</div>
        <div class="label">{title}</div>
    </div>''', unsafe_allow_html=True)


def piles(df, gcols, survivors=None):
    groups = list(df.groupby(gcols, dropna=False, sort=False))
    if not groups:
        st.info("No rows reached this stage.")
        return
    # Use 2 columns so tables have enough width to show all data
    ncols = min(2, len(groups))
    # Process groups in rows of ncols
    for row_start in range(0, len(groups), ncols):
        row_groups = groups[row_start:row_start + ncols]
        ui = st.columns(ncols)
        for col_idx, (key, part) in enumerate(row_groups):
            key = key if isinstance(key, tuple) else (key,)
            label = ", ".join("NULL" if pd.isna(k) else str(k) for k in key)
            i = row_start + col_idx
            tag = ""
            if survivors is not None:
                tag = "  :green[kept]" if tuple(norm(k) for k in key) in survivors else "  :red[dropped]"
            with ui[col_idx]:
                with st.container(border=True):
                    st.markdown(f":{COLORS[i % len(COLORS)]}-background[**{html.escape(label)}**]  {len(part)} row(s){tag}")
                    show(part.drop(columns=gcols).reset_index(drop=True))


class SkipStepTab(Exception):
    """Exit the step-by-step tab without stopping the remainder of the app."""


# ── Header ───────────────────────────────────────────────────────────
st.markdown('''<div class="app-header">
    <span class="icon">⚡</span>
    <span class="title">SQL Visualizer</span>
    <span class="badge">Interactive learning</span>
    <span class="subtitle">Explore how PostgreSQL transforms rows, one stage at a time.</span>
</div>''', unsafe_allow_html=True)

host_label = host.strip() or "Default / local socket"
access_label = "Write access enabled" if allow_database_changes else "Read-only mode"
access_class = "write-mode" if allow_database_changes else "connected"
st.markdown(
    f'''<div class="connection-strip">
        <span class="connection-chip connected">● Connected</span>
        <span class="connection-chip"><strong>Database</strong> {html.escape(dbname)}</span>
        <span class="connection-chip"><strong>Host</strong> {html.escape(host_label)}</span>
        <span class="connection-chip"><strong>Port</strong> {html.escape(port)}</span>
        <span class="connection-chip {access_class}"><strong>Access</strong> {html.escape(access_label)}</span>
    </div>''',
    unsafe_allow_html=True,
)

# ── Example query dropdown + editor ──────────────────────────────────
st.markdown('<div class="workspace-label">01 / Query workspace</div>', unsafe_allow_html=True)
col_ex, col_hint = st.columns([3, 5])
with col_ex:
    example = st.selectbox(
        "Start from an example",
        ["— Custom query —"] + list(EXAMPLES.keys()),
        help="Choose a sample query to prefill the editor.",
    )
with col_hint:
    st.markdown(
        '<div class="editor-help">Tip: use <b>Step by Step</b> to inspect each stage, or <b>Run SQL</b> to execute the full statement.</div>',
        unsafe_allow_html=True,
    )

if example != st.session_state.get("_last_example"):
    st.session_state["_last_example"] = example
    if example != "— Custom query —":
        st.session_state["_query_text"] = EXAMPLES[example]
        # Update the keyed widget before it is instantiated on the next rerun.
        st.session_state["sql_query_editor"] = EXAMPLES[example]
        st.rerun()

default_q = st.session_state.get("_query_text", list(EXAMPLES.values())[0])
query = st.text_area("SQL editor", default_q, height=165, key="sql_query_editor", help="Step-by-step mode supports a single SELECT query. PostgreSQL syntax is expected.")

if st.session_state.get("last_query") != query:
    st.session_state.last_query = query
    st.session_state.step = 0

# ── Tabs ─────────────────────────────────────────────────────────────
run_tab, step_tab = st.tabs(["⚡ Run SQL", "📖 Step by Step"])

# ── Run SQL tab ──────────────────────────────────────────────────────
with run_tab:
    run_col, run_note = st.columns([1.5, 5])
    with run_col:
        run_query_clicked = st.button("▶ Run query", type="primary", use_container_width=True)
    with run_note:
        st.caption(
            "Runs statements in order. Read-only mode is on by default; enable **Allow data-changing SQL** "
            "in the sidebar only when you intend to write to the database."
        )
    if run_query_clicked:
        for stmt in sqlparse.split(query):
            if not stmt.strip(" ;\n\t"):
                continue
            st.code(stmt.strip(), language="sql")
            try:
                df, msg = execute(stmt)
                if df is not None:
                    show(df)
                    st.markdown(f'<div class="row-count">📊 {len(df)} row(s)</div>', unsafe_allow_html=True)
                else:
                    st.success(msg)
            except Exception as e:
                st.error(str(e))
                break

# ── Step by Step tab ─────────────────────────────────────────────────
with step_tab:
    try:
        stmts = [s for s in sqlparse.split(query) if s.strip(" ;\n\t")]
        if len(stmts) != 1:
            st.info("Step-by-step works on a single SELECT query. Use the **Run SQL** tab for everything else.")
            raise SkipStepTab()
        ast = sqlglot.parse_one(stmts[0], read="postgres")
        if not isinstance(ast, exp.Select):
            st.info("Step-by-step works on **SELECT** queries. Use the **Run SQL** tab for this one.")
            raise SkipStepTab()
        from_node = ast.args.get("from_") or ast.args.get("from")
        outer_tables = [from_node.this] + [j.this for j in (ast.args.get("joins") or [])]
        supported_sources = (exp.Table, exp.Subquery)
        if not all(isinstance(t, supported_sources) for t in outer_tables):
            st.info("Complex expressions in FROM or JOIN aren't supported yet.")
            raise SkipStepTab()

        # ── Find all physical tables across the entire query (including inside subqueries) ──
        all_tables = []
        seen_table_names = set()
        for t in ast.find_all(exp.Table):
            t_name = t.name
            if t_name and t_name.lower() not in seen_table_names:
                seen_table_names.add(t_name.lower())
                all_tables.append(t)

        # ── Extract columns and subqueries for each outer source ────────
        cols = []
        from_subqueries = []
        for t in outer_tables:
            if isinstance(t, exp.Subquery):
                alias = t.alias or "sub"
                sub_sql = t.this.sql(dialect="postgres")
                from_subqueries.append((alias, sub_sql))
                sample, _ = execute(f"SELECT * FROM ({sub_sql}) AS {quote_ident(alias)} LIMIT 0")
                if sample is not None:
                    for c in sample.columns:
                        cols.append(f'{alias}."{c}" AS "{alias}.{c}"')
            else:
                ref = t.alias_or_name
                sample, _ = execute(f"SELECT * FROM {table_sql(t)} LIMIT 0")
                if sample is not None:
                    for c in sample.columns:
                        cols.append(qualified_column_sql(ref, c))

        has = {k: bool(ast.args.get(k)) for k in ["where", "group", "having", "order", "limit"]}
        has_join = bool(ast.args.get("joins"))
        is_star = any(isinstance(e, exp.Star) for e in ast.expressions)
        keys = [e.sql(dialect="postgres") for e in ast.args["group"].expressions] if has["group"] else []
        gitems = [f'{k} AS "__g{i}"' for i, k in enumerate(keys)]
        gcols = [f"__g{i}" for i in range(len(keys))]

        # ── Find subqueries in clauses ─────────────────────────────
        where_node = ast.args.get("where")
        where_subqueries = []
        if where_node:
            for s in where_node.find_all(exp.Select):
                where_subqueries.append(s)

        having_node = ast.args.get("having")
        having_subqueries = []
        if having_node:
            for s in having_node.find_all(exp.Select):
                having_subqueries.append(s)

        select_subqueries = []
        for expr in ast.expressions:
            for s in expr.find_all(exp.Select):
                if s is not ast:
                    select_subqueries.append(s)

        # ── Build stages with context-aware titles ────────────────────
        from_label = "FROM / JOIN" if has_join else "FROM"
        NAMES["FROM"] = from_label

        if has_join:
            from_title = "Glue the tables together"
        else:
            first_src = outer_tables[0]
            if isinstance(first_src, exp.Subquery):
                tname = first_src.alias or "derived table"
                from_title = f"Load derived table {tname}"
            else:
                tname = first_src.alias_or_name
                from_title = f"Load the {tname} table"

        # ── Build dynamic stages in logical execution order ───────────
        stages = [("The raw tables", "START", None, {})]

        # 1. Any Subqueries in FROM or JOIN must run FIRST to create derived tables!
        for alias, sub_sql in from_subqueries:
            stages.extend(expand_subquery_stages(
                sub_sql, context_clause=f"FROM ({alias})",
                is_derived=True, alias=alias))

        stages.append((from_title, "FROM", build(ast, cols, []), {}))

        # 2. Subqueries in WHERE run BEFORE WHERE evaluates!
        for i, sq in enumerate(where_subqueries):
            sq_sql = sq.sql(dialect="postgres")
            stages.extend(expand_subquery_stages(
                sq_sql, context_clause="WHERE"))

        if has["where"]:
            stages.append(("Keep only matching rows", "WHERE", build(ast, cols, ["where"]), {}))

        gsql = None
        if has["group"]:
            gsql = build(ast, gitems + cols, ["where"])
            stages.append(("Make one pile per key", "GROUP", gsql, {}))

            # 3. Subqueries in HAVING run BEFORE HAVING evaluates!
            for i, sq in enumerate(having_subqueries):
                sq_sql = sq.sql(dialect="postgres")
                stages.extend(expand_subquery_stages(
                    sq_sql, context_clause="HAVING"))

            if has["having"]:
                stages.append(("Keep or drop whole piles", "HAVING",
                               build(ast, gitems, ["where", "group", "having"]), {}))

        # 4. Subqueries in SELECT expressions
        for i, sq in enumerate(select_subqueries):
            sq_sql = sq.sql(dialect="postgres")
            stages.extend(expand_subquery_stages(
                sq_sql, context_clause="SELECT"))

        base = ["where", "group", "having"]
        stages.append(("Pick the columns", "SELECT", build(ast, None, base), {}))

        if has["order"]:
            stages.append(("Sort the rows", "ORDER", build(ast, None, base + ["order"]), {}))
        if has["limit"]:
            stages.append(("Keep the first N rows", "LIMIT", build(ast, None, base + ["order", "limit"]), {}))

        n = len(stages)
        st.session_state.step = max(0, min(n - 1, st.session_state.get("step", 0)))
        step = st.session_state.step
        stage_item = stages[step]
        title = stage_item[0]
        active = stage_item[1]
        sql = stage_item[2]
        meta = stage_item[3] if len(stage_item) > 3 else {}

        # ── Navigation ───────────────────────────────────────────────
        def go(d):
            st.session_state.step = max(0, min(n - 1, st.session_state.step + d))

        def restart():
            st.session_state.step = 0

        render_pipeline(stages, step)

        nav1, nav2, nav3, nav4 = st.columns([1.1, 1.1, 3.8, 2.0])
        with nav1:
            st.button("← Back", on_click=go, args=(-1,), disabled=step == 0, use_container_width=True)
        with nav2:
            if step < n - 1:
                st.button("Next →", on_click=go, args=(1,), type="primary", use_container_width=True)
            else:
                st.button("↺ Restart", on_click=restart, use_container_width=True)
        with nav3:
            st.progress((step + 1) / n, text=f"Step {step + 1} of {n}")
        with nav4:
            is_side_by_side = st.toggle("Side-by-side", value=st.session_state.get("side_by_side", True), key="side_by_side", help="Show query on left and output on right")

        # Helper: run a stage query with learner-friendly error messages
        def run_stage(stage_sql):
            try:
                return execute(stage_sql)
            except Exception as exc:
                msg = str(exc)
                # ── Friendly hints for common mistakes ────────────
                table_names = [t.alias_or_name for t in all_tables]
                if "missing FROM-clause entry for table" in msg:
                    # Extract the bad table name from the error
                    import re
                    m = re.search(r'table "([^"]+)"', msg)
                    bad = m.group(1) if m else None
                    if bad:
                        close = difflib.get_close_matches(bad, table_names, n=1, cutoff=0.5)
                        hint = f'\n\n💡 **Did you mean `{close[0]}`?** Check spelling — your tables are: {", ".join(f"`{t}`" for t in table_names)}' if close else ""
                        st.error(f'**Table not found:** `{bad}` is not in the FROM clause.{hint}')
                    else:
                        st.error(msg)
                elif 'column "' in msg and "does not exist" in msg:
                    st.error(f"**Column not found.** {msg}\n\n💡 Check the column name and table prefix. "
                             f"Available tables: {', '.join(f'`{t}`' for t in table_names)}")
                elif "syntax error" in msg.lower():
                    st.error(f"**SQL syntax error.** {msg}\n\n💡 Double-check keywords, commas, and parentheses.")
                else:
                    st.error(msg)
                return None, None


        if is_side_by_side:
            col_sql, col_stage = st.columns([5, 7], gap="large")
        else:
            col_sql = st.container()
            col_stage = st.container()

        # ── SQL display (Left column in side-by-side mode) ───────────
        with col_sql:
            st.markdown(
                f'<div class="sticky-query">'
                f'<div class="query-panel-header">'
                f'<span>📝 Query Code</span>'
                f'<span class="query-active-badge">⚡ {NAMES.get(active, active)}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            render_sql(ast, active, meta.get("raw_sql"), meta.get("sub_clause"))
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Stage result (Right column in side-by-side mode) ──────────
        with col_stage:
            render_stage_header(step + 1, f"{NAMES.get(active, active)}: {title}")
            try:
                if active == "START":
                    st.caption("These are all the source tables your query will work with (including subqueries).")
                    ncols = min(2, len(all_tables)) if is_side_by_side else min(2 if len(all_tables) in (2, 4) else 3, len(all_tables))
                    for row_start in range(0, len(all_tables), ncols):
                        row_tables = all_tables[row_start:row_start + ncols]
                        ui = st.columns(len(row_tables))
                        for u, t in zip(ui, row_tables):
                            with u:
                                st.markdown(f"**`{t.name}`**")
                                result = run_stage(f"SELECT * FROM {table_sql(t)} ORDER BY 1")
                                if result[0] is not None:
                                    show(result[0])
                elif active == "FROM":
                    if has_join:
                        st.caption("FROM picks the source tables. JOIN glues matching rows together "
                                   "— look for NULLs where a row had no match.")
                    elif from_subqueries:
                        st.caption("FROM loads the rows from the derived table produced in the previous step.")
                    else:
                        st.caption("FROM picks the source table. With only one table, "
                                   "this step just loads all its rows.")
                    result = run_stage(sql)
                    if result[0] is not None:
                        df = result[0]
                        if not has["order"] and len(df.columns) > 0:
                            df = df.sort_values(df.columns[0]).reset_index(drop=True)
                        show(df)
                        st.markdown(f'<div class="row-count">📊 {len(df)} row(s)</div>', unsafe_allow_html=True)
                elif active.startswith("SUB_"):
                    # ── Subquery sub-step rendering ──
                    sub_clause = meta.get("sub_clause", "")
                    clause_name = meta.get("clause", "outer query")
                    is_derived = meta.get("is_derived_table", False)
                    alias_name = meta.get("alias", "sub")
                    sub_tables_list = meta.get("sub_tables", [])

                    # Context banner
                    if is_derived:
                        ctx = f"🔄 **Inner query** for derived table **`{alias_name}`** (used in outer FROM)"
                    else:
                        ctx = f"🔄 **Inner query** for the **{clause_name}** clause"
                    st.info(ctx)

                    if active == "SUB_FROM":
                        sub_has_join = meta.get("has_join", False)
                        if sub_has_join:
                            st.caption("The subquery's FROM loads its source tables and JOINs them.")
                        else:
                            st.caption("The subquery's FROM loads its source table.")
                        result = run_stage(sql)
                        if result[0] is not None:
                            df = result[0]
                            if len(df.columns) > 0:
                                df = df.sort_values(df.columns[0]).reset_index(drop=True)
                            show(df)
                            st.markdown(f'<div class="row-count">📊 {len(df)} row(s)</div>', unsafe_allow_html=True)

                    elif active == "SUB_WHERE":
                        st.caption("The subquery's WHERE filters rows that don't match.")
                        result = run_stage(sql)
                        if result[0] is not None:
                            df = result[0]
                            if len(df.columns) > 0:
                                df = df.sort_values(df.columns[0]).reset_index(drop=True)
                            show(df)
                            st.markdown(f'<div class="row-count">📊 {len(df)} row(s) after filter</div>', unsafe_allow_html=True)

                    elif active == "SUB_GROUP":
                        st.caption("The subquery's GROUP BY gathers rows into piles by key.")
                        sub_gcols_list = meta.get("sub_gcols", [])
                        result = run_stage(sql)
                        if result[0] is not None:
                            if sub_gcols_list:
                                piles(result[0], sub_gcols_list)
                            else:
                                show(result[0])

                    elif active == "SUB_HAVING":
                        st.caption("The subquery's HAVING keeps or drops entire piles.")
                        sub_gcols_list = meta.get("sub_gcols", [])
                        sub_gsql_val = meta.get("sub_gsql")
                        kept_result = run_stage(sql)
                        if kept_result[0] is not None and sub_gcols_list and sub_gsql_val:
                            survivors = {tuple(norm(v) for v in r) for r in kept_result[0].itertuples(index=False)}
                            gsql_result = run_stage(sub_gsql_val)
                            if gsql_result[0] is not None:
                                piles(gsql_result[0], sub_gcols_list, survivors)
                        elif kept_result[0] is not None:
                            show(kept_result[0])

                    elif active == "SUB_SELECT":
                        st.caption("The subquery's SELECT picks the final columns.")
                        result = run_stage(sql)
                        if result[0] is not None:
                            df = result[0]
                            if len(df.columns) > 0:
                                df = df.sort_values(df.columns[0]).reset_index(drop=True)
                            show(df)
                            st.markdown(f'<div class="row-count">📊 {len(df)} row(s)</div>', unsafe_allow_html=True)

                    elif active in ("SUB_ORDER", "SUB_LIMIT"):
                        label = "sorted" if active == "SUB_ORDER" else "limited"
                        st.caption(f"The subquery's rows are {label}.")
                        result = run_stage(sql)
                        if result[0] is not None:
                            show(result[0])
                            st.markdown(f'<div class="row-count">📊 {len(result[0])} row(s)</div>', unsafe_allow_html=True)

                    elif active == "SUB_RESULT":
                        result = run_stage(sql)
                        if result[0] is not None:
                            sub_df = result[0]
                            if is_derived:
                                st.caption(f"This is the final result of the inner query — the outer query will use it as table `{alias_name}`.")
                                show(sub_df)
                                safe_alias = html.escape(str(alias_name), quote=True)
                                st.markdown(
                                    f'<div class="row-count">📊 {len(sub_df)} row(s) in derived table <code>{safe_alias}</code></div>',
                                    unsafe_allow_html=True,
                                )
                            elif len(sub_df) == 1 and len(sub_df.columns) == 1:
                                val = sub_df.iloc[0, 0]
                                col_name = sub_df.columns[0]
                                try:
                                    fmt_val = f"{float(val):.2f}" if isinstance(val, (int, float)) or (isinstance(val, str) and val.replace('.', '', 1).isdigit()) else str(val)
                                except Exception:
                                    fmt_val = str(val)
                                safe_value = html.escape(fmt_val, quote=True)
                                safe_column = html.escape(str(col_name), quote=True)
                                st.markdown(f"""
                                <div style="background: rgba(255,152,0,0.12); border: 2px solid rgba(255,152,0,0.35); border-radius: 12px; padding: 1.2rem; margin: 1rem 0; text-align: center;">
                                    <div style="font-size: 0.8rem; font-weight: 700; color: rgba(128,128,128,0.8); text-transform: uppercase; letter-spacing: 0.05em;">Subquery Result</div>
                                    <div style="font-size: 2.2rem; font-weight: 800; color: #ff9800; margin: 0.3rem 0;">{safe_value}</div>
                                    <div style="font-size: 0.85rem; color: rgba(128,128,128,0.7);">From column: <code>{safe_column}</code></div>
                                </div>
                                """, unsafe_allow_html=True)
                                st.caption(
                                    f"Next: the outer {clause_name} clause uses the scalar subquery result in its condition."
                                )
                            else:
                                st.caption(f"This is the set of values the outer `{clause_name}` clause will use.")
                                show(sub_df)
                                st.markdown(f'<div class="row-count">📊 {len(sub_df)} row(s) returned by subquery</div>', unsafe_allow_html=True)

                elif active == "SUBQUERY":
                    # Legacy fallback (shouldn't normally reach here now)
                    clause_name = meta.get("clause", "outer query")
                    st.info(f"🔄 Subquery for **{clause_name}**")
                    st.code(sql, language="sql")
                    result = run_stage(sql)
                    if result[0] is not None:
                        show(result[0])
                elif active == "WHERE":
                    if where_subqueries:
                        st.caption("Rows that don't match the condition are removed. (Filtered using the subquery result computed in the previous step!)")
                    else:
                        st.caption("Rows that don't match the condition are removed.")
                    result = run_stage(sql)
                    if result[0] is not None:
                        df = result[0]
                        if not has["order"] and len(df.columns) > 0:
                            df = df.sort_values(df.columns[0]).reset_index(drop=True)
                        show(df)
                        st.markdown(f'<div class="row-count">📊 {len(df)} row(s)</div>', unsafe_allow_html=True)
                elif active == "GROUP":
                    result = run_stage(sql)
                    if result[0] is not None:
                        piles(result[0], gcols)
                elif active == "HAVING":
                    kept_result = run_stage(sql)
                    if kept_result[0] is not None:
                        survivors = {tuple(norm(v) for v in r) for r in kept_result[0].itertuples(index=False)}
                        gsql_result = run_stage(gsql)
                        if gsql_result[0] is not None:
                            piles(gsql_result[0], gcols, survivors)
                elif active == "SELECT":
                    result = run_stage(sql)
                    if result[0] is not None:
                        df = result[0]
                        if not has["order"] and len(df.columns) > 0:
                            df = df.sort_values(df.columns[0]).reset_index(drop=True)
                        if is_star:
                            st.caption("`*` means \"all columns\" — every column is kept, "
                                       "so the data looks the same as the previous step.")
                        if has_join:
                            st.caption("💡 Table prefixes (e.g. `orders.id`) are dropped in the final output — "
                                       "the database only needed them to tell columns apart during the JOIN.")
                        show(df)
                        st.markdown(f'<div class="row-count">📊 {len(df)} row(s)</div>', unsafe_allow_html=True)
                else:
                    result = run_stage(sql)
                    if result[0] is not None:
                        df = result[0]
                        if not has["order"] and len(df.columns) > 0 and active not in ("ORDER", "LIMIT"):
                            df = df.sort_values(df.columns[0]).reset_index(drop=True)
                        show(df)
                        st.markdown(f'<div class="row-count">📊 {len(df)} row(s)</div>', unsafe_allow_html=True)

                if sql:
                    with st.expander("🔧 SQL executed for this stage"):
                        st.code(sql, language="sql")

            except Exception as e:
                st.error(f"Unexpected error: {e}")

        # ── Run full query inside step tab ────────────────────────────
        st.markdown("---")
        if st.button("▶ Run full query", type="primary", key="step_run"):
            st.code(stmts[0].strip(), language="sql")
            try:
                df, msg = execute(stmts[0])
                if df is not None:
                    show(df)
                    st.markdown(f'<div class="row-count">📊 {len(df)} row(s)</div>', unsafe_allow_html=True)
                else:
                    st.success(msg)
            except Exception as exc:
                st.error(str(exc))

    except SkipStepTab:
        pass
    except Exception as e:
        st.error(str(e))

# ── Sidebar: Table browser ───────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("### 📋 Tables in database")
    try:
        meta, _ = execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() ORDER BY table_name, ordinal_position")
        for tname, part in meta.groupby("table_name", sort=False):
            safe_tname = html.escape(str(tname), quote=True)
            with st.expander(f"📄 {safe_tname}"):
                for _, r in part.iterrows():
                    column_name = html.escape(str(r["column_name"]), quote=True)
                    data_type = html.escape(str(r["data_type"]), quote=True)
                    st.markdown(
                        f"`{column_name}` · <span style='color:rgba(128,128,128,0.6);font-size:0.8rem'>{data_type}</span>",
                        unsafe_allow_html=True,
                    )
    except Exception as e:
        st.error(str(e))

# ── Footer ───────────────────────────────────────────────────────────
st.markdown('<div class="app-footer"><span>⚡ SQL Visualizer · Built for learning</span></div>',
            unsafe_allow_html=True)
