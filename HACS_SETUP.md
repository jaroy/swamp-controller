# HACS Setup Complete

Your SWAMP Controller integration is now fully configured for HACS distribution!

## What Was Done

### 1. PyPI Package Setup

✅ **Package name**: `crestron-swamp-controller`
✅ **pyproject.toml** configured with all metadata for PyPI
✅ **LICENSE** file added (MIT)
✅ Package builds successfully and includes all necessary code

### 2. Home Assistant Integration

✅ **manifest.json** updated to require `crestron-swamp-controller==1.0.0` from PyPI
✅ Integration uses standard imports: `from swamp.core...`
✅ No build scripts or code duplication needed
✅ **hacs.json** configured for HACS compatibility

### 3. GitHub Actions

✅ **`.github/workflows/hacs-validation.yml`** - Validates HACS compatibility on push
✅ **`.github/workflows/publish-pypi.yml`** - Automatically publishes to PyPI on release

### 4. Documentation

✅ **README.md** - Updated with PyPI badge and HACS installation instructions
✅ **HOMEASSISTANT.md** - Simplified installation (no manual pip steps)
✅ **RELEASING.md** - Complete release process documentation

## Architecture

This setup uses the **standard pattern** for Home Assistant integrations:

```
Developer workflow:
  Edit code in swamp/ → Commit → Push

Release workflow:
  1. Update versions in pyproject.toml and manifest.json
  2. Create GitHub release with tag (e.g., v1.0.0)
  3. GitHub Actions automatically publishes to PyPI
  4. Users install via HACS
  5. Home Assistant auto-downloads from PyPI

User workflow:
  HACS → Install "Crestron SWAMP Controller"
  ↓
  Home Assistant downloads crestron-swamp-controller from PyPI
  ↓
  Integration works immediately
```

## Before Your First Release

### 1. Set up PyPI Trusted Publishing (Recommended)

1. Create an account on https://pypi.org/
2. Go to "Publishing" → "Add a new pending publisher"
3. Fill in:
   - **PyPI Project Name**: `crestron-swamp-controller`
   - **Owner**: `jaroy`
   - **Repository name**: `swamp-controller`
   - **Workflow name**: `publish-pypi.yml`
   - **Environment name**: (leave blank)

This allows GitHub Actions to publish without needing an API token.

### 2. Test Build Locally

```bash
pip install build
python -m build
# Check output in dist/
```

### 3. Optional: Test on Test PyPI First

```bash
# Manually upload to test.pypi.org first
pip install twine
twine upload --repository testpypi dist/*

# Test install
pip install --index-url https://test.pypi.org/simple/ crestron-swamp-controller
```

## Creating Your First Release

Follow the detailed steps in **RELEASING.md**:

1. Update versions (3 places):
   - `pyproject.toml`: line 7
   - `manifest.json`: line 12 (requirements)
   - `manifest.json`: line 14 (version)

2. Commit and push:
   ```bash
   git add pyproject.toml custom_components/swamp_controller/manifest.json
   git commit -m "Release v1.0.0"
   git push
   ```

3. Create and push tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

4. Create GitHub Release from the tag

5. GitHub Actions will automatically:
   - Build the Python package
   - Publish to PyPI
   - HACS users will see the update

## For Users

### Installation

1. Add custom repository in HACS:
   - URL: `https://github.com/jaroy/swamp-controller`
   - Type: Integration

2. Install "Crestron SWAMP Controller"

3. Restart Home Assistant

4. Add integration via Settings > Devices & Services

Done! The `crestron-swamp-controller` package installs automatically.

## Benefits of This Approach

✅ **No code duplication** - Single source of truth in `swamp/`
✅ **No build scripts** - Standard Python packaging
✅ **Easy maintenance** - Edit once, publish everywhere
✅ **Professional** - Same pattern as official HA integrations
✅ **PyPI discoverability** - Package can be used standalone
✅ **Automatic updates** - HACS + PyPI work together seamlessly

## File Structure

```
swamp-controller/
├── swamp/                          # Python package (source of truth)
│   ├── core/
│   ├── models/
│   ├── network/
│   └── protocol/
├── custom_components/
│   └── swamp_controller/           # HA integration (imports from swamp)
│       ├── __init__.py
│       ├── config_flow.py
│       ├── media_player.py
│       ├── manifest.json           # Requires crestron-swamp-controller from PyPI
│       └── ...
├── pyproject.toml                  # Package metadata
├── hacs.json                       # HACS metadata
├── .github/workflows/
│   ├── hacs-validation.yml
│   └── publish-pypi.yml
└── RELEASING.md                    # Release instructions
```

## Questions?

- **PyPI setup**: See RELEASING.md
- **HACS installation**: See README.md and HOMEASSISTANT.md
- **Development**: Edit code in `swamp/`, commit, and push normally

Happy releasing! 🚀
