# -*- coding: utf-8 -*-
"""
evaluation — ArticulateX Evaluation Framework.

Three-tier rule evaluation:
  1. Deterministic (code-only)
  2. Pattern (regex/NLP)
  3. Subjective (LLM-as-judge)

Plus: caching, provider management, quota protection, reporting.
"""
