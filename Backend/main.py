"""
SQL Validator API using FastAPI

This module exposes two endpoints:
1. /api/query/validate - Validates SQL syntax against custom business rules.
2. /api/query/suggestfix - Calls DocsBot AI to suggest fixes for SQL queries with issues.

Author: Unionware - Alvin Li
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv
import requests
import os
import re

# ------------------------------
# Environment Setup
# ------------------------------

# Load environment variables from .env (used for DocsBot credentials)
load_dotenv()

# Initialize FastAPI application
app = FastAPI()

# Configure CORS for local frontend development
origins = [
    "http://localhost:5173",  # Vite React dev server
    "http://localhost:3000",  # Optional fallback port
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# Request Models
# ------------------------------

class SqlQuery(BaseModel):
    """
    Request body for /api/query/validate endpoint.
    Accepts a single SQL query string.
    """
    query: str


class AiRequest(BaseModel):
    """
    Request body for /api/query/suggestfix endpoint.
    Includes the original query and a list of validation issues.
    """
    query: str
    issues: List[str]

# ------------------------------
# Validation Helpers
# ------------------------------

def is_history_comment_present(lines):
    """
    Checks if the SQL query includes a valid history comment.
    Expected format: <Month YYYY> - <Initials> - <Client>-<YY>-<####>
    """
    history_pattern = re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\s+-\s+[A-Z]{2,4}\s+-\s+[A-Z0-9]+-\d{2}-\d{4}",
        re.IGNORECASE
    )
    return any(
        history_pattern.search(line)
        for line in lines
        if line.strip().startswith("History:")
    )

def check_nolock_rules(line, line_number):
    """
    Applies rules related to:
    - WITH (NOLOCK) usage
    - Updatable view restrictions
    - Base table vs. view guidance
    - Invalid NOLOCK usage with functions or procedures
    """
    issues = []
    is_from_or_join = bool(re.search(r'\b(from|join)\s+dbo\.', line, re.IGNORECASE))
    has_nolock = "with(nolock)" in line.lower().replace(" ", "")
    lower = line.lower()

    uses_updatable_view = "updatable" in lower
    uses_inserted_or_deleted = "inserted" in lower or "deleted" in lower
    uses_dbo_v = "dbo.v" in lower
    uses_dbo_func_or_proc = any(prefix in lower for prefix in ["dbo.uf", "dbo.up", "dbo.cp"])

    if is_from_or_join:
        if not has_nolock and not (uses_updatable_view or uses_inserted_or_deleted or uses_dbo_func_or_proc):
            issues.append(f"Line {line_number}: Missing WITH (NOLOCK) on FROM or JOIN. Required unless using updatable views or trigger context.")

        if has_nolock and uses_updatable_view and uses_dbo_v:
            issues.append(f"Line {line_number}: WITH (NOLOCK) should not be used on an updatable view.")

        if not uses_dbo_v and not uses_dbo_func_or_proc:
            issues.append(f"Line {line_number}: Consider using views instead of referencing base tables.")

        if has_nolock and uses_dbo_func_or_proc:
            issues.append(f"Line {line_number}: WITH (NOLOCK) should not be used with functions or procedures (e.g., dbo.uf..., dbo.up..., dbo.cp...).")

    return issues

def check_unrelated_keys_in_joins(line, line_number):
    """
    Detects suspicious joins using mismatched column names.
    Example: A.TypeID = B.PersonID
    Skips if either side is EntityValue.
    """
    issues = []
    if " join " in line.lower() and " on " in line.lower():
        match = re.search(r'\bON\b\s+([a-zA-Z0-9_\.]+)\s*=\s*([a-zA-Z0-9_\.]+)', line, re.IGNORECASE)
        if match:
            left, right = match.group(1), match.group(2)
            left_col = left.split('.')[-1].lower()
            right_col = right.split('.')[-1].lower()

            # Skip if either column is EntityValue
            if left_col != right_col and left_col != 'entityvalue' and right_col != 'entityvalueid':
                issues.append(f"Line {line_number}: Suspicious join condition `{left} = {right}`. Column names differ; check for unrelated keys.")
    return issues


def collect_string_literals(lines):
    """
    Gathers meaningful string literals and tracks usage frequency.
    Filters out formatting fragments like ') + ', empty strings, or punctuation-only tokens.
    """
    string_counts = defaultdict(int)
    string_lines = defaultdict(set)

    for i, line in enumerate(lines):
        matches = re.findall(r"=\s*'([^']*)'", line)

        for s in matches:
            normalized = s.strip()

            # Skip if:
            # - Empty
            # - Only punctuation
            # - One-character alphanumeric literals
            if not normalized or re.fullmatch(r"[^\w\s]+", normalized) or len(normalized) == 1:
                continue

            string_counts[normalized] += 1
            string_lines[normalized].add(i + 1)

    # Convert sets to sorted lists
    string_lines = {k: sorted(v) for k, v in string_lines.items()}
    return string_counts, string_lines

def check_redundant_join_conditions(lines):
    """
    Detects repeated conditions used in multiple JOINs.
    Flags if the same condition (e.g., A.TypeID = 1) is reused.
    """
    join_conditions = []
    join_condition_usage = defaultdict(int)

    for i, line in enumerate(lines):
        if " join " in line.lower() and " on " in line.lower():
            on_clause = re.split(r"\bON\b", line, flags=re.IGNORECASE)
            if len(on_clause) >= 2:
                conditions = re.split(r"\s+AND\s+", on_clause[1], flags=re.IGNORECASE)
                for cond in conditions:
                    normalized = cond.strip().lower().replace(" ", "")
                    join_conditions.append((normalized, i + 1))
                    join_condition_usage[normalized] += 1

    issues = []
    seen = set()
    for cond, count in join_condition_usage.items():
        if count > 1 and cond not in seen:
            for c, line in join_conditions:
                if c == cond:
                    issues.append(f"Line {line}: Redundant join condition '{cond}' appears in multiple joins. Consider removing duplicates.")
                    seen.add(cond)
                    break
    return issues

# ------------------------------
# API Endpoints
# ------------------------------

@app.post("/api/query/validate")
def validate_sql(request: SqlQuery):
    """
    Validates a SQL query against custom business rules.

    Returns:
    - List[str]: Issues found in the query, if any.
    """
    issues = []
    lines = request.query.split('\n')

    # Rule 1–3: NOLOCK and view usage
    for i, line in enumerate(lines):
        issues += check_nolock_rules(line, i + 1)
        issues += check_unrelated_keys_in_joins(line, i + 1)

    # Rule 4: Repetitive string literals
    string_counts, string_lines = collect_string_literals(lines)
    for s, count in string_counts.items():
        if count >= 2:
            used_lines = ", ".join(map(str, string_lines[s]))
            issues.append(f"String literal '{s}' is used {count} times (lines: {used_lines}). Consider using a variable or parameter.")

    # Rule 5: Missing history comment
    if not is_history_comment_present(lines):
        issues.append("Missing valid history comment.")

    # Rule 6: Redundant join conditions
    issues += check_redundant_join_conditions(lines)

    return issues

@app.post("/api/query/suggestfix")
def suggest_fix(request: AiRequest):
    """
    Calls DocsBot AI to generate a fixed version of the SQL query based on validation issues.

    Returns:
    - str: Suggested fixed SQL query.
    """
    team_id = os.getenv("DOCSBOT_TEAM_ID")
    bot_id = os.getenv("DOCSBOT_BOT_ID")
    api_key = os.getenv("DOCSBOT_API_KEY")

    if not api_key or not bot_id or not team_id:
        raise HTTPException(status_code=500, detail="DocsBot API key, team ID, or bot ID not found in environment.")

    # Construct the prompt for DocsBot AI
    prompt = f"""You are a SQL assistant. A user submitted the following SQL query:

{request.query}

It triggered these validation issues:
{chr(10).join(request.issues)}

Please suggest a corrected version of the SQL query, considering all the above issues. Return only the SQL code. No need to start with "```sql" or end with "```".
"""

    try:
        url = f"https://api.docsbot.ai/teams/{team_id}/bots/{bot_id}/chat"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "question": prompt
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            data = response.json()
            print("DocsBot full response:", data)  # optional: remove in production
            return data.get("answer", "No answer returned from DocsBot.")
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
