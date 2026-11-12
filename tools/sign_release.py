#!/usr/bin/env python3
"""Signs a release's downloads with Project Moon Pi's release key, so the app's Update installs only what was signed
here (signing.py checks it before installing anything):

    python3 tools/sign_release.py dist/SkyScope-1.11.0-for-Mac.dmg dist/Install-SkyScope-1.11.0-for-Windows.exe

writes <file>.sig beside each (OpenSSH's "ssh-keygen -Y sign", namespace projectmoonpi-update), checks each with the
app's own signing.py, and stops if anything's wrong. Upload the .sig files to the release with the downloads.

    python3 tools/sign_release.py --release v1.0.12 [--repo projectmoonpi/train-tracker] [--publish]

does it for a release already on GitHub (Train Tracker's Release workflow builds it as a draft): downloads its .dmg
and .exe, signs them and uploads the .sig files (gh release upload). --publish then publishes the draft, as the
latest release, and keeps only it (tools/prune_releases.py --delete): so nobody sees a release before it's signed.

The private key is ~/CLAUDE CODE PROJECTS/pmp-release-key/pmp-release, on this Mac only: never in a repo, never on
GitHub. Without it nothing can be signed, and copies in use won't update themselves (people would download the next
version by hand). The same file is in SkyScope and US Train Tracker. Designed and Created by Project Moon Pi.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = Path.home() / "CLAUDE CODE PROJECTS" / "pmp-release-key" / "pmp-release"
NAMESPACE = "projectmoonpi-update"


def checker():
    """The app's own signing.py (SkyScope: beside skyscope.py; Train Tracker: in the package)."""
    for p in (ROOT / "signing.py", ROOT / "src" / "train_tracker" / "signing.py"):
        if p.exists():
            spec = importlib.util.spec_from_file_location("signing", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    sys.exit("signing.py not found")


def sign(files) -> list:
    if not KEY.exists():
        sys.exit(f"The release key isn't here ({KEY}): nothing was signed.")
    check = checker()
    if check.NAMESPACE != NAMESPACE:
        sys.exit("signing.py's namespace differs from this tool's")
    sigs = []
    for f in map(Path, files):
        if not f.is_file():
            sys.exit(f"{f}: no such file")
        sig = f.with_name(f.name + ".sig")
        sig.unlink(missing_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(KEY), "-n", NAMESPACE, str(f)],
                       check=True, stdin=subprocess.DEVNULL)
        check.check_file(str(f), sig.read_text())          # (as the app will: stops here if it doesn't pass)
        print(f"signed {f.name} -> {sig.name} (checked)")
        sigs.append(sig)
    return sigs


def gh(*args, **kw):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, **kw).stdout


def sign_release(tag: str, repo: str | None):
    where = ["-R", repo] if repo else []
    assets = [a["name"] for a in json.loads(gh("release", "view", tag, *where, "--json", "assets"))["assets"]]
    wanted = [a for a in assets if a.endswith((".dmg", ".exe"))]
    if not wanted:
        sys.exit(f"{tag} has no .dmg or .exe to sign")
    with tempfile.TemporaryDirectory() as tmp:
        for name in wanted:
            gh("release", "download", tag, *where, "-p", name, "-D", tmp, "--clobber")
        sigs = sign([Path(tmp) / n for n in wanted])
        gh("release", "upload", tag, *where, "--clobber", *map(str, sigs))
    print(f"uploaded {len(sigs)} signature(s) to {tag}")


def publish(tag: str, repo: str | None):
    """The signed draft becomes the latest release, and the older ones go."""
    where = ["-R", repo] if repo else []
    gh("release", "edit", tag, *where, "--draft=false", "--latest")
    print(f"published {tag}")
    subprocess.run([sys.executable, str(ROOT / "tools" / "prune_releases.py"), "--delete"], check=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--release"] and len(a) >= 2:
        repo = a[a.index("--repo") + 1] if "--repo" in a else None
        sign_release(a[1], repo)
        if "--publish" in a:
            publish(a[1], repo)
    elif a and not a[0].startswith("-"):
        sign(a)
    else:
        sys.exit(__doc__)
