"""Exact source/configuration hashes shared by release validation and packaging."""
import hashlib


def source_stamp(root):
    result = {}
    for folder in ('src', 'tests', 'tools', 'windows', '.github'):
        for path in sorted((root / folder).rglob('*')):
            relative = path.relative_to(root)
            if (path.is_file() and path.suffix in {'.py', '.cs', '.ps1', '.iss', '.yml', '.csproj', '.manifest', '.ico', '.txt'}
                    and not {'bin', 'obj', '__pycache__'}.intersection(relative.parts)):
                result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('requirements-build.txt', 'pyproject.toml', 'global.json', '.gitignore'):
        result[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    return result
