import argparse
import os
import re
import shutil

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
VIEWER = os.path.join(REPO, "src", "viewer")


def scene_names(html):
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    scene = re.search(r'<span class="scene">(.*?)</span>', html, re.S)
    return (title.group(1) if title else None), (scene.group(1) if scene else None)


def sync(site, dry):
    index = os.path.join(site, "index.html")
    title, scene = scene_names(open(index, encoding="utf-8").read()) if os.path.exists(index) else (None, None)
    changed = []
    for name in sorted(os.listdir(VIEWER)):
        src, dst = os.path.join(VIEWER, name), os.path.join(site, name)
        if os.path.isdir(src):
            changed.append(name + "/")
            if not dry:
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
        else:
            changed.append(name)
            if not dry:
                shutil.copyfile(src, dst)
    if not dry and (title or scene):
        html = open(index, encoding="utf-8").read()
        template_title, template_scene = scene_names(html)
        if title and template_title:
            html = html.replace(f"<title>{template_title}</title>", f"<title>{title}</title>", 1)
        if scene and template_scene:
            html = html.replace(f'<span class="scene">{template_scene}</span>', f'<span class="scene">{scene}</span>', 1)
        open(index, "w", encoding="utf-8").write(html)
    return title, changed


def main():
    ap = argparse.ArgumentParser(description="Copy src/viewer into every scenes/<name>/site, keeping each scene's title and assets")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = os.path.join(REPO, "scenes")
    for scene in sorted(os.listdir(root)):
        site = os.path.join(root, scene, "site")
        if not os.path.isdir(site):
            continue
        title, changed = sync(site, a.dry_run)
        print(f"{scene:22s} {title or '(no title)'}: {len(changed)} viewer files {'would be ' if a.dry_run else ''}updated")


if __name__ == "__main__":
    main()
