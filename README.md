# Jottit

A radically simple web publishing tool. Write markdown, get a beautiful page with a shareable URL.

The original Jottit was co-created by Simon Carstensen and Aaron Swartz in 2007. This is a spiritual successor — simpler, with dramatically better typography and design.

**Live at [jottit.org](https://jottit.org)**

## How it works

1. Click "Create a page"
2. Write markdown in the split-pane editor
3. Hit publish — get a shareable URL

No account required. Claim your page later with just an email.

## Stack

- Flask + Jinja2 (server-side rendered)
- Vanilla JS (editor only — no JS on published pages)
- Vanilla CSS
- PostgreSQL

## Local development

```bash
# Create the dev database
psql -c "CREATE DATABASE jottit_dev;"

# Install dependencies
pip install -r requirements.txt

# Run the dev server
flask run --debug
```

## Tests

```bash
pytest
```

## Funding

This project was funded by Paul Graham.

## License

MIT
