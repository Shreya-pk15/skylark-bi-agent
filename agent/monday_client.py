"""
monday_client.py
-----------------
Thin wrapper around the monday.com GraphQL v2 API.

The agent itself only ever calls the read methods (get_board_items /
get_board_schema) — per the assignment spec the agent is READ ONLY and must
never hardcode CSV data; it pulls live from monday.com on every query.

The write helpers (create_board, create_columns, create_item) are only used
once, by scripts/setup_monday_boards.py, to provision the two boards from
the cleaned CSVs. They live here too so there's a single source of truth for
the API contract, but app.py / agent/core.py never import them.
"""
import os
import time
from typing import Any

import requests

MONDAY_API_URL = "https://api.monday.com/v2"


class MondayClient:
    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or os.environ.get("MONDAY_API_TOKEN")
        if not self.api_token:
            raise ValueError(
                "No monday.com API token found. Set MONDAY_API_TOKEN as an "
                "env var or Streamlit secret."
            )
        self.headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
            "API-Version": "2024-10",
        }

    def _post(self, query: str, variables: dict | None = None, retries: int = 3) -> dict:
        last_err = None
        for attempt in range(retries):
            try:
                resp = requests.post(
                    MONDAY_API_URL,
                    json={"query": query, "variables": variables or {}},
                    headers=self.headers,
                    timeout=30,
                )
                data = resp.json()
                if "errors" in data:
                    raise RuntimeError(f"monday.com API error: {data['errors']}")
                return data["data"]
            except (requests.RequestException, RuntimeError) as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))  # simple backoff for transient failures
        raise RuntimeError(f"monday.com API call failed after {retries} attempts: {last_err}")

    # -------------------------- READ (used by the agent) -------------------

    def list_boards(self) -> list[dict]:
        q = """
        query {
          boards (limit: 50) { id name }
        }
        """
        return self._post(q)["boards"]

    def get_board_schema(self, board_id: str) -> list[dict]:
        q = """
        query ($ids: [ID!]) {
          boards (ids: $ids) {
            columns { id title type }
          }
        }
        """
        boards = self._post(q, {"ids": [board_id]})["boards"]
        return boards[0]["columns"] if boards else []

    def get_board_items(self, board_id: str, limit: int = 500) -> list[dict]:
        """Pull every item + column values from a board, paginating via cursor."""
        items: list[dict] = []
        cursor = None
        q = """
        query ($ids: [ID!], $cursor: String) {
          boards (ids: $ids) {
            items_page (limit: 100, cursor: $cursor) {
              cursor
              items {
                id
                name
                column_values { id text value column { title } }
              }
            }
          }
        }
        """
        while True:
            data = self._post(q, {"ids": [board_id], "cursor": cursor})
            page = data["boards"][0]["items_page"]
            items.extend(page["items"])
            cursor = page["cursor"]
            if not cursor or len(items) >= limit:
                break
        return items

    def items_to_records(self, items: list[dict]) -> list[dict]:
        """Flatten monday.com's item/column_values shape into plain dict rows."""
        records = []
        for it in items:
            row = {"__item_name": it["name"], "__item_id": it["id"]}
            for cv in it["column_values"]:
                row[cv["column"]["title"]] = cv["text"]
            records.append(row)
        return records

    # -------------------------- WRITE (setup script only) ------------------

    def create_board(self, name: str, board_kind: str = "public") -> str:
        q = """
        mutation ($name: String!, $kind: BoardKind!) {
          create_board (board_name: $name, board_kind: $kind) { id }
        }
        """
        return self._post(q, {"name": name, "kind": board_kind})["create_board"]["id"]

    def create_column(self, board_id: str, title: str, col_type: str) -> str:
        q = """
        mutation ($board: ID!, $title: String!, $type: ColumnType!) {
          create_column (board_id: $board, title: $title, column_type: $type) { id }
        }
        """
        return self._post(
            q, {"board": board_id, "title": title, "type": col_type}
        )["create_column"]["id"]

    def create_item(self, board_id: str, item_name: str, column_values: dict[str, Any]) -> str:
        import json
        q = """
        mutation ($board: ID!, $name: String!, $vals: JSON!) {
          create_item (board_id: $board, item_name: $name, column_values: $vals) { id }
        }
        """
        return self._post(
            q, {"board": board_id, "name": item_name, "vals": json.dumps(column_values)}
        )["create_item"]["id"]
