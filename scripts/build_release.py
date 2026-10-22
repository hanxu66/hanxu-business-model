"""Build an allowlisted, deterministic Skill zip; never export research data."""
import argparse
from pathlib import Path
import re
import zipfile

SKILL_FILES = (
    'SKILL.md', 'LICENSE', 'agents/openai.yaml',
    'references/conversation.md', 'references/judgment.md',
    'references/output.md', 'references/examples.md',
)
NAME = 'hanxu-business-model'
FORBIDDEN = (
    r'/Users/[^\s)]+', r'/home/[^\s)]+', r'file://',
    r'(?i)(?:sk-[a-z0-9_-]{20,}|ghp_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,})',
    r'\b1[3-9][0-9]{9}\b',
    r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+',
)


def release_entries(root):
    root = Path(root).absolute()
    skill = root / 'skills' / NAME
    expected = set(SKILL_FILES)
    if root.is_symlink() or any(p.is_symlink() for p in (root / 'skills', skill)):
        raise ValueError('Symlink root is not allowed')
    if not skill.is_dir():
        raise ValueError('Missing Skill directory')
    actual = set()
    for p in skill.rglob('*'):
        if p.is_symlink():
            raise ValueError(f'Symlink is not allowed: {p.name}')
        if p.is_file():
            actual.add(p.relative_to(skill).as_posix())
    if actual != expected:
        raise ValueError(f'Skill allowlist mismatch: missing={expected-actual}, extra={actual-expected}')
    mapping = {str(skill / f): f'{NAME}/{f}' for f in SKILL_FILES}
    mapping[str(root / 'INSTALL.md')] = f'{NAME}/README.md'
    result = {}
    for source, target in mapping.items():
        p = Path(source)
        if p.is_symlink() or not p.is_file():
            raise ValueError(f'Missing file or symlink: {p.name}')
        raw = p.read_bytes()
        content = raw.decode('utf-8')
        if any(re.search(pattern, content) for pattern in FORBIDDEN):
            raise ValueError(f'Private path, contact, or token pattern in {p.name}')
        result[target] = raw
    return result


def build(root, output):
    entries = release_entries(root)  # Validate everything before opening output.
    output = Path(output).absolute()
    root = Path(root).absolute()
    if output.is_relative_to(root / 'skills'):
        raise ValueError('Output must be outside the Skill directory')
    if output.exists():
        raise ValueError('Refusing to overwrite an existing release')
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output.open('xb') as handle:
            created = True
            with zipfile.ZipFile(handle, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, raw in sorted(entries.items()):
                    info = zipfile.ZipInfo(name, (2026, 10, 21, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, raw)
    except Exception:
        # An incomplete file from this invocation must never look like a release.
        if created and output.is_file():
            output.unlink()
        raise
    return {'files': len(entries), 'bytes': output.stat().st_size, 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1], args.output))
