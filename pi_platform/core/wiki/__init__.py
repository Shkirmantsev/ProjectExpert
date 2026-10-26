"""The LLM Wiki: canonical, LLM-curated project knowledge.

See :mod:`pi_platform.core.wiki.llm_wiki` for the storage contract.
"""

from __future__ import annotations

from .llm_wiki import (
    INDEX_FILENAME,
    LOG_FILENAME,
    LlmWiki,
    LlmWikiError,
    PAGE_TYPE_ALLOWED,
    WIKI_DIR_NAME,
    WikiPage,
    wiki_root_for,
)

__all__ = [
    "LlmWiki",
    "LlmWikiError",
    "WikiPage",
    "WIKI_DIR_NAME",
    "INDEX_FILENAME",
    "LOG_FILENAME",
    "PAGE_TYPE_ALLOWED",
    "wiki_root_for",
]
