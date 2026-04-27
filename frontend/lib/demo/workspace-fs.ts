/**
 * Seeded filesystem for the demo Workspace IDE.
 * The "scraper-agent" project demonstrates a small but realistic Python
 * codebase that agents can navigate and modify.
 */

export interface DemoFileEntry {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number | null;
  children: DemoFileEntry[] | null;
  content?: string;
}

const README = `# scraper-agent

A small example project demonstrating the Forge agent platform.

## Structure

- \`src/scraper.py\` — fetches raw HTML for a target URL
- \`src/parser.py\` — extracts structured data from the HTML
- \`src/output.py\` — writes the structured data to disk
- \`tests/test_scraper.py\` — smoke tests
- \`data/sample_input.json\` — fixture for the parser
- \`.forge/workspace.toml\` — Forge runtime configuration

## Run locally

\`\`\`bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m src.scraper https://example.com
\`\`\`

> Demo mode: edits stay in your browser and revert on refresh. Fork the workspace
> to persist changes.
`;

const REQUIREMENTS = `httpx==0.27.0
beautifulsoup4==4.12.3
pydantic==2.7.1
pytest==8.2.0
`;

const INIT_PY = `"""scraper-agent — a small example project for the Forge demo workspace."""

__version__ = "0.1.0"
`;

const SCRAPER_PY = `"""HTTP client wrapper for fetching pages."""

from __future__ import annotations

import httpx


DEFAULT_TIMEOUT = 10.0


def fetch(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Fetch \`url\` and return the response body as text.

    Raises:
        httpx.HTTPStatusError: if the response status is 4xx or 5xx.
    """
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m src.scraper <url>", file=sys.stderr)
        sys.exit(2)

    print(fetch(sys.argv[1]))
`;

const PARSER_PY = `"""HTML parsing utilities."""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Article:
    title: str
    body: str


def parse_article(html: str) -> Article:
    """Extract the title and body of an article from raw HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    body = "\\n\\n".join(paragraphs)
    return Article(title=title, body=body)
`;

const OUTPUT_PY = `"""Write parsed articles to disk in JSON format."""

from __future__ import annotations

import json
from pathlib import Path

from .parser import Article


def write_article(article: Article, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {"title": article.title, "body": article.body}
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination
`;

const TEST_SCRAPER_PY = `"""Smoke tests for the scraper module."""

from __future__ import annotations

import pytest

from src.scraper import fetch


@pytest.mark.network
def test_fetch_returns_text() -> None:
    body = fetch("https://example.com")
    assert "Example Domain" in body
`;

const SAMPLE_INPUT_JSON = `{
  "url": "https://example.com",
  "expected_title": "Example Domain",
  "expected_keywords": ["example", "illustrative"]
}
`;

const WORKSPACE_TOML = `# Forge workspace configuration
[workspace]
name = "scraper-agent"
description = "Small example project for the Forge demo"
runtime = "python-3.12"

[agents.default_model]
provider = "openai"
model = "gpt-4o-mini"

[tools]
allow = ["fetch_url", "knowledge_retrieval", "workspace_write"]
`;

function file(name: string, path: string, content: string): DemoFileEntry {
  return {
    name,
    path,
    type: "file",
    size: content.length,
    children: null,
    content,
  };
}

function dir(name: string, path: string, children: DemoFileEntry[]): DemoFileEntry {
  return { name, path, type: "directory", size: null, children };
}

export const DEMO_WORKSPACE_TREE: DemoFileEntry[] = [
  file("README.md", "README.md", README),
  file("requirements.txt", "requirements.txt", REQUIREMENTS),
  dir("src", "src", [
    file("__init__.py", "src/__init__.py", INIT_PY),
    file("scraper.py", "src/scraper.py", SCRAPER_PY),
    file("parser.py", "src/parser.py", PARSER_PY),
    file("output.py", "src/output.py", OUTPUT_PY),
  ]),
  dir("tests", "tests", [
    file("test_scraper.py", "tests/test_scraper.py", TEST_SCRAPER_PY),
  ]),
  dir("data", "data", [file("sample_input.json", "data/sample_input.json", SAMPLE_INPUT_JSON)]),
  dir(".forge", ".forge", [file("workspace.toml", ".forge/workspace.toml", WORKSPACE_TOML)]),
];

export const DEMO_WORKSPACE_ID = "ws-demo-scraper-agent";

export const DEMO_WORKSPACE = {
  id: DEMO_WORKSPACE_ID,
  user_id: "demo",
  name: "scraper-agent",
  description: "A small example project for the Forge demo workspace.",
  path: "/workspaces/scraper-agent",
  status: "active",
  settings: {},
  created_at: "2026-04-15T09:00:00Z",
  updated_at: "2026-04-25T18:30:00Z",
};

export const DEMO_AGENT_RUN_COMMENT =
  "# touched by the Forge demo agent — workspace_write\n";

export const DEMO_RECENT_AGENT_ACTIVITY = [
  {
    id: "act-1",
    timestamp: "2026-04-25T18:24:11Z",
    type: "edit",
    path: "src/parser.py",
    summary: "Refactored parse_article to use BeautifulSoup string accessors.",
  },
  {
    id: "act-2",
    timestamp: "2026-04-25T18:18:42Z",
    type: "create",
    path: "tests/test_scraper.py",
    summary: "Added a network-marked smoke test for fetch().",
  },
  {
    id: "act-3",
    timestamp: "2026-04-25T18:11:09Z",
    type: "edit",
    path: "src/scraper.py",
    summary: "Set follow_redirects=True and configured request timeout.",
  },
  {
    id: "act-4",
    timestamp: "2026-04-25T18:02:34Z",
    type: "edit",
    path: "requirements.txt",
    summary: "Pinned httpx to 0.27.0 and bumped pydantic.",
  },
];

export const DEMO_TERMINAL_TRANSCRIPT = [
  { input: "forge cu status", delay: 0 },
  { output: "Steer: ✓ active (macOS)\nDrive: ✓ active (tmux session demo-mac-mini)\nOCR:   ✓ tesseract 5.4.1\n", delay: 250 },
  { input: "forge agents list --workspace scraper-agent", delay: 600 },
  {
    output:
      "  ID                   NAME                STATUS    LAST RUN\n" +
      "  agt_research_2x     Research Agent       idle      18m ago\n" +
      "  agt_extract_7y      Data Extractor       running   just now\n" +
      "  agt_review_4q       Code Reviewer        idle      —\n",
    delay: 1100,
  },
  { input: "", delay: 1800 },
];

export function findDemoFile(path: string): DemoFileEntry | null {
  function walk(entries: DemoFileEntry[]): DemoFileEntry | null {
    for (const entry of entries) {
      if (entry.path === path) return entry;
      if (entry.children) {
        const found = walk(entry.children);
        if (found) return found;
      }
    }
    return null;
  }
  return walk(DEMO_WORKSPACE_TREE);
}
