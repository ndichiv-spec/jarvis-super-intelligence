# Release Process

## Version Scheme

Jarvis follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking API or architectural changes
- **MINOR**: New features, backward-compatible
- **PATCH**: Bug fixes, backward-compatible

## Version Source of Truth

The authoritative version is in `pyproject.toml`:

```toml
[project]
version = "0.1.0"
```

All other version references (config files, env files, etc.) must be kept in sync.

## Release Checklist

### 1. Pre-Release

- [ ] All tests pass: `pytest tests/ --cov=infrastructure --cov=performance`
- [ ] Linting passes: `pre-commit run --all-files`
- [ ] Type checking passes: `mypy infrastructure/ core/`
- [ ] Security scan passes: `bandit -r infrastructure/ core/`
- [ ] Update version: `python scripts/update_version.py <new_version>`
- [ ] Update CHANGELOG.md with new release notes
- [ ] Update any version references in docs and config files
- [ ] Create a release branch: `release/v<version>`

### 2. Release

- [ ] Merge release branch into `main`
- [ ] Tag the release: `git tag -a v<version> -m "Release v<version>"`
- [ ] Push tag: `git push origin v<version>`
- [ ] GitHub Actions release workflow will:
  - Build and publish package
  - Create GitHub Release with changelog
  - Deploy to production (if applicable)

### 3. Post-Release

- [ ] Merge `main` back to `develop`
- [ ] Bump version to next dev version (e.g., `0.2.0-dev`)
- [ ] Update ROADMAP.md if needed
- [ ] Announce release

## Changelog Format

The CHANGELOG.md follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/):

```markdown
## [0.1.1] - 2024-06-01

### Added
- New feature description (#PR)

### Changed
- Change description (#PR)

### Fixed
- Bug fix description (#PR)

### Security
- Security fix description (#PR)
```

## Version Update Script

```bash
python scripts/update_version.py 0.2.0
```

This updates:
- `pyproject.toml` version field
- `core/config/settings.py` version
- `infrastructure/config/settings.py` version

## Automated Release

The `.github/workflows/release.yml` workflow:
1. Triggers on tag push matching `v*`
2. Creates a GitHub Release
3. Builds the package
4. Attaches build artifacts

## Hotfix Process

For critical production fixes:

1. Branch from `main`: `git checkout -b hotfix/v<patch> main`
2. Apply the fix
3. Update version and changelog
4. Create PR into `main` and `develop`
5. Tag and release
