"""
"""

__version__ = '0.0.5'

import os
import re
import sys
import glob
import argparse

from redbaron import RedBaron
from stdlibs import stdlib_module_names, KNOWN_VERSIONS

# [v for v in KNOWN_VERSIONS if "dataclasses" in ]
DEFAULT_PYVER = f'{sys.version_info.major}.{sys.version_info.minor}'


def parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('globs', nargs='+', type=str, help='modules and packages to edit')
    parser.add_argument('--python-version', '-v', type=str, help='the python version to consider', default=DEFAULT_PYVER)
    parser.add_argument('--ignore', '-i', nargs='+', type=str, help="files matching this regex or starting with any of these strings won't be collected")
    parser.add_argument('--collect-only', action='store_true', help='just collect files, do not run the checks')
    mutex = parser.add_mutually_exclusive_group(required=False)
    mutex.add_argument('--all-deps', '-a', action='store_true', help='include stdlib dependencies')
    mutex.add_argument('--stdlib-only', '-s', action='store_true', help='only outputs stdlib dependencies')
    parser.add_argument('--show-globs', '-g', action='store_true', help='for each dependency, indicates which input globs are needing it')
    parser.add_argument('--max-show', '-m', type=int, help='when showing globs per dependencies, show at most N globs to avoid flooding output (zero means no limit)', default=0)
    parser.add_argument('--porcelain', '-p', action='store_true', help='parsable output')
    parser.add_argument('--keep-subpackages', '-k', action='store_true', help='keep subpackages in the dependency list')
    return parser.parse_args()


def get_imports_from(fnames: list[str]) -> list[tuple[str]]:
    for fname in fnames:
        with open(fname) as fd:
            red = RedBaron(fd.read())
            statements = red.find_all('import')
            for s in statements:
                for module in s.modules():
                    yield tuple(module.split('.'))
            statements = red.find_all('from_import')
            for s in statements:
                module_base = tuple(sub.value for sub in s)
                assert all(isinstance(m, str) for m in module_base), tuple(map(type, module_base))
                for module in s.modules():
                    assert isinstance(module, str), type(module)
                    assert '.' not in module, "that is unexpected. Dots are not allowed in from clause of from_import expression, right ?"
                    yield module_base + (module,)


def is_stdlib(package_name: list[str], stdlib_modules: set[str]) -> bool:
    if '.'.join(package_name) in stdlib_modules:
        return True
    if package_name[0] not in stdlib_modules:
        return False
    # the top-level package is here, but the subpackages ? Hard to say.
    assert package_name[0] in stdlib_modules
    # TODO: for the moment, let's consider that subpackage exists too,
    #  but objects of later python version and subpackages
    #  added by tierce-party packages will not be detected as such.
    return True


def get_files_from_glob(globname: str, ignoreds: list[str]) -> list[str]:

    def file_is_ok(fname: str) -> bool:
        fname = fname[2:] if fname.startswith('./') else fname
        return fname.endswith('.py') and not any(fname.startswith(i) or re.fullmatch(i, fname) for i in ignoreds)

    def get_files_from_dir(dirname: str) -> list[str]:
        with os.scandir(dirname) as it:
            for entry in it:
                if entry.is_file() and file_is_ok(entry.path):
                    yield entry.path
                elif entry.is_dir():
                    yield from get_files_from_dir(entry.path)

    for file in glob.glob(globname):
        if os.path.isfile(file) and file_is_ok(file):
            yield file
        if os.path.isdir(file):
            yield from get_files_from_dir(file)


def get_imports_per_glob(globs: list[str], keep_subpackages: bool, ignoreds: list[str]) -> dict[tuple[str], list[str]]:
    out = {}
    for globname in globs:
        files = tuple(get_files_from_glob(globname, ignoreds))
        for dep in get_imports_from(files):
            out.setdefault(dep, []).append(globname)
    if keep_subpackages:  # just ensure unicity of all globs
        out = {dep: sorted(list(set(globs))) for dep, globs in out.items()}
    else:  # e.g. remove os.path if we have os
        niout = {}
        for dep, globs in out.items():
            niout.setdefault(dep[0], set()).update(set(globs))
        out = {(dep,): sorted(list(globs)) for dep, globs in niout.items()}
    return out


def main():
    args = parse_cli()
    target_pyver = args.python_version or DEFAULT_PYVER

    if re.fullmatch('[23]\.[0-9]+\.[0-9]+', target_pyver):
        target_pyver = '.'.join(target_pyver.split('.')[0:-1])

    if target_pyver not in KNOWN_VERSIONS:
        print(f"Given python version {target_pyver} of type {type(target_pyver)} is not a valid value. Please provide one of {', '.join(KNOWN_VERSIONS)} (default is {DEFAULT_PYVER})")
        exit(1)

    if args.collect_only:
        all_py_files = tuple(
            file
            for globname in args.globs
            for file in get_files_from_glob(globname, args.ignore)
        )
        print(f'Collected {len(all_py_files)} files:')
        for f in all_py_files:
            print(f"\t{f}")
        exit(0)

    stdlib_modules = stdlib_module_names(target_pyver)
    results = (
        (dep, globs, is_stdlib(dep, stdlib_modules))
        for dep, globs in sorted(get_imports_per_glob(args.globs, args.keep_subpackages, args.ignore).items())
    )
    results = (
        (dep, globs, isstd)
        for dep, globs, isstd in results
        if args.all_deps or (args.stdlib_only and isstd) or (not isstd)
    )
    if args.show_globs and args.porcelain:
        for dep, globs, isstd in results:
            print(f"{'.'.join(dep)} {' '.join(globs[:args.max_show] if args.max_show else globs)}")
    elif args.show_globs and not args.porcelain:
        for dep, globs, isstd in results:
            print(f"{'.'.join(dep)} is needed by {len(globs)} of the {len(args.globs)} input globs, {'namely' if len(globs) <= args.max_show else 'including'} {', '.join(globs[:args.max_show] if args.max_show else globs)}.")
    elif args.porcelain:
        for dep, globs, isstd in results:
            print(f"{'.'.join(dep)}")
    else:
        for dep, globs, isstd in results:
            print(f"{'.'.join(dep)} is needed by {len(globs)} of the {len(args.globs)} input globs.")

if __name__ == '__main__':
    main()
