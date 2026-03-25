# XD Macau Basic Case

Static GitHub Pages site for Macau Basic Law case materials.

## Structure

- `1999-2010/`, `2011-2018/`, `2019-2025/`: source txt files
- `scripts/build_site.py`: converts txt files into static HTML pages
- `docs/`: generated GitHub Pages output

## Build

Use a local Python 3 interpreter and run:

```powershell
python scripts/build_site.py
```

The generated site is emitted into `docs/`.
