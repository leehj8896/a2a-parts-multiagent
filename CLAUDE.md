# Claude Code Guidelines for a2a-parts-multiagent

## Python Environment
When running tests or executing Python code, always use the Python environment from the `.venv` folder in this project:
```bash
.venv/bin/python -m pytest ...
.venv/bin/python script.py
```

Do NOT use system Python or global Python installations. This ensures consistency with the project's dependencies.
