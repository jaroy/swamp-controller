# Release Process

This document describes how to release a new version of SWAMP Controller.

## Overview

The project uses a dual-release approach:
1. **PyPI** - Python package (`crestron-swamp-controller`) for the CLI tool and core library
2. **GitHub** - Home Assistant integration for HACS

Both should be versioned together and released at the same time.

## Prerequisites

### First-time setup for PyPI

1. Create an account on [PyPI](https://pypi.org/)
2. Set up trusted publishing (recommended) or API token:

#### Option A: Trusted Publishing (Recommended)

1. Go to your PyPI project settings
2. Add a trusted publisher:
   - GitHub owner: `jaroy`
   - Repository: `swamp-controller`
   - Workflow: `publish-pypi.yml`
   - Environment: leave blank

This allows GitHub Actions to publish without needing an API token.

#### Option B: API Token

1. Generate an API token at https://pypi.org/manage/account/token/
2. Add it as a GitHub secret:
   - Go to your repo > Settings > Secrets and variables > Actions
   - Add secret named `PYPI_API_TOKEN` with your token value

## Release Checklist

### 1. Prepare the Release

- [ ] Ensure all changes are committed and tests pass
- [ ] Update version in both places:
  - [ ] `pyproject.toml` - line 7: `version = "X.Y.Z"`
  - [ ] `custom_components/swamp_controller/manifest.json` - line 12: `"crestron-swamp-controller==X.Y.Z"`
  - [ ] `custom_components/swamp_controller/manifest.json` - line 14: `"version": "X.Y.Z"`
- [ ] Update CHANGELOG.md (if you have one) or document changes
- [ ] Commit version changes:
  ```bash
  git add pyproject.toml custom_components/swamp_controller/manifest.json
  git commit -m "Bump version to X.Y.Z"
  git push
  ```

### 2. Create and Push Tag

```bash
# Create annotated tag
git tag -a vX.Y.Z -m "Release version X.Y.Z"

# Push the tag
git push origin vX.Y.Z
```

### 3. Create GitHub Release

1. Go to https://github.com/jaroy/swamp-controller/releases/new
2. Select the tag you just created (`vX.Y.Z`)
3. Title: `vX.Y.Z`
4. Description: List the changes, features, and bug fixes
5. Click "Publish release"

This will trigger the PyPI publish workflow automatically.

### 4. Verify PyPI Publication

1. Check the GitHub Actions workflow completes successfully
2. Verify the package appears on https://pypi.org/project/crestron-swamp-controller/
3. Test installation:
   ```bash
   pip install crestron-swamp-controller==X.Y.Z
   ```

### 5. Update HACS

Users with HACS will automatically see the update. No additional steps needed!

## Testing a Release Before Publishing

### Test PyPI Build Locally

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Check the build
twine check dist/*

# Test install from local build
pip install dist/swamp_controller-X.Y.Z-py3-none-any.whl
```

### Test Publishing to Test PyPI

You can test the full publication process using Test PyPI:

1. Go to the Actions tab in GitHub
2. Select "Publish to PyPI" workflow
3. Click "Run workflow"
4. Check "Publish to Test PyPI"
5. Run workflow

Then test installation:
```bash
pip install --index-url https://test.pypi.org/simple/ crestron-swamp-controller==X.Y.Z
```

## Hotfix Releases

For urgent bug fixes:

1. Create a hotfix branch from the tag:
   ```bash
   git checkout -b hotfix/X.Y.Z+1 vX.Y.Z
   ```

2. Make your fix and commit

3. Update versions to X.Y.Z+1

4. Follow the normal release process

## Troubleshooting

### PyPI publish fails with "File already exists"

- PyPI doesn't allow re-uploading the same version
- You need to increment the version number and create a new release
- Delete the git tag locally and remotely if needed:
  ```bash
  git tag -d vX.Y.Z
  git push origin :refs/tags/vX.Y.Z
  ```

### HACS not showing the update

- HACS caches repository information
- Users may need to wait up to 24 hours or manually refresh
- Ensure the manifest.json version was updated

### Import errors after installing from PyPI

- Verify the package structure is correct in the built wheel
- Check that `swamp` is included in the package:
  ```bash
  unzip -l dist/swamp_controller-X.Y.Z-py3-none-any.whl
  ```

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes
- **MINOR** (0.X.0): New features, backwards compatible
- **PATCH** (0.0.X): Bug fixes, backwards compatible

Examples:
- `1.0.0` - Initial stable release
- `1.1.0` - Added new feature (e.g., support for new message type)
- `1.1.1` - Fixed bug in volume control
- `2.0.0` - Changed API in breaking way
