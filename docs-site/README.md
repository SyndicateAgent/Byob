# BYOB Documentation Site

This directory contains the static documentation site deployed to GitHub Pages. The site summarizes the same product surface as the root `README.md`: self-hosted infrastructure, document ingestion, hybrid retrieval, multimodal RAG, MCP tools, the console QA Agent, and production boundary notes.

The deployment workflow is defined in `.github/workflows/pages.yml`. After the workflow runs on the `main` branch, the public site will be available at:

```text
https://syndicateagent.github.io/Byob/
```

Local preview:

```powershell
Set-Location docs-site
python -m http.server 8080
```
